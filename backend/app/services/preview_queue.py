import os
from typing import Protocol


class PreviewQueueUnavailableError(RuntimeError):
    pass


class PreviewJobQueue(Protocol):
    def enqueue_start(
        self, preview_id: str, environment: dict[str, str],
        repository_authorization: str | None = None,
    ) -> None: ...
    def enqueue_stop(self, preview_id: str, expired: bool = False) -> None: ...


class RQPreviewJobQueue:
    def __init__(self, redis_url: str | None = None, queue_name: str = "previews") -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.queue_name = queue_name

    def _queue(self):
        try:
            from redis import Redis
            from rq import Queue
            connection = Redis.from_url(self.redis_url, socket_connect_timeout=2, socket_timeout=2)
            connection.ping()
            return Queue(
                self.queue_name, connection=connection,
                default_timeout=os.getenv("PREVIEW_JOB_TIMEOUT", "40m"),
            )
        except Exception as exc:
            raise PreviewQueueUnavailableError("The preview worker queue is unavailable.") from exc

    def enqueue_start(
        self, preview_id: str, environment: dict[str, str],
        repository_authorization: str | None = None,
    ) -> None:
        self._queue().enqueue(
            "app.workers.preview_tasks.start_preview",
            preview_id,
            environment,
            repository_authorization,
            job_id=f"preview-start-{preview_id}",
            result_ttl=0,
            failure_ttl=0,
        )

    def enqueue_stop(self, preview_id: str, expired: bool = False) -> None:
        self._queue().enqueue(
            "app.workers.preview_tasks.stop_preview",
            preview_id,
            expired,
            job_id=f"preview-stop-{preview_id}",
            result_ttl=0,
            failure_ttl=0,
        )
