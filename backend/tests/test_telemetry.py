from app.services.telemetry import Telemetry


def test_capture_is_noop_without_configuration(monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    telemetry = Telemetry()

    telemetry.capture("user-1", "user_registered", {"source": "unit-test"})


def test_capture_is_noop_when_posthog_is_unavailable(monkeypatch):
    monkeypatch.setenv("POSTHOG_API_KEY", "test-key")
    telemetry = Telemetry()

    telemetry.capture("user-1", "repo_indexed", {"repo": "example/repo"})
