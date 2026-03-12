"""
Simple conversation title generator based on first user message.
"""

from prism_inspire.core.log_config import logger


def generate_conversation_title(first_message_content: str, max_length: int = 50) -> str:
    """
    Generate a conversation title from the first user message by truncating it.

    Args:
        first_message_content: The content of the first user message
        max_length: Maximum length of the title (default: 50 characters)

    Returns:
        A truncated title based on the first message
    """
    if not first_message_content:
        return "New Conversation"

    try:
        # Clean the message content
        title = first_message_content.strip()

        # Replace newlines with spaces
        title = " ".join(title.split())

        # Truncate if needed
        if len(title) > max_length:
            # Try to truncate at a word boundary
            title = title[:max_length].rsplit(' ', 1)[0] + "..."

        logger.info(f"Generated conversation title: {title}")
        return title

    except Exception as e:
        logger.error(f"Error generating conversation title: {e}")
        return "New Conversation"


def should_generate_title(conversation_message_count: int, current_title: str = None) -> bool:
    """
    Determine if a title should be generated for a conversation.

    Args:
        conversation_message_count: Current number of messages in the conversation
        current_title: Current title of the conversation

    Returns:
        True if title should be generated (on first message if no title or default title)
    """
    # Generate title on first message if there's no custom title
    if conversation_message_count == 1:
        if not current_title or current_title.startswith("Chat ") or current_title == "No Title":
            return True
    return False
