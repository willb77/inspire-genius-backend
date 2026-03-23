import asyncio

from ai.ai_agent_services.agent_services.agents.base_agent import BaseAgent
from ai.ai_agent_services.agent_services.agents.prism_coach_agent import (
    get_coaches_db,
)
from ai.ai_agent_services.agent_utils import get_assistant_helper_gemini
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async


class TrainingAgent(BaseAgent):
    async def get_knowledge_and_prompt(self, user_input: str):
        helper_response = await get_assistant_helper_gemini(user_input)
        search_query = helper_response.refined_query
        
        # Search user's documents using optimized grouping
        user_data_coro = get_similarity_search_async(
            vector_store=self.vector_store,
            query=search_query,
            k=3,
            source=True,
            filter=f'user_id == "{self.user_data["sub"]}"',
            file_ids=self.file_ids,
        )

        prism_data_coro = get_similarity_search_async(
            vector_store=get_coaches_db(),
            query=search_query,
            k=2,
            source=False,
            filter='category == "prism_coach_knowledge"',
        )
        
        user_data, prism_data = await asyncio.gather(
            user_data_coro, prism_data_coro, return_exceptions=True
        )

        # Process user results
        if isinstance(user_data, Exception):
            result_data = ""
        else:
            result_data = self.normalize_data(user_data)

        # Process prism data
        if isinstance(prism_data, Exception):
            prism_data = ""
        else:
            prism_data = self.normalize_data(prism_data)

        knowledge_base = (
            "\n\n# Coach Knowledge:\n"
            + prism_data
            + "\n---\n# User Documents:\n"
            + result_data
        )
        system_data_prompt = self.system_prompt.format(knowledge_base=knowledge_base)

        return knowledge_base, system_data_prompt
