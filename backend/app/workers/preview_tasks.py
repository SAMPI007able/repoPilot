import os
import logging

from app.models.preview_models import PreviewStatus
from app.persistence.artifact_store import create_artifact_store
from app.persistence.database import Database
from app.persistence.preview_persistence_service import PreviewConflictError, PreviewPersistenceService
from app.services.preview_logs import PreviewLogService
from app.services.sandbox_provider import SandboxExecutionError
from app.services.sandbox_provider_factory import create_sandbox_provider
from app.config.rate_limit_settings import RateLimitSettings
from app.services.rate_limit_service import RateLimitBackendUnavailable, RateLimitService
from app.services.telemetry import Telemetry

telemetry = Telemetry()


logger = logging.getLogger(__name__)


def _services():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    persistence_dir = os.path.join(base_dir, "workspace")
    database_path = os.path.join(persistence_dir, "testforge.db").replace("\\", "/")
    database = Database(os.getenv("DATABASE_URL", f"sqlite:///{database_path}"))
    store = create_artifact_store(os.path.join(persistence_dir, "artifacts"))
    return database, PreviewPersistenceService(database), PreviewLogService(store)


def start_preview(
    preview_id: str, environment: dict[str, str],
    repository_authorization: str | None = None,
) -> None:
    database, persistence, logs = _services()
    sensitive_values = [*environment.values(), *([repository_authorization] if repository_authorization else [])]
    log = lambda text: logs.append(preview_id, text, sensitive_values)
    provider = None
    try:
        preview = persistence.get(preview_id)
        if (
            preview.provider == "local-docker"
            and os.getenv("PREVIEW_TRUSTED_LOCAL_EXECUTION", "false").lower() != "true"
        ):
            _fail(
                persistence, preview_id, "PREVIEW_EXECUTION_DISABLED",
                "Trusted local preview execution is disabled on this worker.",
            )
            return
        provider = create_sandbox_provider(preview.provider)
        if preview.status != PreviewStatus.QUEUED:
            return

        def transition(status: PreviewStatus, message: str, state: dict | None) -> None:
            persistence.transition(preview_id, status, message, provider_state=state)

        result = provider.deploy(
            preview, environment, transition, log, repository_authorization,
        )
        persistence.transition(
            preview_id, PreviewStatus.READY, "Preview is ready.",
            preview_url=result.preview_url, internal_url=result.internal_url,
            provider_state=result.provider_state,
        )
    except SandboxExecutionError as exc:
        _fail(persistence, preview_id, exc.code, str(exc))
    except Exception as exc:
        _fail(persistence, preview_id, "PREVIEW_WORKER_FAILED", "The preview worker failed unexpectedly.")
        raise
    finally:
        _release_terminal_slot(persistence, preview_id)
        environment.clear()
        repository_authorization = None
        database.close()


def stop_preview(preview_id: str, expired: bool = False) -> None:
    database, persistence, logs = _services()
    try:
        preview = persistence.get(preview_id)
        if preview.status in {PreviewStatus.STOPPED, PreviewStatus.EXPIRED, PreviewStatus.FAILED}:
            return
        if preview.status != PreviewStatus.STOPPING:
            persistence.transition(preview_id, PreviewStatus.STOPPING, "Preview cleanup started.")
        create_sandbox_provider(preview.provider).cleanup(
            persistence.provider_state(preview_id),
            lambda text: logs.append(preview_id, text),
        )
        target = PreviewStatus.EXPIRED if expired else PreviewStatus.STOPPED
        persistence.transition(
            preview_id, target,
            "Preview expired and sandbox resources were removed." if expired else "Preview stopped and sandbox resources were removed.",
        )
    except Exception as exc:
        _fail(persistence, preview_id, "PREVIEW_CLEANUP_FAILED", str(exc))
        raise
    finally:
        _release_terminal_slot(persistence, preview_id)
        database.close()


def _fail(persistence: PreviewPersistenceService, preview_id: str, code: str, message: str) -> None:
    owner_user_id = None
    try:
        owner_user_id = persistence.owner_user_id(preview_id)
    except Exception:
        pass

    try:
        persistence.transition(
            preview_id, PreviewStatus.FAILED, "Preview execution failed.",
            error_code=code, error_message=message,
        )
    except PreviewConflictError:
        pass

    if owner_user_id:
        telemetry.capture(owner_user_id, "preview_failed", {
            "preview_id": preview_id,
            "error_code": code,
            "error_message": message,
        })


def _release_terminal_slot(persistence: PreviewPersistenceService, preview_id: str) -> None:
    try:
        preview = persistence.get(preview_id)
        if preview.status not in {PreviewStatus.STOPPED, PreviewStatus.EXPIRED, PreviewStatus.FAILED}:
            return
        owner_user_id = persistence.owner_user_id(preview_id)
        if not owner_user_id:
            return
        settings = RateLimitSettings.from_env()
        if settings.enabled:
            RateLimitService(settings).release_concurrency_slot(owner_user_id, "preview", preview_id)
    except RateLimitBackendUnavailable:
        logger.error("Failed to release preview concurrency slot", extra={"previewId": preview_id})
    except Exception as exc:
        logger.error(
            "Unexpected preview quota cleanup failure",
            extra={"previewId": preview_id, "errorType": type(exc).__name__},
        )
