import os
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone

from app.models.preview_models import PreviewEnvironment
from app.services.sandbox_provider import LocalDockerSandboxProvider
from backend.tests.test_runtime_manifest import valid_manifest


@unittest.skipUnless(
    os.getenv("TESTFORGE_PREVIEW_FIXTURE_URL") and os.getenv("TESTFORGE_PREVIEW_FIXTURE_SHA"),
    "Set the Docker preview fixture URL and immutable SHA to run this integration test.",
)
class DockerPreviewIntegrationTests(unittest.TestCase):
    def test_fixture_reaches_ready_and_cleans_every_resource(self) -> None:
        import docker

        now = datetime.now(timezone.utc)
        preview = PreviewEnvironment(
            id="11111111-2222-4333-8444-555555555555",
            workspaceId="fixture",
            status="queued",
            repositoryUrl=os.environ["TESTFORGE_PREVIEW_FIXTURE_URL"],
            commitSha=os.environ["TESTFORGE_PREVIEW_FIXTURE_SHA"],
            manifestRevision=1,
            manifest=valid_manifest(),
            expiresAt=now + timedelta(minutes=20),
            maximumExpiresAt=now + timedelta(minutes=60),
            createdAt=now,
            updatedAt=now,
        )
        provider = LocalDockerSandboxProvider()
        provider_state: dict = {}
        result = None

        def transition(status, message, state):
            provider_state.update(state or {})
            print(f"{status.value}: {message}", flush=True)

        def log(text):
            if text.strip():
                print(text[-1200:], flush=True)

        try:
            result = provider.deploy(
                preview,
                {"VITE_API_URL": "https://api.example.test"},
                transition,
                log,
            )
            validation_url = result.preview_url.replace(
                "127.0.0.1", os.getenv("TESTFORGE_PREVIEW_VALIDATION_HOST", "127.0.0.1")
            )
            request = urllib.request.Request(validation_url, headers={"Host": "127.0.0.1"})
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn("TestForge Preview Fixture", body)
                print(f"HTTP_OK {result.preview_url}", flush=True)
        finally:
            provider.cleanup(result.provider_state if result else provider_state, log)

        client = docker.from_env()
        remaining = client.containers.list(
            all=True, filters={"label": f"testforge.preview_id={preview.id}"}
        )
        self.assertEqual([], remaining)
        print("CLEANUP_OK", flush=True)


if __name__ == "__main__":
    unittest.main()
