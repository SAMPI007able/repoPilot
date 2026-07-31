from app.models.preview_models import (
    ACTIVE_PREVIEW_STATUSES,
    PreviewCreateRequest,
    PreviewEnvironment,
    PreviewExtendRequest,
    PreviewLogs,
    PreviewStatus,
)
from app.persistence.preview_persistence_service import PreviewPersistenceService
from app.services.preview_logs import PreviewLogService
from app.services.preview_queue import PreviewJobQueue, PreviewQueueUnavailableError


class PreviewEnvironmentValidationError(ValueError):
    def __init__(self, violations: list[str]) -> None:
        super().__init__("Invalid preview environment.")
        self.violations = violations


class PreviewService:
    def __init__(
        self,
        persistence: PreviewPersistenceService,
        queue: PreviewJobQueue,
        logs: PreviewLogService,
    ) -> None:
        self.persistence = persistence
        self.queue = queue
        self.logs = logs

    def create(self, workspace_id: str, idempotency_key: str, payload: PreviewCreateRequest) -> PreviewEnvironment:
        if not idempotency_key or len(idempotency_key) > 128:
            raise PreviewEnvironmentValidationError(["Idempotency-Key must contain 1 to 128 characters."])

        # Persist only names. Values live in the short-lived RQ payload and sandbox environment.
        preview, created = self.persistence.create(workspace_id, idempotency_key, sorted(payload.environment))
        if not created:
            return preview
        manifest_environment = preview.manifest.environment
        provided = set(payload.environment)
        required = set(manifest_environment.required)
        allowed = required | set(manifest_environment.optional)
        violations = []
        missing_required = {name for name in required if not payload.environment.get(name)}
        if missing_required:
            violations.append(f"Missing required environment variables: {', '.join(sorted(missing_required))}.")
        if provided - allowed:
            violations.append(f"Environment variables are not declared by the manifest: {', '.join(sorted(provided - allowed))}.")
        if any(len(value) > 16_384 for value in payload.environment.values()):
            violations.append("Environment variable values may not exceed 16384 characters.")
        if violations:
            self.persistence.transition(
                preview.id, PreviewStatus.FAILED, "Preview environment validation failed.",
                error_code="PREVIEW_ENVIRONMENT_INVALID", error_message=" ".join(violations),
            )
            raise PreviewEnvironmentValidationError(violations)
        try:
            self.queue.enqueue_start(preview.id, payload.environment)
        except PreviewQueueUnavailableError:
            self.persistence.transition(
                preview.id, PreviewStatus.FAILED, "Preview queue submission failed.",
                error_code="PREVIEW_QUEUE_UNAVAILABLE", error_message="The preview worker queue is unavailable.",
            )
            raise
        return self.persistence.get(preview.id)

    def get(self, preview_id: str) -> PreviewEnvironment:
        return self.persistence.get(preview_id)

    def latest_for_workspace(self, workspace_id: str) -> PreviewEnvironment:
        return self.persistence.latest_for_workspace(workspace_id)

    def stop(self, preview_id: str, *, expired: bool = False) -> PreviewEnvironment:
        preview = self.persistence.get(preview_id)
        if preview.status not in ACTIVE_PREVIEW_STATUSES:
            return preview
        if preview.status != PreviewStatus.STOPPING:
            preview = self.persistence.transition(
                preview_id, PreviewStatus.STOPPING,
                "Preview expiry cleanup queued." if expired else "Preview stop queued.",
            )
        try:
            self.queue.enqueue_stop(preview_id, expired)
        except PreviewQueueUnavailableError:
            # Keep STOPPING durable so reconciliation can retry cleanup.
            raise
        return preview

    def extend(self, preview_id: str, payload: PreviewExtendRequest) -> PreviewEnvironment:
        return self.persistence.extend(preview_id, payload.minutes)

    def logs_for(self, preview_id: str) -> PreviewLogs:
        self.persistence.get(preview_id)
        content, truncated = self.logs.read(preview_id)
        return PreviewLogs(previewId=preview_id, content=content, truncated=truncated)
