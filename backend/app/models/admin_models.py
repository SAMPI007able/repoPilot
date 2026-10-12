from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminDashboard(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    total_users: int = Field(alias="totalUsers")
    active_previews: int = Field(alias="activePreviews")
    active_browser_sessions: int = Field(alias="activeBrowserSessions")


class AdminUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    primary_email: str = Field(alias="primaryEmail")
    display_name: str | None = Field(alias="displayName")
    status: str
    role: str
    created_at: datetime = Field(alias="createdAt")
    last_login_at: datetime | None = Field(alias="lastLoginAt")


class AdminUserStatusUpdate(BaseModel):
    suspended: bool


class AdminPreview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    workspace_id: str = Field(alias="workspaceId")
    user_id: str | None = Field(alias="userId")
    user_email: str | None = Field(alias="userEmail")
    repository_url: str = Field(alias="repositoryUrl")
    status: str
    provider: str
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime = Field(alias="expiresAt")


class AdminBrowserSession(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    user_id: str | None = Field(alias="userId")
    user_email: str | None = Field(alias="userEmail")
    status: str
    provider: str
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime | None = Field(alias="expiresAt")


class AdminUsage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(alias="userId")
    primary_email: str = Field(alias="primaryEmail")
    ai_requests: int = Field(alias="aiRequests")
    preview_count: int = Field(alias="previewCount")
    preview_minutes: int = Field(alias="previewMinutes")
    storage_bytes: int = Field(alias="storageBytes")


class AdminLog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    category: str
    severity: str
    code: str | None
    message: str
    user_id: str | None = Field(alias="userId")
    created_at: datetime = Field(alias="createdAt")
