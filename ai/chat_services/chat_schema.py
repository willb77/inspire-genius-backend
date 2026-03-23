import uuid, asyncio, os, threading
from datetime import timedelta, datetime

from botocore.exceptions import BotoCoreError, ClientError
import boto3
from typing import Optional, Callable, Awaitable
from sqlalchemy import and_, desc, func

from ai.models.chat import (
    AlexChatMessage,
    AudioTypeEnum,
    ChatMessage,
    Conversation,
    ConversationStatusEnum,
    MessageStatusEnum,
    MessageTypeEnum,
)
from ai.chat_services.title_generator import generate_conversation_title, should_generate_title
from ai.file_services.vector_utils.parent_store import get_next_snowflake
from prism_inspire.core.log_config import logger
from prism_inspire.db.session import ScopedSession


def create_conversation(data):
    """Create a new conversation for a user."""
    try:
        session = ScopedSession()
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=data["user_id"],
            agent_id=data.get("agent_id"),
            title=data.get("title"),
            status=ConversationStatusEnum.active,
            message_count=0,
        )
        session.add(conversation)
        session.commit()
        logger.info(
            f"Created conversation {conversation.id} for user {data['user_id']}"
        )
        return conversation
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating conversation: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()

def get_user_conversations(
    user_id, limit=50, offset=0, include_deleted=False, agent_id=None, search=None
):
    """Get all conversations for a user with optional title search."""
    try:
        session = ScopedSession()
        query = session.query(Conversation).filter(Conversation.user_id == user_id)

        if not include_deleted:
            query = query.filter(Conversation.is_deleted == False)

        if agent_id is not None:
            query = query.filter(Conversation.agent_id == agent_id)

        if search:
            query = query.filter(Conversation.title.ilike(f"%{search}%"))

        conversations = (
            query.order_by(desc(Conversation.updated_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return conversations
    except Exception as e:
        logger.error(f"Error fetching conversations for user {user_id}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def get_conversation_by_id(conversation_id, user_id):
    """Get a specific conversation by ID for a user."""
    try:
        session = ScopedSession()
        conversation = (
            session.query(Conversation)
            .filter(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.is_deleted == False,
                )
            )
            .first()
        )
        return conversation
    except Exception as e:
        logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_or_create_conversation(user_id, agent_id=None):
    """Get the most recent active conversation or create a new one."""
    try:
        session = ScopedSession()
        # Try to get the most recent active conversation
        conversation = (
            session.query(Conversation)
            .filter(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.agent_id == agent_id,
                    Conversation.status == ConversationStatusEnum.active,
                    Conversation.is_deleted == False,
                )
            )
            .order_by(desc(Conversation.updated_at))
            .first()
        )

        if conversation:
            return conversation

        # Create a new conversation if none found
        session.close()
        ScopedSession.remove()
        return create_conversation({"user_id": user_id, "agent_id": agent_id})

    except Exception as e:
        logger.error(f"Error getting or creating conversation: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def start_new_conversation(user_id, agent_id=None, title=None):
    """
    Explicitly start a new conversation for a user with an agent.
    Unlike get_or_create_conversation, this ALWAYS creates a new conversation.
    """
    try:
        # Don't set a default title - let it be auto-generated from first message
        # Only use title if explicitly provided by user
        return create_conversation({
            "user_id": user_id,
            "agent_id": agent_id,
            "title": title
        })
    except Exception as e:
        logger.error(f"Error starting new conversation: {e}")
        return None

def _write_file_sync(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


async def _store_audio_background(message_id, conversation_id, audio_bytes: bytes, filename: str):
    session = None
    try:
        # defensive checks
        if not audio_bytes:
            logger.warning("_store_audio_background: no audio_bytes for message %s", message_id)
            return

        bucket = os.environ.get("S3_BUCKET") or os.environ.get("S3_BUCKET_NAME")
        if not bucket:
            logger.error("_store_audio_background: S3_BUCKET not set in env")
            return

        utc_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        snow_id = str(get_next_snowflake())

        lookup_session = None
        try:
            lookup_session = ScopedSession()
            msg_for_prefix = lookup_session.query(ChatMessage).filter(ChatMessage.id == message_id).first()
            if msg_for_prefix and msg_for_prefix.message_type == MessageTypeEnum.assistant:
                prefix = "A"
            else:
                prefix = "U"
        except Exception:
            logger.exception("Failed to determine message type for prefix, defaulting to 'U' for message %s", message_id)
            prefix = "U"
        finally:
            if lookup_session:
                lookup_session.close()
                ScopedSession.remove()

        # ensure filename and extension
        if not filename:
            filename = f"{utc_ts}.pcm"
        else:
            filename = os.path.basename(filename)
            if not filename.lower().endswith((".pcm", ".wav")):
                filename = f"{filename}.pcm"

        key = f"{prefix}{snow_id}_{utc_ts}"

        loop = asyncio.get_running_loop()
        s3_client = boto3.client("s3")

        # determine content type
        content_type = "audio/pcm" if filename.lower().endswith(".pcm") else "audio/wav" if filename.lower().endswith(".wav") else "application/octet-stream"
        metadata = {"original_filename": filename, "sample_rate": os.environ.get("DEFAULT_AUDIO_SR", "16000"), "channels": os.environ.get("DEFAULT_AUDIO_CHANNELS", "1")}

        def _upload_sync():
            s3_client.put_object(Bucket=bucket, Key=key, Body=audio_bytes, ContentType=content_type, Metadata=metadata)

        await loop.run_in_executor(None, _upload_sync)
        logger.info("Uploaded audio for message %s to s3://%s/%s (ContentType=%s)", message_id, bucket, key, content_type)

        # update DB row with s3 key
        session = ScopedSession()
        try:
            msg = session.query(ChatMessage).filter(ChatMessage.id == message_id).first()
            if msg:
                # only set if not already set (avoid accidental overwrites)
                if not msg.audio_s3_key:
                    msg.audio_s3_key = key
                    msg.has_audio = True
                    session.commit()
                    logger.info("Updated ChatMessage %s with audio_s3_key=%s", message_id, key)
                else:
                    logger.info("ChatMessage %s already has audio_s3_key=%s, skipping DB update", message_id, msg.audio_s3_key)
            else:
                logger.warning("ChatMessage %s not found for DB update", message_id)
        except Exception:
            session.rollback()
            logger.exception("Failed updating DB for message %s", message_id)
        finally:
            session.close()
            ScopedSession.remove()

    except Exception:
        logger.exception("_store_audio_background failed for message_id=%s", message_id)
    finally:
        if session:
            try:
                session.close()
                ScopedSession.remove()
            except Exception:
                pass


def _schedule_background_coro(coro, *args):
    """
    Schedule background coroutine without blocking caller.
    If an asyncio loop is running, create_task; otherwise run coro in a daemon thread.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro(*args))
    except RuntimeError:
        def _runner():
            try:
                asyncio.run(coro(*args))
            except Exception:
                logger.exception("Background audio runner failed in thread")
        t = threading.Thread(target=_runner, daemon=True)
        t.start()


def add_message_to_conversation(
    conversation_id,
    user_id,
    content,
    message_type,
    audio_s3_key=None,
    audio_type=None,
    audio_duration=None,
    model_used=None,
    tokens_used=None,
    response_time_ms=None,
    audio_bytes: bytes = None,
    audio_filename: str = None,
):
    """Add a new message to a conversation."""
    try:
        session = ScopedSession()

        # Get the next sequence number
        last_message = (
            session.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation_id)
            .order_by(desc(ChatMessage.sequence_number))
            .first()
        )

        sequence_number = (last_message.sequence_number + 1) if last_message else 1

        # Create the message
        message = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            message_type=message_type,
            content=content,
            audio_s3_key=audio_s3_key,
            audio_type=audio_type,
            audio_duration=audio_duration,
            has_audio=bool(audio_s3_key),
            status=MessageStatusEnum.sent,
            word_count=len(content.split()) if content else 0,
            character_count=len(content) if content else 0,
            response_time_ms=response_time_ms,
            model_used=model_used,
            tokens_used=tokens_used,
            sequence_number=sequence_number,
        )

        session.add(message)

        # Update conversation metadata
        conversation = (
            session.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )

        if conversation:
            conversation.message_count = (conversation.message_count or 0) + 1
            conversation.last_message_at = message.created_at

            # Auto-generate title from first user message
            if (message_type == MessageTypeEnum.user and
                should_generate_title(conversation.message_count, conversation.title)):
                generated_title = generate_conversation_title(content)
                conversation.title = generated_title
                logger.info(f"Auto-generated title for conversation {conversation_id}: {generated_title}")

        session.commit()

        logger.info(f"Added message {message.id} to conversation {conversation_id}")

        if audio_bytes and audio_filename and not audio_s3_key:
            _schedule_background_coro(_store_audio_background, message.id, conversation_id, audio_bytes, audio_filename)

        return message
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding message to conversation: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_recent_conversation_history(conversation_id, user_id, max_pairs=5, start_date=None, end_date=None):
    """Get recent conversation history formatted for AI context with optional date range filtering."""
    try:
        session = ScopedSession()

        # Verify user has access to this conversation
        conversation = (
            session.query(Conversation)
            .filter(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.is_deleted == False,
                )
            )
            .first()
        )

        if not conversation:
            return []

        query = session.query(ChatMessage).filter(
            and_(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.is_deleted == False,
            )
        )

        # Add date range filtering if provided
        if start_date:
            query = query.filter(ChatMessage.created_at >= start_date)
        if end_date:
            # If end_date has time component as 00:00:00, add 1 day and subtract 1 second to include entire day
            if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
                end_date = end_date + timedelta(days=1, seconds=-1)
            query = query.filter(ChatMessage.created_at <= end_date)

        messages = (
            query
            .order_by(ChatMessage.sequence_number)
            .limit(max_pairs * 2)
            .all()
        )

        # Convert to AI format
        history = []
        for message in messages[-max_pairs * 2 :]:  # Get last N pairs
            role = (
                "user" if message.message_type == MessageTypeEnum.user else "assistant"
            )
            history.append(
                {
                    "role": role,
                    "content": [{"type": "text", "text": message.content}],
                    "timestamp": (
                        message.created_at.isoformat() if message.created_at else None
                    ),
                }
            )

        return history
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def soft_delete_conversation(conversation_id, user_id):
    """Soft delete a conversation."""
    try:
        session = ScopedSession()
        conversation = (
            session.query(Conversation)
            .filter(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.is_deleted == False,
                )
            )
            .first()
        )

        if not conversation:
            return False

        conversation.is_deleted = True
        conversation.status = ConversationStatusEnum.archived
        session.commit()

        logger.info(f"Soft deleted conversation {conversation_id}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting conversation {conversation_id}: {e}")
        return False
    finally:
        session.close()
        ScopedSession.remove()


def update_conversation_title(conversation_id, user_id, title):
    """Update the title of a conversation."""
    try:
        session = ScopedSession()
        conversation = (
            session.query(Conversation)
            .filter(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.is_deleted == False,
                )
            )
            .first()
        )

        if not conversation:
            return None

        conversation.title = title
        session.commit()

        # Refresh to load all attributes before closing session
        session.refresh(conversation)

        logger.info(f"Updated title for conversation {conversation_id} to '{title}'")
        return conversation
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating conversation {conversation_id}: {e}")
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_alex_chat_history_by_device_key(device_key, limit=100, offset=0, start_date=None, end_date=None):
    """Get Alex chat history by device key with optional date range filtering."""
    try:
        session = ScopedSession()

        query = session.query(AlexChatMessage).filter(AlexChatMessage.device_key == device_key)

        # Add date range filtering if provided
        if start_date:
            logger.info(f"Filtering messages >= {start_date}")
            query = query.filter(AlexChatMessage.created_at >= start_date)
        if end_date:
            # If end_date has time component as 00:00:00, add 1 day and subtract 1 second to include entire day
            if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
                end_date = end_date + timedelta(days=1, seconds=-1)
            logger.info(f"Filtering messages <= {end_date}")
            query = query.filter(AlexChatMessage.created_at <= end_date)

        messages = (
            query
            .order_by(desc(AlexChatMessage.sequence_number))
            .offset(offset)
            .limit(limit)
            .all()
        )

        logger.info(
            f"Retrieved {len(messages)} Alex chat messages for device {device_key} (start_date: {start_date}, end_date: {end_date})"
        )
        if messages:
            logger.info(f"First message date: {messages[0].created_at}, Last message date: {messages[-1].created_at}")
        return messages
    except Exception as e:
        logger.error(f"Error fetching Alex chat history for device {device_key}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def create_or_update_alex_chat_message(
    device_key, content, message_type=MessageTypeEnum.user, message_id=None
):
    """Create a new Alex chat message or update an existing one by device key."""
    try:
        session = ScopedSession()

        if message_id:
            # Update existing message
            message = (
                session.query(AlexChatMessage)
                .filter(
                    and_(
                        AlexChatMessage.id == message_id,
                        AlexChatMessage.device_key == device_key,
                    )
                )
                .first()
            )

            if message:
                message.content = content
                message.message_type = message_type
                session.commit()
                logger.info(
                    f"Updated Alex chat message {message_id} for device {device_key}"
                )
                return message
            else:
                logger.warning(
                    f"Alex chat message {message_id} not found for device {device_key}"
                )
                return None
        else:
            last_seq = (
                session.query(func.max(AlexChatMessage.sequence_number))
                .filter_by(device_key=device_key)
                .scalar()
            )
            next_seq = (last_seq or 0) + 1
            # Create new message
            message = AlexChatMessage(
                id=uuid.uuid4(),
                device_key=device_key,
                content=content,
                message_type=message_type,
                sequence_number=next_seq,
            )

            session.add(message)
            session.commit()

            logger.info(
                f"Created new Alex chat message {message.id} for device {device_key}"
            )
            return message

    except Exception as e:
        session.rollback()
        logger.error(
            f"Error creating/updating Alex chat message for device {device_key}: {e}"
        )
        return None
    finally:
        session.close()
        ScopedSession.remove()


def get_conversation_messages(conversation_id, user_id, limit=100, offset=0, start_date=None, end_date=None):
    """Get messages from a conversation with optional date range filtering."""
    try:
        session = ScopedSession()

        # Verify user has access to this conversation
        conversation = session.query(Conversation).filter(
            and_(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted == False
            )
        ).first()

        if not conversation:
            return []

        query = session.query(ChatMessage).filter(
            and_(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.is_deleted == False
            )
        )

        # Add date range filtering if provided
        if start_date:
            query = query.filter(ChatMessage.created_at >= start_date)
        if end_date:
            query = query.filter(ChatMessage.created_at <= end_date)

        messages = query.order_by(ChatMessage.sequence_number).offset(offset).limit(limit).all()

        return messages
    except Exception as e:
        logger.error(f"Error fetching messages for conversation {conversation_id}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()

def get_conversation_messages_loadmore(conversation_id, user_id, limit=100, offset=0, start_date=None, end_date=None):
    """Get messages from a conversation in descending order (newest first) for load-more functionality."""
    try:
        session = ScopedSession()

        # Verify user has access to this conversation
        conversation = session.query(Conversation).filter(
            and_(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
                Conversation.is_deleted == False
            )
        ).first()

        if not conversation:
            return []

        query = session.query(ChatMessage).filter(
            and_(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.is_deleted == False
            )
        )

        # Add date range filtering if provided
        if start_date:
            query = query.filter(ChatMessage.created_at >= start_date)
        if end_date:
            query = query.filter(ChatMessage.created_at <= end_date)

        # Order by descending sequence number (newest first) for load-more
        messages = query.order_by(ChatMessage.sequence_number.desc()).offset(offset).limit(limit).all()

        return messages
    except Exception as e:
        logger.error(f"Error fetching messages (loadmore) for conversation {conversation_id}: {e}")
        return []
    finally:
        session.close()
        ScopedSession.remove()


def make_direct_store_callback(conversation_id, user_id) -> Callable[[str, Optional[bytes], Optional[str]], Awaitable[None]]:
    """
    Async callback used by generate_and_stream_response:
      async def cb(response_text, audio_bytes, audio_filename)
    Creates a DB message and schedules the existing _store_audio_background uploader.
    """
    async def _cb(response_text: str, audio_bytes: Optional[bytes], audio_filename: Optional[str]):
        try:
            # create message row first (synchronous). This will not block audio streaming.
            msg = add_message_to_conversation(
                conversation_id=conversation_id,
                user_id=user_id,
                content=response_text,
                message_type=MessageTypeEnum.assistant,
                audio_bytes=audio_bytes,
                audio_filename=audio_filename,
                audio_type=AudioTypeEnum.assistant_voice if audio_bytes else None,
            )
            if msg:
                logger.info("Created message %s (background store handled by add_message_to_conversation if audio present)", msg.id)
        except Exception as e:
            logger.exception("Error in save_audio_callback: %s", e)

    return _cb