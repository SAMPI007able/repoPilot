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


if __name__ == "__main__":
    unittest.main()
