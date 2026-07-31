import os

from app.models.preview_models import PreviewStatus
from app.persistence.artifact_store import create_artifact_store
from app.persistence.database import Database
from app.persistence.preview_persistence_service import PreviewConflictError, PreviewPersistenceService
from app.services.preview_logs import PreviewLogService
from app.services.sandbox_provider import LocalDockerSandboxProvider, SandboxExecutionError


def _services():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    persistence_dir = os.path.join(base_dir, "workspace")
    database_path = os.path.join(persistence_dir, "testforge.db").replace("\\", "/")
    database = Database(os.getenv("DATABASE_URL", f"sqlite:///{database_path}"))
    store = create_artifact_store(os.path.join(persistence_dir, "artifacts"))
    return database, PreviewPersistenceService(database), PreviewLogService(store)


def start_preview(preview_id: str, environment: dict[str, str]) -> None:
    database, persistence, logs = _services()
    sensitive_values = list(environment.values())
    log = lambda text: logs.append(preview_id, text, sensitive_values)
    provider = LocalDockerSandboxProvider()
    try:
        if os.getenv("PREVIEW_TRUSTED_LOCAL_EXECUTION", "false").lower() != "true":
            _fail(
                persistence, preview_id, "PREVIEW_EXECUTION_DISABLED",
                "Trusted local preview execution is disabled on this worker.",
            )
            return
        preview = persistence.get(preview_id)
        if preview.status != PreviewStatus.QUEUED:
            return

        def transition(status: PreviewStatus, message: str, state: dict | None) -> None:
            persistence.transition(preview_id, status, message, provider_state=state)

        result = provider.deploy(preview, environment, transition, log)
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
        environment.clear()
        database.close()


def stop_preview(preview_id: str, expired: bool = False) -> None:
    database, persistence, logs = _services()
    try:
        preview = persistence.get(preview_id)
        if preview.status in {PreviewStatus.STOPPED, PreviewStatus.EXPIRED, PreviewStatus.FAILED}:
            return
        if preview.status != PreviewStatus.STOPPING:
            persistence.transition(preview_id, PreviewStatus.STOPPING, "Preview cleanup started.")
        LocalDockerSandboxProvider().cleanup(
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
        database.close()


def _fail(persistence: PreviewPersistenceService, preview_id: str, code: str, message: str) -> None:
    try:
        persistence.transition(
            preview_id, PreviewStatus.FAILED, "Preview execution failed.",
            error_code=code, error_message=message,
        )
    except PreviewConflictError:
        pass
