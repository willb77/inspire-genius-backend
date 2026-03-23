"""
Multi-Agent Call Utility

This utility allows any agent to internally call another agent and get a response.
It works like the WebSocket flow but without streaming to the user.
"""
import asyncio
from typing import Optional

from google import genai
from google.genai import types

from ai.ai_agent_services.agent_utils import alex_speech_instructions
from prism_inspire.core.ai_client import genai_client
from prism_inspire.core.log_config import logger


async def call_agent(
    agent_id: str,
    user_input: str,
    connection_handler,
    chat_history: list = None,
) -> str:
    """
    Call another agent internally and get its response.
    
    This function mirrors the WebSocket flow:
    1. Gets the agent logic based on agent_id/name
    2. Calls get_knowledge_and_prompt
    3. Generates a response using Gemini
    
    Args:
        agent_id: The ID or name of the agent to call (can be agent name like "PRISM Coach")
        user_input: The user's query to pass to the agent
        connection_handler: The connection handler with user context (vector_store, user_data, etc.)
        chat_history: Optional chat history for context
    
    Returns:
        The agent's text response
    """
    try:
        from ai.ai_agent_services.agent_services.agent_services import get_agent_logic
        
        # Get the appropriate agent logic based on agent_id
        agent_logic = get_agent_logic(agent_id, connection_handler)
        
        # Get knowledge and prompt from the agent
        _, system_prompt = await agent_logic.get_knowledge_and_prompt(user_input)
        
        # Generate response without streaming
        response = await generate_response_no_stream(
            user_input=user_input,
            system=system_prompt,
            chat_history=chat_history or []
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error calling agent {agent_id}: {e}")
        return ""


async def call_agent_by_name(
    agent_name: str,
    user_input: str,
    connection_handler,
    chat_history: list = None,
) -> str:
    """
    Call another agent by its name and get its response.
    
    Args:
        agent_name: The name of the agent (e.g., "PRISM Coach", "Career Coach")
        user_input: The user's query
        connection_handler: The connection handler with user context
        chat_history: Optional chat history for context
    
    Returns:
        The agent's text response
    """
    try:
        # Map names to agent classes
        from ai.ai_agent_services.agent_services.agents.prism_coach_agent import PrismCoachAgent
        from ai.ai_agent_services.agent_services.agents.career_agent import CareerAgent
        from ai.ai_agent_services.agent_services.agents.training_agent import TrainingAgent
        from ai.ai_agent_services.agent_services.agents.default_agent import DefaultAgent
        
        agent_map = {
            "PRISM Coach": PrismCoachAgent,
            "Career Coach": CareerAgent,
            "Training Coach": TrainingAgent,
        }
        
        agent_class = agent_map.get(agent_name, DefaultAgent)
        agent_logic = agent_class(connection_handler)
        
        # Get knowledge and prompt from the agent
        _, system_prompt = await agent_logic.get_knowledge_and_prompt(user_input)
        
        # Generate response without streaming
        response = await generate_response_no_stream(
            user_input=user_input,
            system=system_prompt,
            chat_history=chat_history or []
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error calling agent by name '{agent_name}': {e}")
        return ""


async def generate_response_no_stream(
    user_input: str,
    system: str,
    chat_history: list = None,
) -> str:
    """
    Generate a response using Gemini without streaming.
    This is used for internal agent-to-agent calls.
    
    Args:
        user_input: The user's query
        system: The system prompt with knowledge base
        chat_history: Optional chat history for context
    
    Returns:
        The generated response text
    """
    try:
        # Build conversation history
        contents = []
        
        # Add chat history if available
        if chat_history:
            for message in chat_history:
                role = "user" if message["role"] == "user" else "model"
                content_text = message["content"]
                if isinstance(content_text, list):
                    content_text = (
                        content_text[0]["text"]
                        if content_text and "text" in content_text[0]
                        else ""
                    )
                
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content_text)],
                    )
                )
        
        # Add current user input
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_input)],
            )
        )
        
        generate_content_config = types.GenerateContentConfig(
            system_instruction=[types.Part.from_text(text=system)],
            thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"),
            temperature=0.9,
            max_output_tokens=1500,
        )
        
        response = genai_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=generate_content_config,
        )
        
        response_text = response.text
        logger.info(f"Internal agent call generated response: {len(response_text)} chars")
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error in generate_response_no_stream: {e}")
        return ""
