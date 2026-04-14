from ai.ai_agent_services.agent_services.agents.base_agent import BaseAgent
from ai.ai_agent_services.agent_utils import get_assistant_helper_gemini
from ai.file_services.vector_utils.vector_store_func import get_similarity_search_async


class DefaultAgent(BaseAgent):
    async def get_knowledge_and_prompt(self, user_input: str):
        helper_response = await get_assistant_helper_gemini(user_input)
        search_query = helper_response.refined_query

        result_data = await get_similarity_search_async(
            vector_store=self.vector_store,
            query=search_query,
            k=5,
            source=True,
            filter=f'user_id == "{self.user_data["sub"]}"',
            file_ids=self.file_ids if self.file_ids else None,
        )

        knowledge_base = (
            "<DOCUMENT_ACCESS_INSTRUCTIONS>\n"
            "You have FULL access to the user's uploaded documents. The content from their documents "
            "has been retrieved and is provided below. When the user asks about their documents, "
            "reports, or files, reference and quote directly from the content provided. Never say "
            "you cannot see, read, or access their documents.\n"
            "</DOCUMENT_ACCESS_INSTRUCTIONS>\n\n"
            "<USER_CASE_FILES>\n"
            + str(result_data)
            + "\n</USER_CASE_FILES>"
        )
        system_data_prompt = self.system_prompt.format(knowledge_base=knowledge_base)

        return knowledge_base, system_data_prompt
