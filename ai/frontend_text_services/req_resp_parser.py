from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class FrontendTextResponse(BaseModel):
    """Response model for frontend text data."""
    id: str = Field(..., description="UUID as string")
    selector: Optional[str]
    routeKey: Optional[str]
    title: Optional[str]
    description: Optional[str]
    meta_data: Optional[Dict[str, Any]]
    comments: Optional[str]

    class Config:
        from_attributes = True


class FrontendTextListResponse(BaseModel):
    """Response model for list of frontend texts."""
    frontend_texts: list[FrontendTextResponse]
    total_count: int

    class Config:
        from_attributes = True


# Audio Preview Request Model
class AudioPreviewRequest(BaseModel):
    """Request model for audio preview."""
    text: str = Field(
        "Welcome to Prism Inspire",
        description="Text to convert to speech for preview",
        min_length=1,
        max_length=2000
    )
    accent_id: UUID = Field(None, description="Accent preference UUID")
    tone_ids: list[UUID] = Field(
        None,
        description="Comma-separated tone preference UUIDs"
    )
    gender_id: UUID = Field(None, description="Gender preference UUID")

    class Config:
        from_attributes = True