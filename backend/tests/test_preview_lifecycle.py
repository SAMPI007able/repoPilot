import os
import tempfile
import unittest
from datetime import datetime, timezone

from app.models.preview_models import PreviewCreateRequest, PreviewExtendRequest, PreviewStatus
from app.persistence.artifact_store import LocalArtifactStore
from app.persistence.database import Database
from app.persistence.models import RuntimeManifestRow, WorkspaceRow
from app.persistence.preview_persistence_service import PreviewConflictError, PreviewPersistenceService
from app.services.preview_logs import PreviewLogService
from app.services.preview_service import PreviewEnvironmentValidationError, PreviewService
from backend.tests.test_runtime_manifest import valid_manifest


class FakeQueue:
    def __init__(self) -> None:
        self.starts = []
        self.stops = []

    def enqueue_start(self, preview_id, environment) -> None:
        self.starts.append((preview_id, environment.copy()))

    def enqueue_stop(self, preview_id, expired=False) -> None:
        self.stops.append((preview_id, expired))


class PreviewLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database_path = os.path.join(self.temp.name, "preview.db").replace("\\", "/")
        self.database = Database(f"sqlite:///{database_path}")
        self.database.create_schema()
        self.persistence = PreviewPersistenceService(self.database)
        self.queue = FakeQueue()
        self.logs = PreviewLogService(LocalArtifactStore(os.path.join(self.temp.name, "artifacts")))
        self.service = PreviewService(self.persistence, self.queue, self.logs)
        now = datetime.now(timezone.utc)
        manifest = valid_manifest()
        with self.database.session() as session:
            session.add(WorkspaceRow(
                id="workspace", repo_url="https://example.test/repository.git",
                repo_name="repository", commit_sha="a" * 40, status="ready",
            ))
            session.add(RuntimeManifestRow(
                id="manifest", workspace_id="workspace", manifest_version="1",
                manifest=manifest.model_dump(mode="json", by_alias=True),
                analysis_summary={"framework": "vite", "packageManager": "npm", "confidence": 1},
                evidence=[], warnings=[], unsupported_reasons=[], supported=True,
                approved=True, revision=2, approved_at=now, created_at=now, updated_at=now,
            ))

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_create_is_idempotent_and_only_enqueues_once(self) -> None:
        payload = PreviewCreateRequest(environment={"VITE_API_URL": "https://api.example.test"})
        first = self.service.create("workspace", "same-request", payload)
        second = self.service.create("workspace", "same-request", payload)

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.status, PreviewStatus.QUEUED)
        self.assertEqual(len(self.queue.starts), 1)
        self.assertNotIn("https://api.example.test", str(self.persistence.provider_state(first.id)))

    def test_lifecycle_enforces_order_and_extension_cap(self) -> None:
        preview = self.service.create(
            "workspace", "lifecycle", PreviewCreateRequest(environment={"VITE_API_URL": "value"})
        )
        with self.assertRaises(PreviewConflictError):
            self.persistence.transition(preview.id, PreviewStatus.READY, "invalid shortcut")
        for status in (
            PreviewStatus.CLONING, PreviewStatus.INSTALLING, PreviewStatus.BUILDING,
            PreviewStatus.STARTING, PreviewStatus.HEALTH_CHECKING, PreviewStatus.READY,
        ):
            preview = self.persistence.transition(preview.id, status, status.value)
        extended = self.service.extend(preview.id, PreviewExtendRequest(minutes=60))
        self.assertLessEqual(extended.expires_at, extended.maximum_expires_at)
        stopped = self.service.stop(preview.id)
        self.assertEqual(stopped.status, PreviewStatus.STOPPING)
        self.assertEqual(self.queue.stops, [(preview.id, False)])

    def test_missing_required_environment_fails_without_queuing(self) -> None:
        with self.assertRaises(PreviewEnvironmentValidationError):
            self.service.create("workspace", "bad-environment", PreviewCreateRequest())
        self.assertEqual(self.queue.starts, [])

    def test_logs_redact_named_and_literal_secrets(self) -> None:
        self.logs.append(
            "preview", "API_KEY=visible application printed super-secret\n", ["super-secret"]
        )
        content, _ = self.logs.read("preview")
        self.assertNotIn("visible", content)
        self.assertNotIn("super-secret", content)
        self.assertIn("[REDACTED]", content)


if __name__ == "__main__":
    unittest.main()
