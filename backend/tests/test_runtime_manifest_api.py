import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.runtime_manifest_models import RuntimeManifestRecord
from app.persistence.runtime_manifest_persistence_service import RuntimeManifestNotFoundError
from backend.tests.test_runtime_manifest import fixture_metadata
from app.services.runtime_manifest_analyzer import DeterministicRuntimeManifestAnalyzer


def manifest_record() -> RuntimeManifestRecord:
    analysis = DeterministicRuntimeManifestAnalyzer().analyze(fixture_metadata())
    now = datetime.now(timezone.utc)
    return RuntimeManifestRecord(
        **analysis.model_dump(),
        workspaceId="workspace-id",
        approved=False,
        revision=1,
        createdAt=now,
        updatedAt=now,
    )


class FakeRuntimeManifestService:
    def analyze(self, workspace_id: str, instructions: str | None = None):
        del instructions
        record = manifest_record()
        return record.model_copy(update={"workspace_id": workspace_id})

    def get(self, workspace_id: str):
        raise RuntimeManifestNotFoundError(workspace_id)


class RuntimeManifestAPITests(unittest.TestCase):
    def test_analyze_returns_typed_manifest_without_execution(self) -> None:
        with patch("app.main.runtime_manifest_service", FakeRuntimeManifestService()):
            response = TestClient(app).post(
                "/workspaces/workspace-id/runtime-manifest/analyze",
                json={"instructions": "Use Vite defaults"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["manifest"]["runtime"]["family"], "node")
        self.assertFalse(response.json()["approved"])

    def test_preview_errors_use_stable_envelope(self) -> None:
        with patch("app.main.runtime_manifest_service", FakeRuntimeManifestService()):
            not_found = TestClient(app).get(
                "/workspaces/workspace-id/runtime-manifest"
            )
            invalid = TestClient(app).post(
                "/workspaces/workspace-id/runtime-manifest/analyze",
                json={"unexpected": True},
            )

        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.json()["code"], "RUNTIME_MANIFEST_NOT_FOUND")
        self.assertIn("correlationId", not_found.json())
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["code"], "PREVIEW_REQUEST_INVALID")


if __name__ == "__main__":
    unittest.main()
