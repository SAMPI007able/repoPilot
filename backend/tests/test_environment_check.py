import os
import unittest
from unittest.mock import patch

from app.scripts.check_environment import validate


class EnvironmentCheckTests(unittest.TestCase):
    def test_complete_backend_environment_passes(self):
        environment = {
            "APP_ENV": "production",
            "FRONTEND_URL": "https://app.example.test",
            "OAUTH_CALLBACK_BASE_URL": "https://api.example.test",
            "CORS_ORIGINS": "https://app.example.test",
            "GEMINI_API_KEY": "configured",
            "DATABASE_URL": "postgresql://example",
            "REDIS_URL": "rediss://example",
            "AUTH_MODE": "oidc",
            "OIDC_ISSUER": "https://tenant.example.test/",
            "OIDC_AUDIENCE": "https://api.example.test",
            "OIDC_JWKS_URL": "https://tenant.example.test/.well-known/jwks.json",
            "ARTIFACT_STORE": "s3",
            "ARTIFACT_S3_BUCKET": "bucket",
            "ARTIFACT_S3_REGION": "us-east-1",
            "ARTIFACT_S3_ACCESS_KEY_ID": "configured",
            "ARTIFACT_S3_SECRET_ACCESS_KEY": "configured",
            "PREVIEW_TRUSTED_LOCAL_EXECUTION": "false",
            "POSTHOG_API_KEY": "configured",
        }
        with patch.dict(os.environ, environment, clear=True):
            errors, warnings = validate("backend")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unsafe_production_defaults_fail(self):
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "DATABASE_URL": "sqlite:///local.db",
            "REDIS_URL": "http://not-redis",
            "ARTIFACT_STORE": "local",
            "PREVIEW_TRUSTED_LOCAL_EXECUTION": "true",
        }, clear=True):
            errors, _ = validate("backend")
        self.assertTrue(any("DATABASE_URL" in error for error in errors))
        self.assertTrue(any("ARTIFACT_STORE" in error for error in errors))
        self.assertTrue(any("PREVIEW_TRUSTED_LOCAL_EXECUTION" in error for error in errors))

    def test_openai_provider_requires_openai_key_instead_of_gemini(self):
        environment = {
            "AI_PROVIDER": "openai",
            "OPENAI_API_KEY": "configured",
        }
        with patch.dict(os.environ, environment, clear=True):
            errors, _ = validate("backend")
        self.assertFalse(any("OPENAI_API_KEY" in error for error in errors))
        self.assertFalse(any("GEMINI_API_KEY" in error for error in errors))

    def test_qwen_provider_accepts_dashscope_key_alias(self):
        environment = {
            "AI_PROVIDER": "qwen",
            "DASHSCOPE_API_KEY": "configured",
            "QWEN_BASE_URL": "https://workspace.example/compatible-mode/v1",
        }
        with patch.dict(os.environ, environment, clear=True):
            errors, _ = validate("backend")
        self.assertFalse(any("QWEN_API_KEY" in error for error in errors))
        self.assertFalse(any("GEMINI_API_KEY" in error for error in errors))

    def test_openrouter_provider_requires_only_openrouter_key(self):
        environment = {
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "sk-or-configured",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        }
        with patch.dict(os.environ, environment, clear=True):
            errors, _ = validate("backend")
        self.assertFalse(any("OPENROUTER_API_KEY" in error for error in errors))
        self.assertFalse(any("QWEN_API_KEY" in error for error in errors))

    def test_preview_worker_requires_a_separate_acknowledged_sandbox_environment(self):
        environment = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://example",
            "REDIS_URL": "rediss://example",
            "ARTIFACT_STORE": "s3",
            "ARTIFACT_S3_BUCKET": "bucket",
            "ARTIFACT_S3_REGION": "us-east-1",
            "PREVIEW_PROVIDER": "railway-sandbox",
            "PREVIEW_TRUSTED_LOCAL_EXECUTION": "false",
            "RAILWAY_API_TOKEN": "configured",
            "RAILWAY_ENVIRONMENT_ID": "production-environment",
            "RAILWAY_SANDBOX_ENVIRONMENT_ID": "sandbox-environment",
            "PREVIEW_RAILWAY_ACKNOWLEDGE_DEDICATED_ENVIRONMENT": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            errors, _ = validate("preview-worker")
        self.assertEqual(errors, [])

        environment["RAILWAY_SANDBOX_ENVIRONMENT_ID"] = "production-environment"
        with patch.dict(os.environ, environment, clear=True):
            errors, _ = validate("preview-worker")
        self.assertTrue(any("must differ" in error for error in errors))

    def test_verification_resend_requires_management_credentials_when_enabled(self):
        environment = {
            "AUTH0_VERIFICATION_RESEND_ENABLED": "true",
            "AUTH0_MANAGEMENT_CLIENT_ID": "configured",
        }
        with patch.dict(os.environ, environment, clear=True):
            errors, _ = validate("backend")
        self.assertTrue(any("AUTH0_MANAGEMENT_CLIENT_SECRET" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
