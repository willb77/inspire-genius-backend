import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ai.ai_agent_services.agent_services.agents.alex_agent import AlexAgent
from ai.ai_agent_services.agent_services.agents.career_agent import CareerAgent
from ai.ai_agent_services.agent_services.agents.default_agent import DefaultAgent
from ai.ai_agent_services.agent_services.agents.prism_coach_agent import PrismCoachAgent
from ai.ai_agent_services.agent_services.agents.training_agent import TrainingAgent
from ai.ai_agent_services.agent_services.handlers.connection_handler import (
    ConnectionHandler,
)
from ai.ai_agent_services.agent_services.handlers.message_handler import MessageHandler
from ai.ai_agent_services.agent_utils import generate_and_stream_gemini_res
from ai.ai_agent_services.prompts import alex_guide_prompt
from ai.chat_services.chat_schema import (
    create_or_update_alex_chat_message,
    get_alex_chat_history_by_device_key,
)
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async
from ai.models.chat import MessageTypeEnum
from prism_inspire.core.alexvector import get_alex_db
from prism_inspire.core.log_config import logger

agent_services = APIRouter(
    prefix="/agents",
    tags=["Agent Services"],
)


def get_agent_logic(agent_id: str, connection_handler: ConnectionHandler):
    if agent_id == "alex":
        return AlexAgent(connection_handler)
    agent = connection_handler.agent
    if agent:
        agent_name = (
            agent.get("name") if hasattr(agent, "get") else getattr(agent, "name", None)
        )
        if agent_name == "PRISM Coach":
            return PrismCoachAgent(connection_handler)
        if agent_name == "Career Coach":
            return CareerAgent(connection_handler)
        if agent_name == "Training Coach":
            return TrainingAgent(connection_handler)
    return DefaultAgent(connection_handler)


def get_alex_db_instance():
    """Get Alex database instance"""
    return get_alex_db()


async def load_alex_history_async(
    device_id: str, chat_history: list, max_history_pairs: int
):
    """Load Alex chat history asynchronously"""
    try:
        stored_messages = get_alex_chat_history_by_device_key(
            device_id, limit=max_history_pairs * 2
        )
        for msg in stored_messages:
            chat_history.append(
                {
                    "role": (
                        "user"
                        if msg.message_type == MessageTypeEnum.user
                        else "assistant"
                    ),
                    "content": [{"type": "text", "text": msg.content}],
                }
            )
    except Exception as e:
        logger.error(f"Error loading Alex chat history: {e}")


async def process_alex_message(
    ws: WebSocket,
    user_input: str,
    chat_history: list,
    alex_db_instance,
    device_id: str,
    max_history_pairs: int,
):
    """Process Alex message with optimized performance"""
    # Add user message to history before generating response
    chat_history.append(
        {"role": "user", "content": [{"type": "text", "text": user_input}]}
    )

    # Save user message asynchronously
    asyncio.create_task(
        save_alex_message_async(device_id, user_input, MessageTypeEnum.user)
    )

    # Maintain history size
    if len(chat_history) > max_history_pairs * 2:
        chat_history = chat_history[-max_history_pairs * 2 :]

    # Use direct search for speed (skip assistant helper)
    alex_context = await get_similarity_search_async(
        vector_store=alex_db_instance,
        query=user_input,  # Direct search for speed
        k=5,
        source=False,
    )

    system_prompt = alex_guide_prompt.format(knowledge_base=alex_context)

    response = await generate_and_stream_gemini_res(
        websocket=ws,
        user_input=user_input,
        system=system_prompt,
        chat_history=chat_history,
    )

    # Add assistant response to history
    chat_history.append(
        {"role": "assistant", "content": [{"type": "text", "text": response}]}
    )

    # Save assistant message asynchronously
    asyncio.create_task(
        save_alex_message_async(device_id, response, MessageTypeEnum.assistant)
    )

    # Maintain history size again
    if len(chat_history) > max_history_pairs * 2:
        chat_history = chat_history[-max_history_pairs * 2 :]


async def save_alex_message_async(
    device_id: str, content: str, message_type: MessageTypeEnum
):
    """Save Alex message asynchronously to not block response"""
    try:
        create_or_update_alex_chat_message(
            device_id, content, message_type=message_type
        )
    except Exception as e:
        logger.error(f"Error saving Alex message: {e}")


@agent_services.websocket("/ws/agents/{agent_id}")
async def agent_chat(ws: WebSocket, agent_id: str):
    await ws.accept()

    connection_handler = ConnectionHandler(ws, agent_id)
    message_handler = None

    try:
        if not await connection_handler.initialize():
            return

        agent_logic = get_agent_logic(agent_id, connection_handler)

        message_handler = MessageHandler(
            ws=ws,
            agent_id=agent_id,
            user_data=connection_handler.user_data,
            conversation=connection_handler.conversation,
            chat_history=connection_handler.chat_history,
            agent_logic=agent_logic,
        )

        while True:
            msg = await ws.receive()
            await message_handler.handle_message(msg)

    except WebSocketDisconnect:
        logger.info(f"[prism-agent-{agent_id}] WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[prism-agent-{agent_id}] Error: {e}")
    finally:
        if message_handler:
            message_handler.cleanup()
        logger.info(f"[prism-agent-{agent_id}] Connection closed.")
