import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from app.models.identity_models import TokenClaims
from app.persistence.database import Database
from app.persistence.identity_persistence_service import IdentityPersistenceService
from app.persistence.oauth_persistence_service import OAuthPersistenceService
from app.services.oauth_integrations import OAuthIntegrationService


class OAuthIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        path = os.path.join(self.temp.name, "oauth.db").replace("\\", "/")
        self.database = Database(f"sqlite:///{path}")
        self.database.create_schema()
        identities = IdentityPersistenceService(self.database)
        self.first = identities.authenticate(TokenClaims(
            issuer="test", subject="first", email="first@example.com", email_verified=True,
        ))
        self.second = identities.authenticate(TokenClaims(
            issuer="test", subject="second", email="second@example.com", email_verified=True,
        ))
        self.persistence = OAuthPersistenceService(self.database)

    def tearDown(self) -> None:
        self.database.close()
        self.temp.cleanup()

    def test_state_is_user_bound_single_use_and_expires_from_storage(self) -> None:
        self.persistence.create_state("state-value", self.first.user_id, "github")
        self.assertIsNone(self.persistence.consume_state("state-value", "gitlab"))
        self.assertEqual(self.first.user_id, self.persistence.consume_state("state-value", "github"))
        self.assertIsNone(self.persistence.consume_state("state-value", "github"))

    def test_connections_are_isolated_by_internal_user(self) -> None:
        self.persistence.upsert_connection(
            user_id=self.first.user_id, provider="github", access_token="ciphertext",
            refresh_token=None, token_type="Bearer", scopes=["repo"],
            external_account_id="1", external_account_name="octocat",
            external_avatar_url=None, expires_at=None,
        )
        self.assertIsNotNone(self.persistence.get_connection(self.first.user_id, "github"))
        self.assertIsNone(self.persistence.get_connection(self.second.user_id, "github"))

    def test_authorization_url_has_callback_scope_and_persisted_state(self) -> None:
        environment = {
            "OAUTH_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "GITHUB_OAUTH_CLIENT_ID": "client-id",
            "GITHUB_OAUTH_CLIENT_SECRET": "client-secret",
        }
        with patch.dict(os.environ, environment, clear=False):
            service = OAuthIntegrationService(self.persistence)
            url = service.authorization_url("github", self.first.user_id)
        query = parse_qs(urlparse(url).query)
        self.assertEqual(["client-id"], query["client_id"])
        self.assertEqual(["http://127.0.0.1:8000/integrations/github/callback"], query["redirect_uri"])
        self.assertEqual({"repo", "read:user"}, set(query["scope"][0].split()))
        self.assertEqual(self.first.user_id, self.persistence.consume_state(query["state"][0], "github"))

    def test_callback_encrypts_token_and_rejects_state_replay(self) -> None:
        environment = {
            "OAUTH_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "GITHUB_OAUTH_CLIENT_ID": "client-id",
            "GITHUB_OAUTH_CLIENT_SECRET": "client-secret",
        }
        with patch.dict(os.environ, environment, clear=False):
            service = OAuthIntegrationService(self.persistence)
            state = parse_qs(urlparse(service.authorization_url("github", self.first.user_id)).query)["state"][0]
            with patch.object(service, "_exchange_code", return_value={"access_token": "plain-secret", "scope": "repo read:user"}), patch.object(
                service, "_profile", return_value={"id": 1, "login": "octocat"}
            ):
                service.complete_callback("github", "code", state)
                stored = self.persistence.get_connection(self.first.user_id, "github")
                self.assertIsNotNone(stored)
                self.assertNotIn("plain-secret", stored.access_token_ciphertext)
                with self.assertRaises(Exception):
                    service.complete_callback("github", "code", state)

    def test_bitbucket_repositories_use_supported_workspace_endpoints_and_pagination(self) -> None:
        service = OAuthIntegrationService(self.persistence)
        config = service.providers["bitbucket"]
        workspace_page_two = f"{config.api_url}/user/workspaces?page=2"
        repo_url = f"{config.api_url}/repositories/acme?pagelen=100&sort=-updated_on"
        repo_page_two = f"{config.api_url}/repositories/acme?page=2"
        responses = {
            f"{config.api_url}/user/workspaces?pagelen=100": {
                "values": [{"workspace": {"slug": "acme"}}], "next": workspace_page_two,
            },
            workspace_page_two: {"values": []},
            repo_url: {
                "values": [self._bitbucket_item("{one}", "acme/one")], "next": repo_page_two,
            },
            repo_page_two: {"values": [self._bitbucket_item("{two}", "acme/two")]},
        }
        requested: list[str] = []

        def fake_json(method: str, url: str, token: str):
            self.assertEqual("GET", method)
            self.assertEqual("access-token", token)
            requested.append(url)
            return responses[url]

        with patch.object(service, "_connection_token", return_value=(config, "access-token")), patch.object(
            service, "_json", side_effect=fake_json
        ):
            repositories = service.repositories(self.first.user_id, "bitbucket")

        self.assertEqual(["acme/one", "acme/two"], [item.full_name for item in repositories])
        self.assertEqual(
            [f"{config.api_url}/user/workspaces?pagelen=100", workspace_page_two, repo_url, repo_page_two],
            requested,
        )

    def test_bitbucket_pagination_rejects_cross_origin_next_url(self) -> None:
        service = OAuthIntegrationService(self.persistence)
        with patch.object(service, "_json", return_value={"values": [], "next": "https://example.com/token"}):
            with self.assertRaisesRegex(Exception, "invalid pagination URL"):
                service._bitbucket_paginated_values(
                    "https://api.bitbucket.org/2.0/user/workspaces", "token", "https://api.bitbucket.org/2.0"
                )

    @staticmethod
    def _bitbucket_item(identifier: str, full_name: str) -> dict:
        owner, name = full_name.split("/", 1)
        return {
            "uuid": identifier,
            "slug": name,
            "full_name": full_name,
            "workspace": {"slug": owner},
            "is_private": True,
            "mainbranch": {"name": "main"},
            "links": {
                "html": {"href": f"https://bitbucket.org/{full_name}"},
                "clone": [{"name": "https", "href": f"https://bitbucket.org/{full_name}.git"}],
            },
            "updated_on": "2026-08-02T00:00:00Z",
        }


if __name__ == "__main__":
    unittest.main()
