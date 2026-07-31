from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.runtime_manifest_models import ManifestModel, RuntimeManifest


class PreviewStatus(StrEnum):
    QUEUED = "queued"
    CLONING = "cloning"
    INSTALLING = "installing"
    BUILDING = "building"
    STARTING = "starting"
    HEALTH_CHECKING = "health_checking"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    EXPIRED = "expired"
    FAILED = "failed"


ACTIVE_PREVIEW_STATUSES = {
    PreviewStatus.QUEUED,
    PreviewStatus.CLONING,
    PreviewStatus.INSTALLING,
    PreviewStatus.BUILDING,
    PreviewStatus.STARTING,
    PreviewStatus.HEALTH_CHECKING,
    PreviewStatus.READY,
    PreviewStatus.STOPPING,
}


class PreviewCreateRequest(ManifestModel):
    environment: dict[str, str] = Field(default_factory=dict, max_length=100)


class PreviewExtendRequest(ManifestModel):
    minutes: int = Field(default=30, ge=5, le=60)


class PreviewEvent(ManifestModel):
    id: str
    preview_id: str
    status: PreviewStatus
    message: str
    created_at: datetime


class PreviewEnvironment(ManifestModel):
    id: str
    workspace_id: str
    status: PreviewStatus
    repository_url: str
    commit_sha: str
    manifest_revision: int
    manifest: RuntimeManifest
    preview_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    expires_at: datetime
    maximum_expires_at: datetime
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None = None
    stopped_at: datetime | None = None
    provider: str = "local-docker"
    development_warning: str = (
        "Trusted-development mode only. Docker alone is not an approved isolation "
        "boundary for hostile repositories."
    )


class PreviewLogs(ManifestModel):
    preview_id: str
    content: str
    truncated: bool = False

