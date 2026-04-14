import asyncio
import json
import uuid

from fastapi import WebSocket
from jose import JWTError

from ai.file_services.schema import get_report_str_for_files, get_filenames_for_files

# Constants
DEFAULT_ACCENT = "US/English"

from ai.agent_settings.schema import (
    get_agent_by_id,
    get_preferences_by_user,
    get_prompts_by_agent_id,
    get_all_agents,
)
from ai.ai_agent_services.agent_utils import get_device_id, get_voice_gender
from ai.chat_services.chat_schema import (
    get_alex_chat_history_by_device_key,
    get_or_create_conversation,
    get_recent_conversation_history,
)
from ai.models.chat import MessageTypeEnum
from prism_inspire.core.log_config import logger
from prism_inspire.core.milvus_client import milvus_client
from users.auth import verify_websocket_token


class ConnectionHandler:
    def __init__(self, ws: WebSocket, agent_id: str):
        self.ws = ws
        self.agent_id = agent_id
        self.predefined_agents = None
        self.user_data = None
        self.agent = None
        self.vector_store = None
        self.system_prompt = ""
        self.file_ids = []
        self.conversation = None
        self.conversation_id = None  # Store conversation_id
        self.chat_history = []
        self.accent = DEFAULT_ACCENT
        self.tone = "Warm"
        self.voice = "coral"
        self.report_str = {}
        self.filenames = ""

    async def initialize(self):
        if self.agent_id == "alex":
            return await self.initialize_alex()
        return await self.initialize_prism_agent()

    async def initialize_alex(self):
        device_id = get_device_id(self.ws)
        self.user_data = {"sub": device_id}
        self.agent = {"name": "alex"}  # Mock agent object

        # Alex doesn't need vector store from users_db, it uses its own alex_db
        # This will be handled by the AlexAgent itself

        # Load chat history in background to not block initialization
        asyncio.create_task(self._load_alex_history_async(device_id))

        await self.ws.send_text(
            json.dumps(
                {
                    "type": "init_success",
                    "message": "Alex initialized successfully",
                    "user_id": device_id,
                }
            )
        )
        return True

    async def _load_alex_history_async(self, device_id: str):
        """Load Alex chat history asynchronously"""
        try:
            stored_messages = get_alex_chat_history_by_device_key(device_id, limit=4)
            for msg in stored_messages:
                self.chat_history.append(
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

    async def initialize_prism_agent(self):
        initial_msg = await self.ws.receive()
        if initial_msg.get("text") is None:
            await self._send_error(
                "init_error", "Expected text message for initialization"
            )
            return False

        initial_payload = json.loads(initial_msg["text"])
        if initial_payload.get("type") != "init":
            await self._send_error(
                "init_error", "Expected init message with access_token and file_ids"
            )
            return False

        if not await self._authenticate(initial_payload.get("access_token")):
            return False

        # Store conversation_id from payload (optional - if not provided, will create new)
        self.conversation_id = initial_payload.get("conversation_id")

        # Run these operations in parallel for faster initialization
        agent_task = self._load_agent_data()
        vector_task = self._connect_vector_store()

        agent_result, vector_result = await asyncio.gather(
            agent_task, vector_task, return_exceptions=True
        )

        if isinstance(agent_result, Exception) or not agent_result:
            if isinstance(agent_result, Exception):
                await self._send_error(
                    "auth_error", f"Failed to get agent: {str(agent_result)}"
                )
            return False

        if isinstance(vector_result, Exception) or not vector_result:
            if isinstance(vector_result, Exception):
                await self._send_error(
                    "auth_error",
                    f"Failed to connect to vector store: {str(vector_result)}",
                )
            return False

        if not await self._load_prompts():
            return False

        # Load predefined agents
        try:
            from ai.agent_settings.schema import get_predefined_agents_for_toon
            self.predefined_agents = get_predefined_agents_for_toon()
        except Exception as e:
            logger.error(f"Error loading predefined agents: {e}")
            self.predefined_agents = []


        # Process file IDs and load preferences in parallel
        file_ids = initial_payload.get("file_ids", [])

        # Auto-load ALL user documents when no specific files are selected
        # so agents always have access to the user's uploaded documents
        if not file_ids:
            try:
                file_ids = await self._get_all_user_file_ids()
                logger.info(
                    f"[prism-agent-{self.agent_id}] No file_ids provided — "
                    f"auto-loaded {len(file_ids)} user documents"
                )
            except Exception as e:
                logger.warning(f"Failed to auto-load user files: {e}")
                file_ids = []

        try:
            self.filenames = await get_filenames_for_files(file_ids, user_id=self.user_data["sub"])
            self.report_str = await get_report_str_for_files(file_ids)
        except Exception as e:
            logger.error(f"Error loading report_str: {e}")
            self.report_str = {}
        prefs_task = asyncio.create_task(self._load_user_preferences_async())

        self._process_file_ids(file_ids)

        # Wait for preferences to complete
        await prefs_task

        if not await self._initialize_conversation():
            return False

        await self.ws.send_text(
            json.dumps(
                {
                    "type": "init_success",
                    "message": f"Prism agent {self.agent_id} initialized successfully",
                    "user_id": self.user_data["sub"],
                    "conversation_id": str(self.conversation.id),
                    "accent": self.accent,
                    "tone": self.tone
                }
            )
        )
        return True

    async def _authenticate(self, access_token):
        if not access_token:
            await self._send_error("auth_error", "Access token is required")
            return False
        try:
            self.user_data = verify_websocket_token(access_token)
            return True
        except JWTError as e:
            await self._send_error("auth_error", f"Authentication failed: {str(e)}")
            return False

    def _process_file_ids(self, file_ids):
        self.file_ids = file_ids
        logger.info(f"[prism-agent-{self.agent_id}] Received file_ids: {self.file_ids}")

    async def _load_agent_data(self):
        try:
            self.agent = get_agent_by_id(self.agent_id)
            if not self.agent:
                await self._send_error(
                    "auth_error", f"Agent not found for ID: {self.agent_id}"
                )
                return False
            return True
        except Exception as e:
            await self._send_error(
                "auth_error", f"Failed to get agent by user ID: {str(e)}"
            )
            return False

    async def _connect_vector_store(self):
        try:
            self.vector_store = milvus_client.get_store("users_db")
            logger.info(
                f"[prism-agent-{self.agent_id}] Connected to Milvus users_db collection"
            )
            return True
        except Exception as e:
            await self._send_error(
                "auth_error", f"Failed to connect to vector store: {str(e)}"
            )
            return False

    async def _load_prompts(self):
        try:
            prompts = get_prompts_by_agent_id(self.agent_id)
            if not prompts:
                await self._send_error(
                    "auth_error", f"No prompts found for agent ID: {self.agent_id}"
                )
                return False
            self.system_prompt = prompts[0].prompt
            return True
        except Exception:
            await self._send_error(
                "auth_error", f"Failed to get prompts for agent ID: {self.agent_id}"
            )
            return False

    async def _load_user_preferences_async(self):
        """Async version of load user preferences"""
        try:
            user_prefs = get_preferences_by_user(self.user_data["sub"], self.agent_id)
            if user_prefs:
                self.accent = (
                    user_prefs[0]["accent"]["name"]
                    if user_prefs[0].get("accent")
                    else DEFAULT_ACCENT
                )
                # Handle multiple tones - join them as comma-separated string
                tones_list = user_prefs[0].get("tones", [])
                if tones_list and len(tones_list) > 0:
                    # Extract tone names and join them
                    tone_names = [tone["name"] for tone in tones_list if tone.get("name")]
                    self.tone = ", ".join(tone_names) if tone_names else "Warm"
                else:
                    self.tone = "Warm"

                gender = (
                    user_prefs[0]["gender"]["name"].lower()
                    if user_prefs[0].get("gender")
                    else "female"
                )
                self.voice = get_voice_gender(gender)
    
        except Exception as e:
            logger.error(f"Error loading user preferences: {e}")
            # Use defaults
            self.accent = DEFAULT_ACCENT
            self.tone = "Warm"
            self.voice = "coral"

    async def _initialize_conversation(self):
        try:
            user_uuid = uuid.UUID(self.user_data["sub"])

            # conversation_id is now REQUIRED - must be obtained from /sessions/start API first
            if not self.conversation_id:
                await self._send_error(
                    "init_error",
                    "conversation_id is required. Please call POST /api/chat/sessions/start first to get a conversation_id"
                )
                return False

            try:
                conversation_uuid = uuid.UUID(self.conversation_id)
                from ai.chat_services.chat_schema import get_conversation_by_id

                self.conversation = get_conversation_by_id(
                    conversation_id=conversation_uuid, user_id=user_uuid
                )

                # Verify the conversation belongs to the correct agent
                if self.conversation and str(self.conversation.agent_id) != self.agent_id:
                    await self._send_error(
                        "auth_error",
                        f"Conversation {self.conversation_id} does not belong to agent {self.agent_id}"
                    )
                    return False

                if not self.conversation:
                    await self._send_error(
                        "auth_error",
                        f"Conversation {self.conversation_id} not found or access denied"
                    )
                    return False

                logger.info(
                    f"[prism-agent-{self.agent_id}] Loaded conversation {self.conversation.id}"
                )
            except ValueError:
                await self._send_error(
                    "auth_error", f"Invalid conversation_id format: {self.conversation_id}"
                )
                return False

            # Load chat history for the conversation
            self.chat_history = get_recent_conversation_history(
                conversation_id=self.conversation.id, user_id=user_uuid, max_pairs=30
            )

            logger.info(
                f"[prism-agent-{self.agent_id}] Loaded {len(self.chat_history)} messages from conversation {self.conversation.id}"
            )
            return True
        except Exception as e:
            logger.error(
                f"[prism-agent-{self.agent_id}] Error initializing conversation: {e}"
            )
            await self._send_error(
                "auth_error", f"Failed to initialize conversation: {str(e)}"
            )
            return False

    async def _get_all_user_file_ids(self) -> list:
        """Fetch all non-deleted file IDs belonging to the current user.

        Used when no specific file_ids are provided in the WebSocket init
        message so that agents can automatically access all user documents.
        """
        from ai.file_services.schema import get_files_by_user_id

        user_id = self.user_data["sub"]
        date_groups = get_files_by_user_id(uuid.UUID(user_id))
        if not date_groups:
            return []

        # date_groups is a list of {"date_label", "date", "files": [file_dicts]}
        all_ids = []
        for group in date_groups:
            for f in group.get("files", []):
                file_id = f.get("id") if isinstance(f, dict) else getattr(f, "id", None)
                if file_id:
                    all_ids.append(str(file_id))
        return all_ids

    async def _send_error(self, error_type, message):
        await self.ws.send_text(json.dumps({"type": error_type, "message": message}))
        await self.ws.close()
