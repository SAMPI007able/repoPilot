import os

from app.services.railway_sandbox_provider import RailwaySandboxProvider
from app.services.sandbox_provider import LocalDockerSandboxProvider, SandboxExecutionError


def configured_preview_provider() -> str:
    return os.getenv("PREVIEW_PROVIDER", "local-docker").strip().lower()


def create_sandbox_provider(provider_name: str | None = None):
    provider = (provider_name or configured_preview_provider()).strip().lower()
    if provider == "local-docker":
        return LocalDockerSandboxProvider()
    if provider == RailwaySandboxProvider.PROVIDER_NAME:
        return RailwaySandboxProvider()
    raise SandboxExecutionError(
        "SANDBOX_CONFIGURATION_INVALID", f"Unsupported preview provider '{provider}'."
    )
