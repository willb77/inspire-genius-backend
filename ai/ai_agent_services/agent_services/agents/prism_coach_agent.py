import asyncio
from datetime import datetime

from ai.ai_agent_services.agent_services.agents.base_agent import BaseAgent
from ai.ai_agent_services.agent_utils import get_assistant_helper_gemini
from ai.ai_agent_services.prompts import prism_query_prompt
from ai.ai_agent_services.ai_tools import PRISMAssistantQuery
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async
from prism_inspire.core.alexvector import get_alex_db
from prism_inspire.core.file_utils import backblaze_handler


def get_coaches_db():
    """Get the Coaches database instance"""
    return get_alex_db()


class PrismCoachAgent(BaseAgent):
    async def get_knowledge_and_prompt(self, user_input: str):
        formatted_prism_query_prompt: str = prism_query_prompt.format(files = self.filenames)
        print("Filenames in PrismCoachAgent:", self.filenames)
        helper_response: PRISMAssistantQuery = await get_assistant_helper_gemini(user_input=user_input, system_prompt=formatted_prism_query_prompt, response_format=PRISMAssistantQuery)
        user_document_search_query = helper_response.user_document_queries
        prism_coach_knowledge_search_query = helper_response.prism_knowledge_queries
        prism_professional_knowledge_search_query = helper_response.prism_coach_professional_knowledge

        result_data_coro = None
        if self.file_ids and user_document_search_query: 
            result_data_coro = get_similarity_search_async(
                vector_store=self.vector_store,
                query=user_document_search_query,       
                k=2,
                source=True,
                filter=f'user_id == "{self.user_data["sub"]}"',
                file_ids=self.file_ids,
                report_str=self.report_str,
            )
        elif self.file_ids:
            result_data = "General PRISM Knowledge only. No user-specific questions."
        else:
            result_data = "No user files selected. inform them to select a file in the coach dashboard in the documents tab."

        # Get coach knowledge
        prism_filter = 'category == "prism_coach_knowledge"'
        coaches_data_coro = get_similarity_search_async(
            vector_store=get_coaches_db(),
            query=prism_coach_knowledge_search_query,
            k=2,
            source=False,
            filter=prism_filter,
        )
        professional_knowledge_filter = 'category == "prism_coach_professional_knowledge"'
        professional_knowledge_data_coro = get_similarity_search_async(
            vector_store=get_coaches_db(),
            query=prism_professional_knowledge_search_query,
            k=2,
            source=False,
            filter=professional_knowledge_filter,
        )

        # Gather results
        if result_data_coro:
            raw_result_data, coaches_data, professional_knowledge_data = await asyncio.gather(
                result_data_coro, coaches_data_coro, professional_knowledge_data_coro, return_exceptions=True
            )
            if isinstance(raw_result_data, Exception):
                result_data = ""
            else:
                result_data = self.normalize_data(raw_result_data)
        else:
            coaches_data, professional_knowledge_data = await asyncio.gather(coaches_data_coro, professional_knowledge_data_coro)

        if isinstance(coaches_data, Exception):
            coaches_data = ""
        else:
            coaches_data = self.normalize_data(coaches_data)

        if isinstance(professional_knowledge_data, Exception):
            professional_knowledge_data = ""
        else:
            professional_knowledge_data = self.normalize_data(professional_knowledge_data)

        knowledge_base = (
            "<INTERNAL_EXPERTISE>\n" 
            "This section contains your training and PRISM theory. Adopt this as your own knowledge.\n\n"
            "**Behaviour Preference Classification:**\n"
            "1. if `score >= 75` → very high behaviour preference\n"
            "2. else if `score >= 65` → natural behaviour preference\n"
            "3. else if `score >= 50` → moderate behaviour preference\n"
            "4. else if `score >= 36` → low-moderate behaviour preference\n"
            "5. else → very low behaviour preference\n"
            + coaches_data
            + "\n"
            + professional_knowledge_data
            + "\n</INTERNAL_EXPERTISE>\n\n"
            
            "<USER_CASE_FILES>\n"
            "This section contains the specific documents, reports, and diaries of the user you are talking to.\n\n"
            + result_data
            + "\n</USER_CASE_FILES>"
        )


        # Format the prompt
        system_data_prompt = self.system_prompt.format(knowledge_base=knowledge_base)

        return knowledge_base, system_data_prompt
