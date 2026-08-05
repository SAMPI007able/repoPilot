import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.models.identity_models import TokenClaims, UserStatus
from app.persistence.database import Database
from app.persistence.identity_persistence_service import IdentityPersistenceService
from app.persistence.artifact_store import LocalArtifactStore
from app.persistence.workspace_persistence_service import WorkspacePersistenceService
from app.services.authentication import DevelopmentTokenVerifier, OIDCTokenVerifier


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        path = os.path.join(self.temp.name, "identity.db").replace("\\", "/")
        self.database = Database(f"sqlite:///{path}")
        self.database.create_schema()
        self.identities = IdentityPersistenceService(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_issuer_and_subject_map_stably_to_internal_user(self) -> None:
        claims = TokenClaims(
            issuer="https://issuer.example", subject="subject-1",
            email="User@Example.com", email_verified=True,
        )
        first = self.identities.authenticate(claims)
        second = self.identities.authenticate(claims)

        self.assertEqual(first.user_id, second.user_id)
        self.assertEqual("user@example.com", first.email)
        self.assertEqual(UserStatus.ACTIVE, first.status)

    def test_same_email_does_not_implicitly_link_different_subject(self) -> None:
        first = self.identities.authenticate(TokenClaims(
            issuer="https://issuer.example", subject="one",
            email="user@example.com", email_verified=True,
        ))
        second = self.identities.authenticate(TokenClaims(
            issuer="https://issuer.example", subject="two",
            email="user@example.com", email_verified=True,
        ))
        self.assertNotEqual(first.user_id, second.user_id)

    def test_unverified_email_is_preserved(self) -> None:
        principal = self.identities.authenticate(TokenClaims(
            issuer="https://issuer.example", subject="pending",
            email="pending@example.com", email_verified=False,
        ))
        self.assertEqual(UserStatus.PENDING_VERIFICATION, principal.status)

    def test_development_token_verification_is_exact(self) -> None:
        verifier = DevelopmentTokenVerifier("expected", "developer@example.com")
        self.assertEqual("developer@example.com", verifier.verify("expected").email)
        with self.assertRaises(Exception):
            verifier.verify("wrong")

    def test_oidc_verifier_requires_the_configured_api_audience(self) -> None:
        verifier = OIDCTokenVerifier(
            issuer="https://issuer.example",
            audience="https://api.example.com",
            jwks_url="https://issuer.example/.well-known/jwks.json",
        )

        self.assertFalse(verifier._audience_matches({"aud": "client-id", "azp": "client-id"}))
        self.assertTrue(verifier._audience_matches({"aud": ["https://api.example.com", "client-id"], "azp": "client-id"}))
        self.assertFalse(verifier._audience_matches({"aud": "another-client"}))

    def test_oidc_verifier_rejects_auth0_opaque_token_with_actionable_error(self) -> None:
        verifier = OIDCTokenVerifier(
            issuer="https://issuer.example", audience="https://api.example.com",
            jwks_url="https://issuer.example/.well-known/jwks.json",
        )
        with self.assertRaises(Exception) as context:
            verifier.verify("header..iv.ciphertext.tag")
        self.assertEqual("AUTH_TOKEN_AUDIENCE_REQUIRED", context.exception.code)

    def test_oidc_verifier_enriches_valid_jwt_from_matching_userinfo(self) -> None:
        verifier = OIDCTokenVerifier(
            issuer="https://issuer.example", audience="https://api.example.com",
            jwks_url="https://issuer.example/.well-known/jwks.json",
        )
        verifier.jwks_client.get_signing_key_from_jwt = Mock(return_value=Mock(key="public-key"))
        jwt_payload = {
            "iss": "https://issuer.example/", "sub": "auth0|one",
            "aud": "https://api.example.com", "exp": 9999999999, "iat": 1,
        }
        with patch("app.services.authentication.jwt.decode", return_value=jwt_payload), patch.object(
            verifier, "_userinfo", return_value={
                "sub": "auth0|one", "email": "user@example.com",
                "email_verified": True, "name": "Test User",
            },
        ):
            claims = verifier.verify("header.payload.signature")
        self.assertEqual("auth0|one", claims.subject)
        self.assertEqual("user@example.com", claims.email)
        self.assertTrue(claims.email_verified)

    def test_workspace_queries_are_scoped_to_internal_owner(self) -> None:
        service = WorkspacePersistenceService(
            self.database, LocalArtifactStore(os.path.join(self.temp.name, "artifacts"))
        )
        first = self.identities.authenticate(TokenClaims(
            issuer="https://issuer.example", subject="owner-1",
            email="one@example.com", email_verified=True,
        ))
        second = self.identities.authenticate(TokenClaims(
            issuer="https://issuer.example", subject="owner-2",
            email="two@example.com", email_verified=True,
        ))
        workspace = service.create_workspace(
            "https://github.com/example/one", "one", first.user_id
        )

        self.assertEqual([workspace.id], [item.id for item in service.list_workspaces(first.user_id)])
        self.assertEqual([], service.list_workspaces(second.user_id))
        self.assertTrue(service.owns_workspace(workspace.id, first.user_id))
        self.assertFalse(service.owns_workspace(workspace.id, second.user_id))


class AuthenticationAPITests(unittest.TestCase):
    def test_me_rejects_unauthenticated_and_maps_authenticated_user(self) -> None:
        from app.main import app

        client = TestClient(app)
        unauthenticated = client.get("/me")
        protected = client.post(
            "/workspaces/index", json={"githubUrl": "https://github.com/example/repository"}
        )
        protected = client.post(
            "/workspaces/index", json={"githubUrl": "https://github.com/example/repository"}
        )
        authenticated = client.get(
            "/me", headers={"Authorization": "Bearer testforge-test-development"}
        )

        self.assertEqual(401, unauthenticated.status_code)
        self.assertEqual("AUTH_REQUIRED", unauthenticated.json()["code"])
        self.assertEqual(401, protected.status_code)
        self.assertEqual("AUTH_REQUIRED", protected.json()["code"])
        self.assertEqual(401, protected.status_code)
        self.assertEqual("AUTH_REQUIRED", protected.json()["code"])
        self.assertEqual(200, authenticated.status_code)
        self.assertEqual("developer@testforge.local", authenticated.json()["primaryEmail"])


if __name__ == "__main__":
    unittest.main()
