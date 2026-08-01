from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    SUSPENDED = "SUSPENDED"
    DELETION_REQUESTED = "DELETION_REQUESTED"
    DELETED = "DELETED"


class UserRole(StrEnum):
    USER = "USER"
    SUPPORT = "SUPPORT"
    ADMIN = "ADMIN"


class TokenClaims(BaseModel):
    issuer: str
    subject: str
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    avatar_url: str | None = None
    provider: str = "oidc"


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None
    status: UserStatus
    role: UserRole
    email_verified: bool


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    primary_email: str = Field(alias="primaryEmail")
    display_name: str | None = Field(alias="displayName")
    avatar_url: str | None = Field(alias="avatarUrl")
    status: UserStatus
    role: UserRole
    email_verified: bool = Field(alias="emailVerified")
    created_at: datetime = Field(alias="createdAt")
    last_login_at: datetime | None = Field(alias="lastLoginAt")
