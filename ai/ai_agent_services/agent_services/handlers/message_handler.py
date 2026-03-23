import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime
from ai.audio_services.audio_utils import convert_to_pcm

from fastapi import WebSocket

from ai.ai_agent_services.agent_utils import (
    audio_transcription,
    generate_and_stream_gemini_res,
    generate_and_stream_response,
)
from ai.chat_services.chat_schema import (
    add_message_to_conversation,
    create_or_update_alex_chat_message,
    make_direct_store_callback,
)
from ai.models.chat import AudioTypeEnum, MessageTypeEnum
from prism_inspire.core.log_config import logger


class MessageHandler:
    def __init__(
        self,
        ws: WebSocket,
        agent_id: str,
        user_data: dict,
        conversation: object,
        chat_history: list,
        agent_logic,
    ):
        self.ws = ws
        self.agent_id = agent_id
        self.user_data = user_data
        self.conversation = conversation
        self.chat_history = chat_history
        self.agent_logic = agent_logic
        self.audio_file = None
        self.audio_path = None
        self.max_history_pairs = 2
        self.user_input = ""

    async def handle_message(self, msg: dict):
        if msg.get("bytes") is not None:
            await self._handle_audio_bytes(msg["bytes"])
        elif msg.get("text") is not None:
            payload = json.loads(msg["text"])
            if "mute" in payload:
                await self._set_mute_state(payload["mute"])
                return
            msg_type = payload.get("type")
            if msg_type == "audio_end":
                await self._handle_audio_end()
            elif msg_type == "text":
                self.user_input = payload.get("text", "")
                if hasattr(
                    self.agent_logic, "handle_special_case"
                ) and await self.agent_logic.handle_special_case(self.user_input):
                    return
                await self._handle_text_message(self.user_input)
            elif msg_type == "start_continuous":
                await self._handle_start_continuous()
            elif msg_type == "switch_conversation":
                await self._handle_switch_conversation(payload)
            elif msg_type == "new_conversation":
                await self._handle_new_conversation(payload)
            else:
                await self.ws.send_text(
                    json.dumps(
                        {"type": "error", "message": f"⚠️ Unknown type: {msg_type}"}
                    )
                )

    async def _handle_audio_bytes(self, audio_bytes: bytes):
        if self.audio_file is None:
            # Use a secure named temporary file instead of the insecure tempfile.mktemp
            temp = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
            self.audio_path = temp.name
            self.audio_file = temp
            logger.info(
                f"[prism-agent-{self.agent_id}] Started new audio file: {self.audio_path}"
            )
        # Write and flush incoming audio bytes to the temporary file
        self.audio_file.write(audio_bytes)
        try:
            self.audio_file.flush()
        except Exception:
            # If flushing isn't supported for some file-like objects, ignore
            pass

    async def _set_mute_state(self, mute: bool):
        """Set mute state for the agent"""
        self.agent_logic.mute = mute
        logger.info(f"[prism-agent-{self.agent_id}] Mute set to: {mute}")
        await self.ws.send_text(
            json.dumps({"type": "mute_status", "mute": mute})
        )
        

    async def _handle_audio_end(self):
        if self.audio_file:
            self.audio_file.close()
            logger.info(
                f"[prism-agent-{self.agent_id}] Audio complete: {self.audio_path}"
            )

            await self.ws.send_text(
                json.dumps(
                    {"type": "processing", "message": "Processing your audio..."}
                )
            )

            self.user_input = await audio_transcription(self.audio_path)
            logger.info(f"[prism-agent-{self.agent_id}] Transcript: {self.user_input}")

            await self.ws.send_text(
                json.dumps({"type": "transcript", "text": self.user_input})
            )

            try:
                # read raw bytes
                with open(self.audio_path, "rb") as f:
                    raw_bytes = f.read()

                try:
                    pcm_bytes = await convert_to_pcm(raw_bytes, sample_rate=16000, channels=1)
                except Exception as e:
                    logger.exception("convert_to_pcm failed; saving original bytes")
                    pcm_bytes = raw_bytes

                utc_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                audio_filename = f"{utc_ts}.pcm"

                add_message_to_conversation(
                    conversation_id=self.conversation.id,
                    user_id=uuid.UUID(self.user_data["sub"]),
                    content=self.user_input,
                    message_type=MessageTypeEnum.user,
                    audio_bytes=pcm_bytes,
                    audio_filename=audio_filename,
                    audio_type=AudioTypeEnum.user_voice,
                )

                logger.info(f"[prism-agent-{self.agent_id}] Saved user audio message (queued background upload)")

            except Exception:
                logger.exception("[prism-agent-%s] Failed saving user audio message", self.agent_id)

            await self._process_and_respond(self.user_input, is_audio=True)

            try:
                os.remove(self.audio_path)
            except Exception as e:
                logger.error(f"Error removing audio file {self.audio_path}: {e}")
            self.audio_file = None
            self.audio_path = None
        else:
            await self.ws.send_text(
                json.dumps({"type": "error", "message": "⚠️ No active audio to end"})
            )

    async def _handle_text_message(self, text: str):
        logger.info(f"[prism-agent-{self.agent_id}] Chat text: {text}")

        # Send immediate thinking message
        await self.ws.send_text(
            json.dumps({"type": "processing", "message": "Thinking..."})
        )

        # Process asynchronously to avoid blocking
        await self._process_and_respond(text)

    async def _process_and_respond(self, user_input: str, is_audio: bool = False):
        
        if not is_audio:
            asyncio.create_task(self._save_user_message_async(user_input, is_audio))
        else:
            logger.info(f"[prism-agent-{self.agent_id}] Skipping duplicate user save for audio input")
        _, system_data_prompt = await self.agent_logic.get_knowledge_and_prompt(user_input)
        save_cb = make_direct_store_callback(self.conversation.id, uuid.UUID(self.user_data["sub"]))

        response_text, audio_bytes, audio_filename = await generate_and_stream_response(
            websocket=self.ws,
            user_input=user_input,
            system=system_data_prompt,
            chat_history=self.chat_history,
            accent=self.agent_logic.accent,
            tone=self.agent_logic.tone,
            voice=self.agent_logic.voice,
            save_callback=save_cb
        )

        # Add to chat history
        self.chat_history.append(
            {"role": "assistant", "content": [{"type": "text", "text": response_text}]}
        )
        self._maintain_history_size()


    async def _save_user_message_async(self, content: str, is_audio: bool):
        """Async version of save user message to avoid blocking"""
        try:
            if is_audio:
                logger.info(f"[prism-agent-{self.agent_id}] _save_user_message_async: skipping duplicate save for audio input")
                return

            if self.agent_id == "alex":
                create_or_update_alex_chat_message(
                    self.user_data["sub"], content, message_type=MessageTypeEnum.user
                )
            else:
                add_message_to_conversation(
                    conversation_id=self.conversation.id,
                    user_id=uuid.UUID(self.user_data["sub"]),
                    content=content,
                    message_type=MessageTypeEnum.user,
                    audio_s3_key=None,
                    audio_type=AudioTypeEnum.user_voice if is_audio else None,
                )
            logger.info(f"[prism-agent-{self.agent_id}] Saved user message.")
        except Exception as e:
            logger.error(
                f"[prism-agent-{self.agent_id}] Error saving user message: {e}"
            )

    async def _save_assistant_message_async(self, content: str, audio_bytes: bytes = None, audio_filename: str = None):
        """Async version of save assistant message to avoid blocking"""
        try:
            if self.agent_id == "alex":
                create_or_update_alex_chat_message(
                    self.user_data["sub"],
                    content,
                    message_type=MessageTypeEnum.assistant,
                )
            else:
                add_message_to_conversation(
                    conversation_id=self.conversation.id,
                    user_id=uuid.UUID(self.user_data["sub"]),
                    content=content,
                    message_type=MessageTypeEnum.assistant,
                    audio_bytes=audio_bytes,
                    audio_filename=audio_filename,
                    audio_type=AudioTypeEnum.assistant_voice if audio_bytes else None,
                )
            logger.info(f"[prism-agent-{self.agent_id}] Saved assistant message.")
        except Exception as e:
            logger.error(
                f"[prism-agent-{self.agent_id}] Error saving assistant message: {e}"
            )

    def _save_user_message(self, content: str, is_audio: bool):
        try:
            if is_audio:
                logger.info(f"[prism-agent-{self.agent_id}] _save_user_message: skipping duplicate save for audio input")
                return

            if self.agent_id == "alex":
                create_or_update_alex_chat_message(
                    self.user_data["sub"], content, message_type=MessageTypeEnum.user
                )
            else:
                add_message_to_conversation(
                    conversation_id=self.conversation.id,
                    user_id=uuid.UUID(self.user_data["sub"]),
                    content=content,
                    message_type=MessageTypeEnum.user,
                    audio_s3_key=None,  # Assuming S3 key handling is separate
                    audio_type=AudioTypeEnum.user_voice if is_audio else None,
                )
            logger.info(f"[prism-agent-{self.agent_id}] Saved user message.")
        except Exception as e:
            logger.error(
                f"[prism-agent-{self.agent_id}] Error saving user message: {e}"
            )

    def _save_assistant_message(self, content: str, audio_bytes: bytes = None, audio_filename: str = None):
        try:
            if self.agent_id == "alex":
                create_or_update_alex_chat_message(
                    self.user_data["sub"],
                    content,
                    message_type=MessageTypeEnum.assistant,
                )
            else:
                add_message_to_conversation(
                    conversation_id=self.conversation.id,
                    user_id=uuid.UUID(self.user_data["sub"]),
                    content=content,
                    message_type=MessageTypeEnum.assistant,
                    audio_bytes=audio_bytes,
                    audio_filename=audio_filename,
                    audio_type=AudioTypeEnum.assistant_voice if audio_bytes else None,
                )
            logger.info(f"[prism-agent-{self.agent_id}] Saved assistant message.")
        except Exception as e:
            logger.error(
                f"[prism-agent-{self.agent_id}] Error saving assistant message: {e}"
            )

    def _maintain_history_size(self):
        if len(self.chat_history) > self.max_history_pairs * 2:
            self.chat_history = self.chat_history[-self.max_history_pairs * 2 :]

    async def _handle_start_continuous(self):
        await self.ws.send_text(
            json.dumps(
                {
                    "type": "continuous_mode",
                    "status": "active",
                    "message": f"Continuous streaming mode activated for agent {self.agent_id}. I'm ready to respond instantly!",
                }
            )
        )

    async def _handle_switch_conversation(self, payload: dict):
        """Switch to a different existing conversation."""
        try:
            if self.agent_id == "alex":
                await self.ws.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "Alex does not support conversation switching"
                    })
                )
                return

            conversation_id = payload.get("conversation_id")
            if not conversation_id:
                await self.ws.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "conversation_id is required"
                    })
                )
                return

            user_uuid = uuid.UUID(self.user_data["sub"])
            conversation_uuid = uuid.UUID(conversation_id)

            from ai.chat_services.chat_schema import get_conversation_by_id, get_recent_conversation_history

            # Load the conversation
            conversation = get_conversation_by_id(
                conversation_id=conversation_uuid,
                user_id=user_uuid
            )

            if not conversation:
                await self.ws.send_text(
                    json.dumps({
                        "type": "error",
                        "message": f"Conversation {conversation_id} not found or access denied"
                    })
                )
                return

            # Verify it belongs to the same agent
            if str(conversation.agent_id) != self.agent_id:
                await self.ws.send_text(
                    json.dumps({
                        "type": "error",
                        "message": f"Conversation {conversation_id} belongs to a different agent"
                    })
                )
                return

            # Switch to the new conversation
            self.conversation = conversation
            self.chat_history = get_recent_conversation_history(
                conversation_id=conversation.id,
                user_id=user_uuid,
                max_pairs=self.max_history_pairs
            )

            logger.info(
                f"[prism-agent-{self.agent_id}] Switched to conversation {conversation.id}"
            )

            await self.ws.send_text(
                json.dumps({
                    "type": "conversation_switched",
                    "conversation_id": str(conversation.id),
                    "title": conversation.title if conversation.title else "New Conversation",
                    "message_count": conversation.message_count,
                    "message": f"Switched to conversation: {conversation.title if conversation.title else 'New Conversation'}"
                })
            )

        except ValueError as e:
            await self.ws.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"Invalid conversation_id format: {str(e)}"
                })
            )
        except Exception as e:
            logger.error(f"Error switching conversation: {e}")
            await self.ws.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"Failed to switch conversation: {str(e)}"
                })
            )

    async def _handle_new_conversation(self, payload: dict):
        """Create and switch to a new conversation."""
        try:
            if self.agent_id == "alex":
                await self.ws.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "Alex does not support multiple conversations"
                    })
                )
                return

            user_uuid = uuid.UUID(self.user_data["sub"])
            agent_uuid = uuid.UUID(self.agent_id)
            title = payload.get("title")  # Optional title

            from ai.chat_services.chat_schema import start_new_conversation

            # Create new conversation
            conversation = start_new_conversation(
                user_id=user_uuid,
                agent_id=agent_uuid,
                title=title
            )

            if not conversation:
                await self.ws.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "Failed to create new conversation"
                    })
                )
                return

            # Switch to the new conversation
            self.conversation = conversation
            self.chat_history = []  # New conversation has no history

            logger.info(
                f"[prism-agent-{self.agent_id}] Created and switched to new conversation {conversation.id}"
            )

            await self.ws.send_text(
                json.dumps({
                    "type": "conversation_created",
                    "conversation_id": str(conversation.id),
                    "title": conversation.title if conversation.title else "New Conversation",
                    "message": f"Started new conversation: {conversation.title if conversation.title else 'New Conversation'}"
                })
            )

        except Exception as e:
            logger.error(f"Error creating new conversation: {e}")
            await self.ws.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"Failed to create new conversation: {str(e)}"
                })
            )

    def cleanup(self):
        if self.audio_file:
            self.audio_file.close()
            logger.info(f"[prism-agent-{self.agent_id}] Closed leftover audio file")
        if self.audio_path and os.path.exists(self.audio_path):
            try:
                os.remove(self.audio_path)
            except Exception as e:
                logger.error(
                    f"Error removing audio file during cleanup {self.audio_path}: {e}"
                )
