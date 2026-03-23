import asyncio
import json

from ai.ai_agent_services.agent_services.agents.base_agent import BaseAgent
from ai.ai_agent_services.agent_services.agent_call import call_agent_by_name
from ai.ai_agent_services.ai_tools import CareerAssistantQuery
from ai.ai_agent_services.prompts import career_query_prompt
from ai.ai_agent_services.agent_utils import get_assistant_helper_gemini
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async


class CareerAgent(BaseAgent):
    async def get_knowledge_and_prompt(self, user_input: str):
        # Get predefined agents in TOON format (excluding self)
        agents_toon = await self.get_predefined_agents()
        
        # Format the prompt with files and agent list
        formatted_prompt = career_query_prompt.format(
            files=self.filenames,
            agent_list=agents_toon
        )
        
        # Get helper response to classify the query
        helper_response: CareerAssistantQuery = await get_assistant_helper_gemini(
            user_input=user_input,
            system_prompt=formatted_prompt,
            response_format=CareerAssistantQuery
        )
        
        other_agent_response = ""
        other_agent_name = None
        print (helper_response)
        
        # Check if we need to contact another agent
        if helper_response.is_agent_contact_query and helper_response.agent_contact_query:
            other_agent_name = helper_response.agent_contact_query.agent_name
            
            if other_agent_name:
                # Notify user about connecting to another coach
                await self.ws.send_text(
                    json.dumps({
                        "type": "processing",
                        "message": f"Connecting to {other_agent_name}...This may take a few seconds."
                    })
                )
                
                # Call the other agent using the agent_call utility
                other_agent_response = await call_agent_by_name(
                    agent_name=other_agent_name,
                    user_input=user_input,
                    connection_handler=self.connection_handler,
                    chat_history=[]
                )
        
        if other_agent_response:
            await self.ws.send_text(
                json.dumps({
                    "type": "processing",
                    "message": f"Other agent response: {other_agent_response[:50]}...."
                })
            )
        
        # Search user documents only
        result_data = ""
        search_queries = helper_response.user_document_queries
        
        if search_queries and self.file_ids:
            search_query = " ".join(search_queries)
            
            user_data = await get_similarity_search_async(
                vector_store=self.vector_store,
                query=search_query,
                k=3,
                source=True,
                filter=f'user_id == "{self.user_data["sub"]}"',
                file_ids=self.file_ids,
            )
            
            if not isinstance(user_data, Exception):
                result_data = self.normalize_data(user_data)
        
        # Assemble knowledge base
        knowledge_parts = []
        
        if result_data:
            knowledge_parts.append(f"# User Documents:\n{result_data}")
        
        if other_agent_response:
            agent_label = other_agent_name or "Specialized Coach"
            knowledge_parts.append(
                f"# {agent_label} Insights:\n"
                f"The following is expert advice from {agent_label}:\n"
                f"{other_agent_response}"
            )
        
        knowledge_base = "\n\n---\n\n".join(knowledge_parts)
        system_data_prompt = self.system_prompt.format(knowledge_base=knowledge_base)
        
        return knowledge_base, system_data_prompt
