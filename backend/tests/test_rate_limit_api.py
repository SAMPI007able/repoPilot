import unittest
import json
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.config.rate_limit_settings import RateLimitPolicy, RateLimitSettings
from app.models.identity_models import Principal, UserRole, UserStatus
from app.models.preview_models import PreviewEnvironment, PreviewStatus
from app.services.rate_limit_guard import RateLimitGuard
from app.services.rate_limit_service import RateLimitService
try:
    from backend.tests.test_runtime_manifest import fixture_metadata, valid_manifest
except ModuleNotFoundError:
    try:
        from tests.test_runtime_manifest import fixture_metadata, valid_manifest
    except ModuleNotFoundError:
        from test_runtime_manifest import fixture_metadata, valid_manifest
from test_rate_limit_service import FakeRedis, MutableClock


def principal(user_id: str) -> Principal:
    return Principal(
        user_id=user_id, email=f"{user_id}@example.test", display_name=user_id,
        avatar_url=None, status=UserStatus.ACTIVE, role=UserRole.USER, email_verified=True,
    )


def quota_settings() -> RateLimitSettings:
    policies = {
        action: RateLimitPolicy(limit, 60)
        for action, limit in {
            "repository_index": 5, "ai_generation": 1, "project_chat": 1,
            "document_upload": 10, "preview_creation": 5, "preview_extension": 20,
            "browser_session_creation": 20, "screenshot_generation": 50,
        }.items()
    }
    return RateLimitSettings(
        enabled=True, environment="test", redis_url="redis://unused", policies=policies,
        active_previews_per_user=1, active_browser_sessions_per_user=1,
        concurrency_ttl_seconds=120,
    )


class FakeAIService:
    def chat(self, metadata, query, history=None):
        del metadata, query, history
        return "prompt", "answer"

    def stream_chat(self, metadata, query, history=None):
        del metadata, query, history
        return "prompt", iter(["streamed ", "answer"])


class FakeChatPersistence:
    def __init__(self):
        self.exchanges = []

    def create(self, user_id, workspace_id):
        return SimpleNamespace(id=f"session-{user_id}-{workspace_id}")

    def get(self, session_id, user_id, workspace_id):
        del user_id, workspace_id
        return SimpleNamespace(id=session_id)

    def context(self, session_id, user_id, workspace_id):
        del session_id, user_id, workspace_id
        return []

    def append_exchange(self, session_id, user_id, workspace_id, question, answer):
        self.exchanges.append((session_id, user_id, workspace_id, question, answer))


class FakePreviewPersistence:
    def __init__(self):
        self.active: dict[str, list[str]] = {}
        self.by_idempotency = {}

    def find_by_idempotency(self, workspace_id, key):
        return self.by_idempotency.get((workspace_id, key))

    def active_ids_for_user(self, user_id):
        return list(self.active.get(user_id, []))

    def is_owned_by(self, preview_id, user_id):
        return preview_id in self.active.get(user_id, [])


class FakePreviewService:
    def __init__(self, persistence: FakePreviewPersistence, user_id: str):
        self.persistence = persistence
        self.user_id = user_id
        self.count = 0

    def create(self, workspace_id, idempotency_key, payload, repository_authorization=None):
        del payload
        self.count += 1
        preview = preview_model(f"preview-{self.count}", workspace_id, PreviewStatus.QUEUED)
        self.persistence.active.setdefault(self.user_id, []).append(preview.id)
        self.persistence.by_idempotency[(workspace_id, idempotency_key)] = preview
        return preview

    def stop(self, preview_id):
        self.persistence.active[self.user_id].remove(preview_id)
        return preview_model(preview_id, "workspace", PreviewStatus.STOPPING)


def preview_model(preview_id: str, workspace_id: str, status: PreviewStatus) -> PreviewEnvironment:
    now = datetime.now(timezone.utc)
    return PreviewEnvironment(
        id=preview_id, workspaceId=workspace_id, status=status,
        repositoryUrl="https://example.test/repository.git", commitSha="a" * 40,
        manifestRevision=1, manifest=valid_manifest(), expiresAt=now + timedelta(minutes=30),
        maximumExpiresAt=now + timedelta(hours=2), createdAt=now, updatedAt=now,
    )


class RateLimitAPITests(unittest.TestCase):
    def setUp(self):
        self.clock = MutableClock(100)
        self.redis = FakeRedis(self.clock)
        self.settings = quota_settings()
        self.service = RateLimitService(self.settings, self.redis, self.clock)
        self.guard = RateLimitGuard(self.service, self.settings)
        self.client = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_ai_limit_returns_429_and_different_user_is_independent(self):
        current = {"principal": principal("user-one")}
        main.app.dependency_overrides[main.auth.active_principal] = lambda: current["principal"]
        with patch.object(main, "rate_limit_service", self.service), patch.object(
            main, "rate_limit_guard", self.guard,
        ), patch.object(main, "_load_workspace", return_value=("", fixture_metadata())), patch.object(
            main, "ai_service", FakeAIService(),
        ), patch.object(
            main, "chat_persistence_service", FakeChatPersistence(),
        ), patch.object(
            main.admin_service, "record_usage",
        ):
            first = self.client.post("/ai/query", json={"type": "chat", "workspaceId": "workspace", "query": "hello"})
            rejected = self.client.post("/ai/query", json={"type": "chat", "workspaceId": "workspace", "query": "again"})
            current["principal"] = principal("user-two")
            independent = self.client.post("/ai/query", json={"type": "chat", "workspaceId": "workspace", "query": "hello"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(rejected.status_code, 429)
        self.assertEqual(rejected.json()["code"], "RATE_LIMIT_EXCEEDED")
        self.assertIn("X-RateLimit-Reset", rejected.headers)
        self.assertEqual(independent.status_code, 200)

    def test_chat_stream_emits_deltas_and_persists_completed_answer(self):
        user = principal("stream-user")
        persistence = FakeChatPersistence()
        main.app.dependency_overrides[main.auth.active_principal] = lambda: user
        with patch.object(main, "rate_limit_service", self.service), patch.object(
            main, "rate_limit_guard", self.guard,
        ), patch.object(main, "_load_workspace", return_value=("", fixture_metadata())), patch.object(
            main, "ai_service", FakeAIService(),
        ), patch.object(
            main, "chat_persistence_service", persistence,
        ), patch.object(main.admin_service, "record_usage"), patch.object(
            main.telemetry, "capture",
        ):
            response = self.client.post(
                "/ai/query/stream",
                json={"type": "chat", "workspaceId": "workspace", "query": "hello"},
            )

        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/x-ndjson")
        self.assertEqual([item["type"] for item in events], ["metadata", "delta", "delta", "done"])
        self.assertEqual("".join(item.get("text", "") for item in events), "streamed answer")
        self.assertEqual(persistence.exchanges[-1][-1], "streamed answer")

    def test_preview_concurrency_blocks_then_stop_releases(self):
        user = principal("preview-user")
        main.app.dependency_overrides[main.auth.active_principal] = lambda: user
        persistence = FakePreviewPersistence()
        preview_service = FakePreviewService(persistence, user.user_id)
        with patch.object(main, "rate_limit_service", self.service), patch.object(
            main, "rate_limit_guard", self.guard,
        ), patch.object(
            main.feature_flag_service, "is_enabled", return_value=True,
        ), patch.object(main, "preview_persistence_service", persistence), patch.object(
            main, "preview_service", preview_service,
        ), patch.object(main, "_authorize_workspace"):
            first = self.client.post(
                "/workspaces/workspace/previews", json={"environment": {}},
                headers={"Idempotency-Key": "first"},
            )
            rejected = self.client.post(
                "/workspaces/workspace/previews", json={"environment": {}},
                headers={"Idempotency-Key": "second"},
            )
            stopped = self.client.post(
                "/previews/preview-1/stop", headers={"Idempotency-Key": "stop"},
            )
            after_stop = self.client.post(
                "/workspaces/workspace/previews", json={"environment": {}},
                headers={"Idempotency-Key": "third"},
            )

        self.assertEqual(first.status_code, 202)
        self.assertEqual(rejected.status_code, 429)
        self.assertEqual(rejected.json()["code"], "CONCURRENCY_LIMIT_EXCEEDED")
        self.assertEqual(stopped.status_code, 202)
        self.assertEqual(after_stop.status_code, 202)


if __name__ == "__main__":
    unittest.main()
