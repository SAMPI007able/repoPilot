import os
import time

from app.persistence.database import Database
from app.persistence.preview_persistence_service import PreviewPersistenceService
from app.models.preview_models import PreviewStatus
from app.services.preview_queue import RQPreviewJobQueue


def run() -> None:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    database_path = os.path.join(base_dir, "workspace", "testforge.db").replace("\\", "/")
    database = Database(os.getenv("DATABASE_URL", f"sqlite:///{database_path}"))
    persistence = PreviewPersistenceService(database)
    queue = RQPreviewJobQueue()
    interval = int(os.getenv("PREVIEW_RECONCILE_SECONDS", "15"))
    try:
        while True:
            for preview_id in persistence.expired_active_ids():
                try:
                    preview = persistence.get(preview_id)
                    if preview.status != PreviewStatus.STOPPING:
                        persistence.transition(
                            preview_id, PreviewStatus.STOPPING, "Preview expired; cleanup queued."
                        )
                    queue.enqueue_stop(preview_id, expired=True)
                except Exception:
                    # Durable STOPPING state makes the next reconciliation pass retry safely.
                    continue
            time.sleep(interval)
    finally:
        database.close()


if __name__ == "__main__":
    run()
