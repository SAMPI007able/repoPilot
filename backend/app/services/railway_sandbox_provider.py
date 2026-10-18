import json
import os
import subprocess

from app.models.preview_models import PreviewStatus
from app.services.sandbox_provider import SandboxExecutionError, SandboxResult


class RailwaySandboxProvider:
    """Production preview provider backed by Railway's isolated Sandbox VMs."""

    PROVIDER_NAME = "railway-sandbox"

    def __init__(self, bridge_path: str | None = None) -> None:
        self.bridge_path = bridge_path or os.getenv(
            "PREVIEW_RAILWAY_BRIDGE_PATH", "/app/sandbox-runtime/bridge.mjs"
        )
        self._validate_configuration()

    def deploy(
        self, preview, environment, transition, log,
        repository_authorization: str | None = None,
    ) -> SandboxResult:
        payload = {
            "action": "deploy",
            "repositoryUrl": preview.repository_url,
            "commitSha": preview.commit_sha,
            "manifest": preview.manifest.model_dump(by_alias=True),
            "environment": environment,
            "repositoryAuthorization": repository_authorization,
        }
        result = self._run_bridge(payload, transition, log)
        return SandboxResult(
            preview_url=result["previewUrl"],
            internal_url=result.get("internalUrl", result["previewUrl"]),
            provider_state=result["providerState"],
        )

    def cleanup(self, provider_state: dict, log) -> None:
        self._run_bridge(
            {"action": "cleanup", "providerState": provider_state},
            lambda *_args: None,
            log,
        )

    def _run_bridge(self, payload: dict, transition, log) -> dict:
        try:
            process = subprocess.Popen(
                ["node", self.bridge_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=os.environ.copy(),
            )
        except Exception as exc:
            raise SandboxExecutionError(
                "SANDBOX_UNAVAILABLE", "The Railway Sandbox bridge could not start."
            ) from exc

        assert process.stdin is not None
        assert process.stdout is not None
        process.stdin.write(json.dumps(payload, ensure_ascii=False))
        process.stdin.close()
        result: dict | None = None
        bridge_error: str | None = None
        for raw_line in process.stdout:
            line = raw_line.rstrip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                log(line)
                continue
            event_type = event.get("type")
            if event_type == "log":
                log(str(event.get("text", "")))
            elif event_type == "transition":
                transition(
                    PreviewStatus(event["status"]),
                    str(event.get("message", "Preview stage changed.")),
                    event.get("state"),
                )
            elif event_type == "result":
                result = event
            elif event_type == "error":
                bridge_error = str(event.get("message", "Railway Sandbox operation failed."))
        return_code = process.wait()
        if return_code != 0 or bridge_error:
            raise SandboxExecutionError(
                "SANDBOX_DEPLOY_FAILED",
                bridge_error or "The Railway Sandbox operation failed.",
            )
        if result is None:
            raise SandboxExecutionError(
                "SANDBOX_DEPLOY_FAILED", "The Railway Sandbox bridge returned no result."
            )
        return result

    @staticmethod
    def _validate_configuration() -> None:
        missing = [
            name for name in ("RAILWAY_API_TOKEN", "RAILWAY_SANDBOX_ENVIRONMENT_ID")
            if not os.getenv(name, "").strip()
        ]
        if missing:
            raise SandboxExecutionError(
                "SANDBOX_CONFIGURATION_INVALID",
                f"Missing Railway Sandbox configuration: {', '.join(missing)}.",
            )
        if os.getenv(
            "PREVIEW_RAILWAY_ACKNOWLEDGE_DEDICATED_ENVIRONMENT", "false"
        ).lower() != "true":
            raise SandboxExecutionError(
                "SANDBOX_CONFIGURATION_INVALID",
                "Railway previews require an explicitly acknowledged dedicated sandbox environment.",
            )
