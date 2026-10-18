import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from app.services.email_verification_service import (
    Auth0EmailVerificationService,
    Auth0VerificationSettings,
    EmailVerificationError,
)


class _Response:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class EmailVerificationServiceTests(unittest.TestCase):
    def settings(self, **overrides) -> Auth0VerificationSettings:
        values = {
            "enabled": True,
            "issuer": "https://tenant.example/",
            "management_client_id": "management-client",
            "management_client_secret": "management-secret",
            "application_client_id": "application-client",
        }
        values.update(overrides)
        return Auth0VerificationSettings(**values)

    def test_sends_job_for_authenticated_subject_and_reuses_management_token(self):
        requests = []

        def open_request(request, timeout):
            self.assertEqual(timeout, 10)
            requests.append(request)
            if request.full_url.endswith("oauth/token"):
                return _Response({"access_token": "token", "expires_in": 3600})
            return _Response()

        service = Auth0EmailVerificationService(self.settings())
        with patch("urllib.request.urlopen", side_effect=open_request):
            service.send("auth0|user-one")
            service.send("auth0|user-one")

        self.assertEqual(3, len(requests))
        jobs = [request for request in requests if request.full_url.endswith("verification-email")]
        self.assertEqual(2, len(jobs))
        self.assertEqual({
            "user_id": "auth0|user-one",
            "client_id": "application-client",
        }, json.loads(jobs[0].data.decode("utf-8")))
        self.assertEqual("Bearer token", jobs[0].headers["Authorization"])

    def test_disabled_service_fails_without_network_call(self):
        service = Auth0EmailVerificationService(self.settings(enabled=False))
        with patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(EmailVerificationError) as raised:
                service.send("auth0|user-one")
        self.assertEqual("VERIFICATION_EMAIL_RESEND_DISABLED", raised.exception.code)
        urlopen.assert_not_called()

    def test_provider_rate_limit_is_safe_and_retryable(self):
        rate_limit = urllib.error.HTTPError(
            "https://tenant.example/api/v2/jobs/verification-email",
            429,
            "limited",
            {},
            io.BytesIO(b"{}"),
        )
        service = Auth0EmailVerificationService(self.settings())
        with patch("urllib.request.urlopen", side_effect=[
            _Response({"access_token": "token", "expires_in": 3600}),
            rate_limit,
        ]):
            with self.assertRaises(EmailVerificationError) as raised:
                service.send("auth0|user-one")
        self.assertEqual(429, raised.exception.status_code)
        self.assertTrue(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
