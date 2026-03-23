import base64
import json
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from typing import Optional
from fastapi import Response
from uuid import UUID

import markdown2
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi_utils.cbv import cbv
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

from ai.ai_agent_services.agent_utils import get_device_id
from ai.chat_services.chat_models import (
    CreateConversationRequest,
    MessageListResponse,
    MessageResponse,
    StartSessionRequest,
    StartSessionResponse,
    UpdateConversationRequest,
)
from ai.chat_services.chat_schema import (
    create_conversation,
    get_alex_chat_history_by_device_key,
    get_conversation_by_id,
    get_conversation_messages,
    get_conversation_messages_loadmore,
    get_recent_conversation_history,
    get_user_conversations,
    soft_delete_conversation,
    start_new_conversation,
    update_conversation_title,
)
from ai.models.chat import MessageTypeEnum
from prism_inspire.core.log_config import logger
from users.auth import verify_token
from users.response import (
    NOT_FOUND,
    SOMETHING_WENT_WRONG,
    SUCCESS_CODE,
    create_response,
)

UNKNOW_DATE = "Unknown Date"

chat_routes = APIRouter(
    prefix="/chat",
    tags=["Chat Management"],
)

went_wrong = "Something went wrong, please try again later"


class ConversationPDFBuilder:
    def __init__(self, conversation_id, history, start_date=None, end_date=None, timezone="UTC"):
        self.conversation_id = conversation_id
        self.history = history
        self.start_date = start_date
        self.end_date = end_date
        self.timezone = timezone
        self.styles = self._get_chat_styles()

    def build_base64_pdf(self):
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
            title=f"Alex Chat Export - {self.conversation_id}",
        )

        try:
            sorted_dates = self._group_history()
            content = []

            # Add date filter header if filters are applied
            logger.info(f"PDF Builder - start_date: {self.start_date}, end_date: {self.end_date}")
            if self.start_date or self.end_date:
                filter_text = "Date Filter Applied: "
                if self.start_date and self.end_date:
                    filter_text += f"{self.start_date.strftime('%B %d, %Y')} to {self.end_date.strftime('%B %d, %Y')}"
                elif self.start_date:
                    filter_text += f"From {self.start_date.strftime('%B %d, %Y')}"
                elif self.end_date:
                    filter_text += f"Until {self.end_date.strftime('%B %d, %Y')}"

                content.append(Paragraph(filter_text, self.styles["filter_header"]))
                content.append(Spacer(1, 0.3 * inch))

            # Handle empty chat
            if not sorted_dates or not any(messages for _, messages in sorted_dates):
                content.append(Spacer(1, 2 * inch))
                content.append(
                    Paragraph("💬 Chat Export", self.styles["date"])
                )
                content.append(Spacer(1, 0.5 * inch))
                content.append(
                    Paragraph(
                        "No active messages were found for the selected date range.",
                        self.styles["assistant"],
                    )
                )
                content.append(Spacer(1, 0.2 * inch))
                content.append(
                    Paragraph(
                        "Please try again with a different date range or ensure that the conversation has active messages.",
                        self.styles["meta"],
                    )
                )
                doc.build(content)
                pdf_buffer.seek(0)
                pdf_bytes = pdf_buffer.read()
                return base64.b64encode(pdf_bytes).decode("utf-8")

            # Build normal chat content
            for idx, (date_str, messages) in enumerate(sorted_dates):
                content.append(Paragraph(date_str, self.styles["date"]))
                try:
                    message_blocks = self._build_message_blocks(messages)
                    content.extend(message_blocks)
                except Exception as e:
                    logger.warning(f"Error processing messages for date {date_str}: {e}")
                    error_msg = (
                        f"Error rendering messages for {date_str}. Some content may be missing."
                    )
                    content.append(Paragraph(error_msg, self.styles["meta"]))

                if idx < len(sorted_dates) - 1:
                    content.append(Paragraph("***", self.styles["separator"]))

            # Finalize and build valid PDF
            doc.build(content)
            pdf_buffer.seek(0)
            pdf_bytes = pdf_buffer.read()

            # Validate PDF structure
            if not pdf_bytes.startswith(b"%PDF") or b"%%EOF" not in pdf_bytes:
                raise ValueError("Generated invalid PDF stream")

            return base64.b64encode(pdf_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Error building PDF: {e}")
            # Fallback valid PDF on any exception
            fallback_content = [
                Paragraph("Conversation Export", self.styles["date"]),
                Paragraph(
                    "An error occurred while generating the conversation PDF.",
                    self.styles["assistant"],
                ),
                Paragraph(str(e), self.styles["meta"]),
            ]
            doc.build(fallback_content)
            pdf_buffer.seek(0)
            pdf_bytes = pdf_buffer.read()
            return base64.b64encode(pdf_bytes).decode("utf-8")

    def _get_chat_styles(self):
        styles = getSampleStyleSheet()
        return {
            "meta": ParagraphStyle(
                name="MetaStyle",
                parent=styles["Normal"],
                fontSize=9,
                textColor=colors.gray,
                spaceAfter=2,
            ),
            "user": ParagraphStyle(
                name="UserStyle",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.black,
                backColor=colors.whitesmoke,
                borderPadding=5,
                leading=14,
                wordWrap='CJK',  # Enable better word wrapping
                allowWidows=1,   # Allow widow lines
                allowOrphans=1,  # Allow orphan lines
            ),
            "assistant": ParagraphStyle(
                name="AssistantStyle",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.black,
                backColor=colors.aliceblue,
                borderPadding=5,
                leading=14,
                wordWrap='CJK',  # Enable better word wrapping
                allowWidows=1,   # Allow widow lines
                allowOrphans=1,  # Allow orphan lines
            ),
            "date": ParagraphStyle(
                name="DateHeader",
                parent=styles["Heading2"],
                fontSize=12,
                textColor=colors.black,
                alignment=TA_LEFT,
                spaceBefore=16,
                spaceAfter=10,
            ),
            "separator": ParagraphStyle(
                name="SeparatorStyle",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.gray,
                alignment=TA_CENTER,
                spaceBefore=10,
                spaceAfter=10,
            ),
            "filter_header": ParagraphStyle(
                name="FilterHeader",
                parent=styles["Heading3"],
                fontSize=11,
                textColor=colors.HexColor("#2563eb"),  # Blue color
                alignment=TA_CENTER,
                spaceBefore=10,
                spaceAfter=6,
                fontName="Helvetica-Bold",
            ),
        }

    def _group_history(self):
        grouped_history = defaultdict(list)
        for msg in self.history:
            timestamp = msg.get("timestamp")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    date_key = dt.strftime("%B %d, %Y")
                    grouped_history[date_key].append((dt, msg))
                except Exception:
                    grouped_history[UNKNOW_DATE].append((None, msg))
            else:
                grouped_history[UNKNOW_DATE].append((None, msg))

        return sorted(
            grouped_history.items(),
            key=lambda x: (
                datetime.strptime(x[0], "%B %d, %Y")
                if x[0] != UNKNOW_DATE
                else datetime.min
            ),
        )

    def _build_message_blocks(self, messages):
        blocks = []
        messages.sort(key=lambda x: x[0] if x[0] else datetime.min)

        for dt, msg in messages:
            try:
                blocks.extend(self._create_single_message_block(dt, msg))
            except Exception as e:
                logger.warning(f"Error processing message: {e}")
                # Add fallback simple message
                fallback_text = f"[Error processing message from {dt or 'Unknown Time'}]"
                fallback_para = Paragraph(fallback_text, self.styles["meta"])
                blocks.extend([fallback_para, Spacer(1, 6)])

        return blocks

    def _create_single_message_block(self, dt, msg):
        """Create a single message block with proper error handling."""
        content_text = msg["content"][0].get("text", "")
        if len(content_text) > 5000:
            content_text = (
                content_text[:4950]
                + "... [Content truncated for PDF generation]"
            )

        html_text = markdown2.markdown(content_text)
        import pytz
        if dt and dt.tzinfo:
            try:
                # Use the requested timezone
                local_dt = dt.astimezone(pytz.timezone(self.timezone))
            except Exception as e:
                logger.warning(f"Error converting timezone {self.timezone}: {e}")
                local_dt = dt
        else:
            local_dt = dt
        time_str = local_dt.strftime("%I:%M %p") if local_dt else "Unknown Time"
        role = msg["role"]

        meta = f"{'User' if role == 'user' else 'Alex'} - {time_str}"
        meta_para = Paragraph(meta, self.styles["meta"])
        msg_para = Paragraph(html_text, self.styles[role])

        # Create message block elements with full width
        message_content = [
            Table([[meta_para]], colWidths=[7 * inch], splitByRow=1, hAlign="LEFT"),
            Table([[msg_para]], colWidths=[7 * inch], splitByRow=1, hAlign="LEFT"),
        ]

        # Style all tables
        for table in message_content:
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )

        # Try to keep message together, but allow splitting if too large
        try:
            return [KeepTogether(message_content), Spacer(1, 6)]
        except (ValueError, RuntimeError):
            # If KeepTogether fails, add elements individually
            return message_content + [Spacer(1, 6)]


@cbv(chat_routes)
class ConversationView:

    @chat_routes.post("/conversations")
    def create_conversation_api(
        self,
        request: CreateConversationRequest,
        user_data: dict = Depends(verify_token),
    ):
        """Create a new conversation."""
        try:
            user_id = UUID(user_data["sub"])
            data = request.model_dump()
            data["user_id"] = user_id

            conversation = create_conversation(data)

            if conversation:
                response_data = {
                    "id": str(conversation.id),
                    "title": conversation.title if conversation.title else "New Conversation",
                    "agent_id": (
                        str(conversation.agent_id) if conversation.agent_id else None
                    ),
                    "status": conversation.status.value,
                    "message_count": conversation.message_count,
                    "created_at": conversation.created_at.isoformat(),
                    "updated_at": conversation.updated_at.isoformat(),
                }

                return create_response(
                    message="Conversation created successfully",
                    error_code=SUCCESS_CODE,
                    status=True,
                    data={"conversation": response_data},
                )

            return create_response(
                message="Failed to create conversation",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.post("/sessions/start")
    def start_session_api(
        self,
        request: StartSessionRequest,
        user_data: dict = Depends(verify_token),
    ):
        """
        Start or resume a conversation session.
        - If conversation_id is provided: Resume existing conversation
        - If conversation_id is None:
            - Check for existing empty conversations (message_count = 0) for this agent
            - If found, reuse the empty conversation
            - If not found, create a new conversation
        Returns conversation_id to use in WebSocket connection.
        """
        try:
            user_id = UUID(user_data["sub"])
            is_new = False
            conversation = None

            # Case 1: Resume existing conversation
            if request.conversation_id:
                conversation = get_conversation_by_id(
                    conversation_id=request.conversation_id,
                    user_id=user_id
                )

                if not conversation:
                    return create_response(
                        message="Conversation not found or access denied",
                        error_code=NOT_FOUND,
                        status=False,
                        status_code=404
                    )

                # Verify conversation belongs to the requested agent
                if str(conversation.agent_id) != str(request.agent_id):
                    return create_response(
                        message="Conversation does not belong to this agent",
                        error_code=NOT_FOUND,
                        status=False,
                        status_code=404
                    )

                logger.info(
                    f"Resuming conversation {conversation.id} for user {user_id}"
                )

            # Case 2: Create new conversation (or reuse empty one)
            else:
                # First check if there's an existing empty conversation for this agent
                existing_conversations = get_user_conversations(
                    user_id=user_id,
                    limit=10,  # Check last 10 conversations
                    offset=0,
                    include_deleted=False,
                    agent_id=request.agent_id
                )

                # Find an empty conversation (message_count = 0)
                empty_conversation = None
                for conv in existing_conversations:
                    if conv.message_count == 0:
                        empty_conversation = conv
                        break

                if empty_conversation:
                    # Reuse existing empty conversation
                    conversation = empty_conversation
                    is_new = False
                    logger.info(
                        f"Reusing empty conversation {conversation.id} for user {user_id}"
                    )
                else:
                    # Create new conversation
                    conversation = start_new_conversation(
                        user_id=user_id,
                        agent_id=request.agent_id,
                        title=request.title
                    )

                    if not conversation:
                        return create_response(
                            message="Failed to create conversation",
                            error_code=SOMETHING_WENT_WRONG,
                            status=False,
                            status_code=500
                        )

                    is_new = True
                    logger.info(
                        f"Created new conversation {conversation.id} for user {user_id}"
                    )

            # Build response
            session_data = StartSessionResponse(
                conversation_id=str(conversation.id),
                title=conversation.title or "New Conversation",
                is_new=is_new,
                message_count=conversation.message_count,
                created_at=conversation.created_at,
                last_message_at=conversation.last_message_at
            )

            return create_response(
                message="Session started successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"session": session_data.model_dump()},
            )

        except Exception as e:
            logger.error(f"Error starting session: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.get("/conversations")
    def get_conversations_api(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        include_deleted: bool = Query(False),
        agent_id: Optional[UUID] = Query(None),
        search: Optional[str] = Query(None, description="Search conversations by title"),
        user_data: dict = Depends(verify_token),
    ):
        """Get user's conversations with pagination and optional search by title."""
        try:
            user_id = UUID(user_data["sub"])
            offset = (page - 1) * page_size

            conversations = get_user_conversations(
                user_id=user_id,
                limit=page_size + 1,  # Get one extra to check if there's a next page
                offset=offset,
                include_deleted=include_deleted,
                agent_id=agent_id,
                search=search,
            )

            has_next = len(conversations) > page_size
            if has_next:
                conversations = conversations[:-1]  # Remove the extra item

            data = [
                {
                    "id": str(conv.id),
                    "title": conv.title if conv.title else "New Conversation",
                    "agent_id": str(conv.agent_id) if conv.agent_id else None,
                    "status": conv.status.value,
                    "message_count": conv.message_count,
                    "created_at": conv.created_at.isoformat(),
                    "updated_at": conv.updated_at.isoformat(),
                    "last_message_at": (
                        conv.last_message_at.isoformat()
                        if conv.last_message_at
                        else None
                    ),
                }
                for conv in conversations
            ]

            return create_response(
                message="Conversations retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={
                    "conversations": data,
                    "page": page,
                    "page_size": page_size,
                    "has_next": has_next,
                    "total_count": len(data),
                },
            )

        except Exception as e:
            logger.error(f"Error fetching conversations: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.get("/conversations/{conversation_id}")
    def get_conversation_api(
        self, conversation_id: UUID, user_data: dict = Depends(verify_token)
    ):
        """Get a specific conversation."""
        try:
            user_id = UUID(user_data["sub"])

            conversation = get_conversation_by_id(
                conversation_id=conversation_id, user_id=user_id
            )

            if not conversation:
                return create_response(
                    message="Conversation not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            data = {
                "id": str(conversation.id),
                "title": conversation.title if conversation.title else "New Conversation",
                "agent_id": (
                    str(conversation.agent_id) if conversation.agent_id else None
                ),
                "status": conversation.status.value,
                "message_count": conversation.message_count,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
                "last_message_at": (
                    conversation.last_message_at.isoformat()
                    if conversation.last_message_at
                    else None
                ),
            }

            return create_response(
                message="Conversation retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"conversation": data},
            )

        except Exception as e:
            logger.error(f"Error fetching conversation: {e}")
            return create_response(
                message=went_wrong,
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.delete("/conversations/{conversation_id}")
    def delete_conversation_api(
        self, conversation_id: UUID, user_data: dict = Depends(verify_token)
    ):
        """Soft delete a conversation."""
        try:
            user_id = UUID(user_data["sub"])

            success = soft_delete_conversation(
                conversation_id=conversation_id, user_id=user_id
            )

            if not success:
                return create_response(
                    message="Conversation not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            return create_response(
                message="Conversation deleted successfully",
                error_code=SUCCESS_CODE,
                status=True,
            )

        except Exception as e:
            logger.error(f"Error deleting conversation: {e}")
            return create_response(
                message="Failed to delete conversation",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.patch("/conversations/{conversation_id}")
    def update_conversation_api(
        self,
        conversation_id: UUID,
        request: UpdateConversationRequest,
        user_data: dict = Depends(verify_token)
    ):
        """Update conversation title."""
        try:
            user_id = UUID(user_data["sub"])

            conversation = update_conversation_title(
                conversation_id=conversation_id,
                user_id=user_id,
                title=request.title
            )

            if not conversation:
                return create_response(
                    message="Conversation not found",
                    error_code=NOT_FOUND,
                    status=False,
                    status_code=404
                )

            data = {
                "id": str(conversation.id),
                "title": conversation.title,
                "agent_id": str(conversation.agent_id) if conversation.agent_id else None,
                "status": conversation.status.value,
                "message_count": conversation.message_count,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
                "last_message_at": (
                    conversation.last_message_at.isoformat()
                    if conversation.last_message_at
                    else None
                ),
            }

            return create_response(
                message="Conversation title updated successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"conversation": data},
            )

        except Exception as e:
            logger.error(f"Error updating conversation: {e}")
            return create_response(
                message="Failed to update conversation",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    # DEPRECATED: This API returns messages in ascending order (oldest first).
    # If get_conversation_messages_loadmore_api works correctly, this endpoint should be removed.
    # Use /conversations/{conversation_id}/messages/loadmore instead for newest-first ordering.
    @chat_routes.get("/conversations/{conversation_id}/messages")
    def get_conversation_messages_api(
        self,
        conversation_id: UUID,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO format)"),
        end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO format)"),
        user_data: dict = Depends(verify_token)
    ):
        """Get messages from a conversation with pagination and optional date range filtering."""
        try:
            user_id = UUID(user_data["sub"])
            offset = (page - 1) * page_size

            messages = get_conversation_messages(
                conversation_id=conversation_id,
                user_id=user_id,
                limit=page_size + 1,   # fetch one extra to check has_next
                offset=offset,
                start_date=start_date,
                end_date=end_date
            )

            has_next = len(messages) > page_size
            if has_next:
                messages = messages[:-1]

            message_responses = [
                MessageResponse.model_validate(msg) for msg in messages
            ]

            response_data = MessageListResponse(
                messages=message_responses,
                conversation_id=conversation_id,
                total_count=len(message_responses),
                page=page,
                page_size=page_size,
                has_next=has_next
            )

            # Convert response data to dict before JSON serialization
            response_dict = {
                "status": True,
                "message": "Messages retrieved successfully",
                "error_code": SUCCESS_CODE,
                "data": response_data.dict()
            }
            # Ensure all UUIDs are converted to strings
            response_json = json.dumps(response_dict, default=str)
            return Response(content=response_json, media_type="application/json")

        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            return create_response(
                message="Failed to fetch messages",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.get("/conversations/{conversation_id}/messages/loadmore")
    def get_conversation_messages_loadmore_api(
        self,
        conversation_id: UUID,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO format)"),
        end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO format)"),
        user_data: dict = Depends(verify_token)
    ):
        """Get messages from a conversation with pagination in descending order (newest first).

        This is optimized for 'load more' functionality where users scroll up to see older messages.
        Messages are returned newest-first, so page 1 contains the most recent messages.
        """
        try:
            user_id = UUID(user_data["sub"])
            offset = (page - 1) * page_size

            messages = get_conversation_messages_loadmore(
                conversation_id=conversation_id,
                user_id=user_id,
                limit=page_size + 1,   # fetch one extra to check has_next
                offset=offset,
                start_date=start_date,
                end_date=end_date
            )

            has_next = len(messages) > page_size
            if has_next:
                messages = messages[:-1]

            message_responses = [
                MessageResponse.model_validate(msg) for msg in messages
            ]

            response_data = MessageListResponse(
                messages=message_responses,
                conversation_id=conversation_id,
                total_count=len(message_responses),
                page=page,
                page_size=page_size,
                has_next=has_next
            )

            # Convert response data to dict before JSON serialization
            response_dict = {
                "status": True,
                "message": "Messages retrieved successfully",
                "error_code": SUCCESS_CODE,
                "data": response_data.model_dump()
            }
            # Ensure all UUIDs are converted to strings
            response_json = json.dumps(response_dict, default=str)
            return Response(content=response_json, media_type="application/json")

        except Exception as e:
            logger.error(f"Error fetching messages (loadmore): {e}")
            return create_response(
                message="Failed to fetch messages",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.get("/conversations/{conversation_id}/download")
    def get_conversation_download_api(
        self,
        conversation_id: UUID,
        max_pairs: int = Query(10, ge=1, le=50),
        start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO format)"),
        end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO format)"),
        timezone: str = Query("UTC", description="Target timezone for the PDF report"),
        user_data: dict = Depends(verify_token),
    ):
        """Get conversation history as base64-encoded PDF with optional date range filtering."""
        try:
            user_id = UUID(user_data["sub"])
            # If date filters are provided, fetch all messages without limit (5000 pairs = 10000 messages)
            # Otherwise, respect the max_pairs limit
            pairs_limit = 5000 if (start_date or end_date) else max_pairs
            history = get_recent_conversation_history(
                conversation_id=conversation_id, user_id=user_id, max_pairs=pairs_limit,
                start_date=start_date, end_date=end_date
            )

            # Handle empty history
            if not history:
                history = []

            # Validate timezone
            try:
                import pytz
                pytz.timezone(timezone)
            except Exception:
                timezone = "UTC"

            pdf_builder = ConversationPDFBuilder(
                conversation_id, 
                history, 
                start_date=start_date, 
                end_date=end_date,
                timezone=timezone
            )
            base64_pdf = pdf_builder.build_base64_pdf()

            return JSONResponse(
                content={
                    "status": True,
                    "file_name": f"conversation_{conversation_id}.pdf",
                    "mime_type": "application/pdf",
                    "base64_pdf": base64_pdf,
                }
            )

        except Exception as e:
            logger.error(f"Error fetching conversation history: {e}")
            return create_response(
                message="Failed to fetch conversation history",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )


@cbv(chat_routes)
class AlexChatHistoryView:

    @chat_routes.get("/AlexChat/history/new")
    def get_chat_history_new(
        self,
        device_key: str,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0),
    ):
        try:
            messages = get_alex_chat_history_by_device_key(
                device_key, limit=limit, offset=offset
            )

            def _msg_to_dict(msg):
                if not msg:
                    return None

                # Extract nested conditional expressions into independent statements
                content = getattr(msg, "content", None)

                created_at_obj = getattr(msg, "created_at", None)
                created_at = created_at_obj.isoformat() if created_at_obj else None

                updated_at_obj = getattr(msg, "updated_at", None)
                updated_at = updated_at_obj.isoformat() if updated_at_obj else None

                return {
                    "content": content,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }

            def _get_date_label(msg_date):
                today = datetime.now().date()
                delta = (today - msg_date.date()).days
                if delta == 0:
                    return "today"
                elif delta == 1:
                    return "yesterday"
                return msg_date.strftime("%d-%m-%Y")

            date_groups = defaultdict(list)
            i = 0

            while i < len(messages):
                current = messages[i]
                user_msg = assistant_msg = None

                if current.message_type == MessageTypeEnum.user:
                    user_msg = current
                    if i + 1 < len(messages) and messages[i + 1].message_type == MessageTypeEnum.assistant:
                        assistant_msg = messages[i + 1]
                        i += 1
                    msg_datetime = user_msg.created_at
                    sequence = user_msg.sequence_number
                else:
                    assistant_msg = current
                    msg_datetime = current.created_at
                    sequence = current.sequence_number

                if msg_datetime:
                    date_label = _get_date_label(msg_datetime)
                    date_groups[date_label].append({
                        "sequence": sequence,
                        "user": _msg_to_dict(user_msg),
                        "assistant": _msg_to_dict(assistant_msg),
                    })
                i += 1

            # Sort messages within each date group by sequence number
            for date_label in date_groups:
                date_groups[date_label].sort(key=lambda x: x["sequence"])

            result = [{"date": d, "history": h} for d, h in date_groups.items()]
            # Sort: oldest dates first, yesterday next, today last
            result.sort(key=lambda x: (
                2 if x["date"] == "today" else
                1 if x["date"] == "yesterday" else
                0, datetime.strptime(x["date"], "%d-%m-%Y").timestamp() if x["date"] not in ["today", "yesterday"] else 0
            ))

            return create_response(
                message="Chat history retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"history": result},
            )
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return create_response(
                message="Something went wrong",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.get("/AlexChat/history")
    def get_chat_history(
        self,
        device_key: str,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0),
    ):
        try:
            messages = get_alex_chat_history_by_device_key(
                device_key, limit=limit, offset=offset
            )

            grouped = []
            i = 0

            def _msg_to_dict(msg):
                if not msg:
                    return None

                # Extract nested conditional expressions into independent statements
                content = getattr(msg, "content", None)

                created_at_obj = getattr(msg, "created_at", None)
                created_at = created_at_obj.isoformat() if created_at_obj else None

                updated_at_obj = getattr(msg, "updated_at", None)
                updated_at = updated_at_obj.isoformat() if updated_at_obj else None

                return {
                    "content": content,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }

            # Iterate and pair each user message with the following assistant message when present.
            while i < len(messages):
                current = messages[i]
                user_msg = None
                assistant_msg = None

                if current.message_type == MessageTypeEnum.user:
                    user_msg = current
                    # If the next message exists and is an assistant, pair it
                    if (
                        i + 1 < len(messages)
                        and messages[i + 1].message_type == MessageTypeEnum.assistant
                    ):
                        assistant_msg = messages[i + 1]
                        i += 1  # consume the assistant message
                    sequence = user_msg.sequence_number
                else:
                    # current is not a user message; treat it as assistant-only entry
                    assistant_msg = current
                    sequence = current.sequence_number

                # Extract content and timestamps into independent variables for clarity
                user_entry = _msg_to_dict(user_msg)
                assistant_entry = _msg_to_dict(assistant_msg)

                grouped.append(
                    {
                        "sequence": sequence,
                        "user": user_entry,
                        "assistant": assistant_entry,
                    }
                )

                i += 1

            return create_response(
                message="Chat history retrieved successfully",
                error_code=SUCCESS_CODE,
                status=True,
                data={"history": grouped},
            )
        except Exception as e:
            logger.error(f"Error fetching chat history: {e}")
            return create_response(
                message="Something went wrong",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500
            )

    @chat_routes.get("/AlexChat/download")
    def get_alex_chat_download_api(
        self,
        device_key: str,
        max_pairs: int = Query(10, ge=1, le=50),
        start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO format)"),
        end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO format)"),
        timezone: str = Query("UTC", description="Target timezone for the PDF report"),
        user_data: dict = Depends(verify_token),
    ):
        """Get Alex chat history as base64-encoded PDF with optional date range filtering."""
        try:
            logger.info(f"PDF Download - start_date: {start_date} (type: {type(start_date)}), end_date: {end_date} (type: {type(end_date)})")
            # If date filters are provided, fetch all messages without limit
            # Otherwise, respect the max_pairs limit
            limit = 10000 if (start_date or end_date) else max_pairs * 2
            messages = get_alex_chat_history_by_device_key(
                device_key, limit=limit, offset=0, start_date=start_date, end_date=end_date
            )

            history = []
            for msg in messages:
                content = getattr(msg, "content", None)
                created_at_obj = getattr(msg, "created_at", None)
                message_type = getattr(msg, "message_type", None)

                if content and created_at_obj:
                    history.append({
                        "role": "user" if message_type == MessageTypeEnum.user else "assistant",
                        "content": [{"text": content}],
                        "timestamp": created_at_obj.isoformat(),
                    })

            # Validate timezone
            try:
                import pytz
                pytz.timezone(timezone)
            except Exception:
                timezone = "UTC"

            pdf_builder = ConversationPDFBuilder(
                device_key, 
                history, 
                start_date=start_date, 
                end_date=end_date,
                timezone=timezone
            )
            base64_pdf = pdf_builder.build_base64_pdf()

            return JSONResponse(
                content={
                    "status": True,
                    "file_name": f"alex_chat_{device_key}.pdf",
                    "mime_type": "application/pdf",
                    "base64_pdf": base64_pdf,
                }
            )

        except Exception as e:
            logger.error(f"Error fetching Alex chat history for download: {e}")
            return create_response(
                message="Failed to fetch chat history",
                error_code=SOMETHING_WENT_WRONG,
                status=False,
                status_code=500,
            )


@chat_routes.get("/AlexChat/device-id")
def get_device_id_route(request: Request):
    return {"device_id": get_device_id(request)}
