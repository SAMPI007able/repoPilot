from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SupportCategory(StrEnum):
    CHAT_WITH_CODEBASE = "CHAT_WITH_CODEBASE"
    TEST_GENERATION = "TEST_GENERATION"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    PREVIEW = "PREVIEW"
    OTHER = "OTHER"


SUPPORT_CATEGORY_LABELS: dict[SupportCategory, str] = {
    SupportCategory.CHAT_WITH_CODEBASE: "Chat with Codebase",
    SupportCategory.TEST_GENERATION: "Test Generation",
    SupportCategory.IMPACT_ANALYSIS: "Impact Analysis",
    SupportCategory.PREVIEW: "Preview",
    SupportCategory.OTHER: "Other",
}


class SupportTicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


SUPPORT_STATUS_LABELS: dict[SupportTicketStatus, str] = {
    SupportTicketStatus.OPEN: "Open",
    SupportTicketStatus.IN_PROGRESS: "In Progress",
    SupportTicketStatus.COMPLETED: "Completed",
}


class SupportTicketCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    category: SupportCategory
    subject: str = Field(min_length=3, max_length=200)
    description_html: str = Field(alias="descriptionHtml", min_length=1, max_length=100_000)


class SupportTicketStatusUpdate(BaseModel):
    status: Literal[SupportTicketStatus.IN_PROGRESS, SupportTicketStatus.COMPLETED]


class SupportTicket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    category: SupportCategory
    subject: str
    description_html: str = Field(alias="descriptionHtml")
    status: SupportTicketStatus
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    in_progress_at: datetime | None = Field(alias="inProgressAt")
    completed_at: datetime | None = Field(alias="completedAt")


class AdminSupportTicket(SupportTicket):
    user_id: str = Field(alias="userId")
    user_email: str = Field(alias="userEmail")
    user_display_name: str | None = Field(alias="userDisplayName")


class SupportUploadResponse(BaseModel):
    url: str
