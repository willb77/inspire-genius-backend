import json

from ai.ai_agent_services.agent_services.agents.base_agent import BaseAgent
from ai.ai_agent_services.agent_utils import (
    get_assistant_helper_gemini,
    stream_gemini_audio,
)
from ai.ai_agent_services.prompts import alex_guide_prompt, alex_read_dict
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async
from prism_inspire.core.alexvector import get_alex_db


class AlexAgent(BaseAgent):
    def __init__(self, connection_handler):
        super().__init__(connection_handler)
        self.alex_db_instance = get_alex_db()
        # Override vector_store for Alex to use its own DB
        self.vector_store = self.alex_db_instance
        # Alex doesn't need these but initialize to avoid errors
        self.accent = "US/English"
        self.tone = "Warm"

    async def get_knowledge_and_prompt(self, user_input: str):
        if user_input in alex_read_dict:
            # This is a special case for pre-defined responses
            return None, None

        helper_response = await get_assistant_helper_gemini(user_input)
        # refined_query is a list, so we need to join them or use the first one
        search_query = (
            " ".join(helper_response.refined_query)
            if helper_response.refined_query
            else user_input
        )

        filter_expr = 'category == "alex_knowledge"'
        alex_context = await get_similarity_search_async(
            vector_store=self.alex_db_instance,
            query=search_query,
            k=5,
            source=False,
            filter=filter_expr,
        )

        system_prompt = alex_guide_prompt.format(knowledge_base=alex_context)
        return alex_context, system_prompt

    async def handle_special_case(self, user_input: str):
        if user_input in alex_read_dict:
            value = alex_read_dict[user_input]
            await self.ws.send_text(
                json.dumps(
                    {
                        "type": "response",
                        "text": value,
                    }
                )
            )
            await self.ws.send_text(
                json.dumps({"type": "audio_start", "format": "pcm"})
            )
            await stream_gemini_audio(websocket=self.ws, sentence=value)
            await self.ws.send_text(json.dumps({"type": "audio_complete"}))
            return True
        return False
