from abc import ABC, abstractmethod


class BaseAgent(ABC):
    @staticmethod
    def normalize_data(data):
        if isinstance(data, list):
            return "\n".join(map(str, data))
        return str(data)

    def __init__(self, connection_handler):
        self.connection_handler = connection_handler
        self.ws = connection_handler.ws
        self.agent_id = connection_handler.agent_id
        self.user_data = connection_handler.user_data
        self.vector_store = connection_handler.vector_store
        self.system_prompt = connection_handler.system_prompt
        self.file_ids = connection_handler.file_ids
        self.accent = connection_handler.accent
        self.tone = connection_handler.tone
        self.voice = connection_handler.voice
        self.report_str = connection_handler.report_str
        self.filenames = connection_handler.filenames
        self.predefined_agents = connection_handler.predefined_agents
        self.mute = False 

    async def get_predefined_agents(self):
        """Get predefined agents in TOON format, excluding self."""
        import toon
        from ai.agent_settings.schema import get_predefined_agents_for_toon
        
        agents = get_predefined_agents_for_toon(exclude_agent_id=self.agent_id)
        self.predefined_agents_toon = toon.encode(agents)
        return self.predefined_agents_toon


    @abstractmethod
    async def get_knowledge_and_prompt(self, user_input: str):
        raise NotImplementedError

    async def handle_special_case(self, user_input: str):
        """Override in child classes for special case handling"""
        return False
