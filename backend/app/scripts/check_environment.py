"""Validate deployment environment names without printing secret values."""

import argparse
import os
import sys
from urllib.parse import urlparse


BACKEND_REQUIRED = (
    "APP_ENV",
    "FRONTEND_URL",
    "CORS_ORIGINS",
    "DATABASE_URL",
    "REDIS_URL",
    "AUTH_MODE",
)
FRONTEND_REQUIRED = (
    "VITE_API_BASE_URL",
    "VITE_AUTH_MODE",
    "VITE_OIDC_AUTHORITY",
    "VITE_OIDC_CLIENT_ID",
    "VITE_OIDC_AUDIENCE",
    "VITE_OIDC_REDIRECT_URI",
)
OIDC_REQUIRED = ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL")
S3_REQUIRED = ("ARTIFACT_S3_BUCKET", "ARTIFACT_S3_REGION")


def present(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def validate(target: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required = []
    if target in {"backend", "all"}:
        required.extend(BACKEND_REQUIRED)
    if target in {"frontend", "all"}:
        required.extend(FRONTEND_REQUIRED)
    errors.extend(f"{name} is missing" for name in required if not present(name))

    if target in {"backend", "all"}:
        default_ai_provider = os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini"
        configured_providers = {
            os.getenv("AI_CHAT_PROVIDER", "").strip().lower() or default_ai_provider,
            os.getenv("AI_GENERATION_PROVIDER", "").strip().lower() or default_ai_provider,
        }
        supported_providers = {"gemini", "openai", "openrouter", "qwen"}
        for provider in configured_providers:
            if provider not in supported_providers:
                errors.append(f"Unsupported AI provider: {provider}")
            elif provider == "gemini" and not present("GEMINI_API_KEY"):
                errors.append("GEMINI_API_KEY is missing")
            elif provider == "openai" and not present("OPENAI_API_KEY"):
                errors.append("OPENAI_API_KEY is missing")
            elif provider == "openrouter" and not present("OPENROUTER_API_KEY"):
                errors.append("OPENROUTER_API_KEY is missing")
            elif provider == "qwen" and not (
                present("QWEN_API_KEY") or present("DASHSCOPE_API_KEY")
            ):
                errors.append("QWEN_API_KEY or DASHSCOPE_API_KEY is missing")
        if "qwen" in configured_providers and not present("QWEN_BASE_URL"):
            warnings.append(
                "QWEN_BASE_URL is absent; the legacy Singapore endpoint will be used"
            )
        elif "qwen" in configured_providers and not os.environ["QWEN_BASE_URL"].startswith(
            "https://"
        ):
            errors.append("QWEN_BASE_URL must use HTTPS")
        if "openrouter" in configured_providers and present("OPENROUTER_BASE_URL"):
            if not os.environ["OPENROUTER_BASE_URL"].startswith("https://"):
                errors.append("OPENROUTER_BASE_URL must use HTTPS")
        if os.getenv("APP_ENV", "").lower() not in {"production", "staging"}:
            warnings.append("APP_ENV is not production or staging")
        if os.getenv("AUTH_MODE", "oidc").lower() != "oidc":
            errors.append("AUTH_MODE must be oidc in production")
        else:
            errors.extend(f"{name} is missing" for name in OIDC_REQUIRED if not present(name))
        if os.getenv("ARTIFACT_STORE", "local").lower() != "s3":
            errors.append("ARTIFACT_STORE must be s3 for a multi-instance deployment")
        else:
            errors.extend(f"{name} is missing" for name in S3_REQUIRED if not present(name))
            if not present("ARTIFACT_S3_ACCESS_KEY_ID") or not present("ARTIFACT_S3_SECRET_ACCESS_KEY"):
                warnings.append("S3 static credentials are absent; the runtime must provide an AWS credential chain")
        if not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
            errors.append("DATABASE_URL must use PostgreSQL in production")
        if not os.getenv("REDIS_URL", "").startswith(("redis://", "rediss://")):
            errors.append("REDIS_URL must use redis:// or rediss://")
        if os.getenv("PREVIEW_TRUSTED_LOCAL_EXECUTION", "false").lower() == "true":
            errors.append("PREVIEW_TRUSTED_LOCAL_EXECUTION must be false in production")
        if not present("POSTHOG_API_KEY"):
            warnings.append("POSTHOG_API_KEY is absent; backend analytics will be disabled")
        provider_configured = any(present(f"{provider}_OAUTH_CLIENT_ID") for provider in ("GITHUB", "GITLAB", "BITBUCKET"))
        if provider_configured and not present("OAUTH_TOKEN_ENCRYPTION_KEY"):
            errors.append("OAUTH_TOKEN_ENCRYPTION_KEY is required when source-control OAuth is configured")
        if provider_configured and not present("OAUTH_CALLBACK_BASE_URL"):
            errors.append("OAUTH_CALLBACK_BASE_URL is required when source-control OAuth is configured")
        if "*" in {origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",")}:
            errors.append("CORS_ORIGINS must contain explicit origins, not *")

    if target in {"frontend", "all"}:
        if not present("VITE_POSTHOG_API_KEY"):
            warnings.append("VITE_POSTHOG_API_KEY is absent; frontend analytics will be disabled")

    for name in ("FRONTEND_URL", "OAUTH_CALLBACK_BASE_URL", "VITE_API_BASE_URL", "VITE_OIDC_REDIRECT_URI"):
        if present(name) and urlparse(os.environ[name]).scheme != "https":
            if os.getenv("APP_ENV", "").lower() == "production":
                errors.append(f"{name} must use HTTPS in production")
            else:
                warnings.append(f"{name} is not HTTPS")
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate TestForge deployment environment variables.")
    parser.add_argument("--target", choices=("backend", "frontend", "all"), default="backend")
    args = parser.parse_args()
    errors, warnings = validate(args.target)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"Environment check failed with {len(errors)} error(s).")
        return 1
    print(f"Environment check passed for {args.target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
