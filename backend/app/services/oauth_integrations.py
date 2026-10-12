import base64
import json
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken

from app.models.integration_models import ProviderConnection, ProviderRepository, RepositoryContent
from app.persistence.oauth_persistence_service import OAuthPersistenceService


class IntegrationError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    api_url: str
    scopes: tuple[str, ...]

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


class OAuthIntegrationService:
    def __init__(self, persistence: OAuthPersistenceService) -> None:
        self.persistence = persistence
        key = os.getenv("OAUTH_TOKEN_ENCRYPTION_KEY", "")
        self.cipher = Fernet(key.encode("ascii")) if key else None
        self.callback_base = os.getenv("OAUTH_CALLBACK_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        self.frontend_url = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
        self.providers = {
            "github": ProviderConfig("github", "GitHub", os.getenv("GITHUB_OAUTH_CLIENT_ID", ""), os.getenv("GITHUB_OAUTH_CLIENT_SECRET", ""), "https://github.com/login/oauth/authorize", "https://github.com/login/oauth/access_token", "https://api.github.com", ("repo", "read:user")),
            "gitlab": ProviderConfig("gitlab", "GitLab", os.getenv("GITLAB_OAUTH_CLIENT_ID", ""), os.getenv("GITLAB_OAUTH_CLIENT_SECRET", ""), "https://gitlab.com/oauth/authorize", "https://gitlab.com/oauth/token", "https://gitlab.com/api/v4", ("read_user", "api", "read_repository")),
            "bitbucket": ProviderConfig("bitbucket", "Bitbucket", os.getenv("BITBUCKET_OAUTH_CLIENT_ID", ""), os.getenv("BITBUCKET_OAUTH_CLIENT_SECRET", ""), "https://bitbucket.org/site/oauth2/authorize", "https://bitbucket.org/site/oauth2/access_token", "https://api.bitbucket.org/2.0", ("account", "repository")),
        }

    def statuses(self, user_id: str) -> list[ProviderConnection]:
        connected = {row.provider: row for row in self.persistence.list_connections(user_id)}
        return [ProviderConnection(
            provider=config.id, name=config.name, configured=config.configured and self.cipher is not None,
            connected=config.id in connected,
            accountName=connected[config.id].external_account_name if config.id in connected else None,
            avatarUrl=connected[config.id].external_avatar_url if config.id in connected else None,
        ) for config in self.providers.values()]

    def authorization_url(self, provider: str, user_id: str) -> str:
        config = self._config(provider)
        self._require_ready(config)
        state = secrets.token_urlsafe(32)
        self.persistence.create_state(state, user_id, provider)
        query = {
            "client_id": config.client_id, "redirect_uri": self._callback(provider),
            "response_type": "code", "state": state, "scope": " ".join(config.scopes),
        }
        return f"{config.authorize_url}?{urllib.parse.urlencode(query)}"

    def complete_callback(self, provider: str, code: str, state: str) -> str:
        config = self._config(provider)
        self._require_ready(config)
        user_id = self.persistence.consume_state(state, provider)
        if user_id is None:
            raise IntegrationError(400, "The OAuth state is invalid or expired. Start the connection again.")
        token = self._exchange_code(config, code)
        profile = self._profile(config, token["access_token"])
        expires_at = None
        if token.get("expires_in"):
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
        self.persistence.upsert_connection(
            user_id=user_id, provider=provider,
            access_token=self._encrypt(token["access_token"]),
            refresh_token=self._encrypt(token["refresh_token"]) if token.get("refresh_token") else None,
            token_type=token.get("token_type", "Bearer"), scopes=self._scopes(token, config),
            external_account_id=str(profile.get("id") or profile.get("uuid") or profile.get("account_id") or ""),
            external_account_name=profile.get("login") or profile.get("username") or profile.get("display_name") or profile.get("name"),
            external_avatar_url=profile.get("avatar_url") or (profile.get("links", {}).get("avatar", {}).get("href")),
            expires_at=expires_at,
        )
        return f"{self.frontend_url}/repositories?integration={urllib.parse.quote(provider)}&status=connected"

    def repositories(self, user_id: str, provider: str) -> list[ProviderRepository]:
        config, token = self._connection_token(user_id, provider)
        if provider == "github":
            items = self._json("GET", f"{config.api_url}/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator,organization_member", token)
            return [self._github_repo(item) for item in items]
        if provider == "gitlab":
            items = self._json("GET", f"{config.api_url}/projects?membership=true&simple=true&per_page=100&order_by=last_activity_at", token)
            return [self._gitlab_repo(item) for item in items]
        workspace_access = self._bitbucket_paginated_values(
            f"{config.api_url}/user/workspaces?pagelen=100", token, config.api_url
        )
        repositories: dict[str, ProviderRepository] = {}
        for access in workspace_access:
            workspace = access.get("workspace") if isinstance(access, dict) else None
            slug = workspace.get("slug") if isinstance(workspace, dict) else None
            if not slug:
                continue
            safe_workspace = urllib.parse.quote(str(slug), safe="")
            items = self._bitbucket_paginated_values(
                f"{config.api_url}/repositories/{safe_workspace}?pagelen=100&sort=-updated_on",
                token,
                config.api_url,
            )
            for item in items:
                repository = self._bitbucket_repo(item)
                repositories[repository.id] = repository
        return list(repositories.values())

    def repository(self, user_id: str, provider: str, owner: str, repo: str) -> ProviderRepository:
        match = next((item for item in self.repositories(user_id, provider) if item.owner == owner and item.name == repo), None)
        if match is None:
            raise IntegrationError(404, "The repository is not available through this connection.")
        return match

    def branches(self, user_id: str, provider: str, owner: str, repo: str) -> list[str]:
        config, token = self._connection_token(user_id, provider)
        safe_owner = urllib.parse.quote(owner, safe="")
        safe_repo = urllib.parse.quote(repo, safe="")
        if provider == "github":
            items = self._json(
                "GET",
                f"{config.api_url}/repos/{safe_owner}/{safe_repo}/branches?per_page=100",
                token,
            )
        elif provider == "gitlab":
            project = urllib.parse.quote(f"{owner}/{repo}", safe="")
            items = self._json(
                "GET",
                f"{config.api_url}/projects/{project}/repository/branches?per_page=100",
                token,
            )
        else:
            items = self._bitbucket_paginated_values(
                f"{config.api_url}/repositories/{safe_owner}/{safe_repo}/refs/branches?pagelen=100",
                token,
                config.api_url,
            )
        names = {
            str(item.get("name"))
            for item in items
            if isinstance(item, dict) and item.get("name")
        }
        return sorted(names, key=str.casefold)

    def content(self, user_id: str, provider: str, owner: str, repo: str, path: str, ref: str | None) -> RepositoryContent:
        config, token = self._connection_token(user_id, provider)
        safe_path = urllib.parse.quote(path.strip("/"), safe="/")
        branch = ref or self.repository(user_id, provider, owner, repo).default_branch
        if provider == "github":
            payload = self._json("GET", f"{config.api_url}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/contents/{safe_path}?ref={urllib.parse.quote(branch)}", token)
            if not isinstance(payload, dict) or payload.get("type") != "file":
                raise IntegrationError(400, "The requested path is not a file.")
            return RepositoryContent(path=path, content=payload.get("content", "").replace("\n", ""), encoding="base64")
        if provider == "gitlab":
            project = urllib.parse.quote(f"{owner}/{repo}", safe="")
            payload = self._json("GET", f"{config.api_url}/projects/{project}/repository/files/{urllib.parse.quote(path, safe='')}?ref={urllib.parse.quote(branch)}", token)
            return RepositoryContent(path=path, content=payload["content"].replace("\n", ""), encoding="base64")
        url = f"{config.api_url}/repositories/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}/src/{urllib.parse.quote(branch)}/{safe_path}"
        raw = self._request("GET", url, token)
        try:
            return RepositoryContent(path=path, content=raw.decode("utf-8"), encoding="utf-8")
        except UnicodeDecodeError:
            return RepositoryContent(path=path, content=base64.b64encode(raw).decode("ascii"), encoding="base64")

    def access_token(self, user_id: str, provider: str) -> str:
        return self._connection_token(user_id, provider)[1]

    def disconnect(self, user_id: str, provider: str) -> bool:
        self._config(provider)
        return self.persistence.delete_connection(user_id, provider)

    def _connection_token(self, user_id: str, provider: str) -> tuple[ProviderConfig, str]:
        config = self._config(provider)
        row = self.persistence.get_connection(user_id, provider)
        if row is None:
            raise IntegrationError(409, f"Connect {config.name} before accessing repositories.")
        now = datetime.now(timezone.utc)
        expires_at = row.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is not None and expires_at <= now + timedelta(minutes=1):
            if not row.refresh_token_ciphertext:
                raise IntegrationError(401, f"The {config.name} connection expired. Reconnect it.")
            token = self._refresh_token(config, self._decrypt(row.refresh_token_ciphertext))
            next_expiry = now + timedelta(seconds=int(token["expires_in"])) if token.get("expires_in") else None
            self.persistence.upsert_connection(
                user_id=user_id, provider=provider,
                access_token=self._encrypt(token["access_token"]),
                refresh_token=self._encrypt(token["refresh_token"]) if token.get("refresh_token") else row.refresh_token_ciphertext,
                token_type=token.get("token_type", row.token_type), scopes=self._scopes(token, config),
                external_account_id=row.external_account_id, external_account_name=row.external_account_name,
                external_avatar_url=row.external_avatar_url, expires_at=next_expiry,
            )
            return config, token["access_token"]
        return config, self._decrypt(row.access_token_ciphertext)

    def _refresh_token(self, config: ProviderConfig, refresh_token: str) -> dict:
        values = {"grant_type": "refresh_token", "refresh_token": refresh_token}
        headers = {"Accept": "application/json"}
        if config.id == "bitbucket":
            credentials = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            values.update({"client_id": config.client_id, "client_secret": config.client_secret})
        payload = json.loads(self._request("POST", config.token_url, None, urllib.parse.urlencode(values).encode(), headers))
        if not payload.get("access_token"):
            raise IntegrationError(401, f"The {config.name} connection could not be refreshed. Reconnect it.")
        return payload

    def _exchange_code(self, config: ProviderConfig, code: str) -> dict:
        values = {"grant_type": "authorization_code", "code": code, "redirect_uri": self._callback(config.id)}
        headers = {"Accept": "application/json"}
        if config.id == "bitbucket":
            credentials = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
        else:
            values.update({"client_id": config.client_id, "client_secret": config.client_secret})
        raw = self._request("POST", config.token_url, None, urllib.parse.urlencode(values).encode(), headers)
        payload = json.loads(raw)
        if not payload.get("access_token"):
            raise IntegrationError(502, "The provider did not return an access token.")
        return payload

    def _profile(self, config: ProviderConfig, token: str) -> dict:
        endpoint = {"github": "/user", "gitlab": "/user", "bitbucket": "/user"}[config.id]
        return self._json("GET", config.api_url + endpoint, token)

    def _json(self, method: str, url: str, token: str) -> dict | list:
        return json.loads(self._request(method, url, token))

    def _bitbucket_paginated_values(self, url: str, token: str, api_url: str) -> list[dict]:
        values: list[dict] = []
        next_url: str | None = url
        seen: set[str] = set()
        allowed = urllib.parse.urlparse(api_url)
        for _ in range(100):
            if not next_url:
                return values
            resolved = urllib.parse.urljoin(api_url + "/", next_url)
            parsed = urllib.parse.urlparse(resolved)
            if parsed.scheme != allowed.scheme or parsed.netloc != allowed.netloc:
                raise IntegrationError(502, "Bitbucket returned an invalid pagination URL.")
            if resolved in seen:
                raise IntegrationError(502, "Bitbucket returned a pagination loop.")
            seen.add(resolved)
            payload = self._json("GET", resolved, token)
            page_values = payload.get("values") if isinstance(payload, dict) else None
            if not isinstance(page_values, list):
                raise IntegrationError(502, "Bitbucket returned an invalid paginated response.")
            values.extend(item for item in page_values if isinstance(item, dict))
            candidate = payload.get("next")
            next_url = candidate if isinstance(candidate, str) and candidate else None
        raise IntegrationError(502, "Bitbucket pagination exceeded the safety limit.")

    def _request(self, method: str, url: str, token: str | None, data: bytes | None = None, extra_headers: dict | None = None) -> bytes:
        headers = {"Accept": "application/json", "User-Agent": "TestForge-AI"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.update(extra_headers or {})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(512).decode("utf-8", errors="replace")
            raise IntegrationError(502 if exc.code >= 500 else exc.code, f"Provider API request failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise IntegrationError(503, "The provider API is unavailable.") from exc

    def _encrypt(self, value: str) -> str:
        if self.cipher is None:
            raise IntegrationError(503, "OAuth token encryption is not configured.")
        return self.cipher.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        if self.cipher is None:
            raise IntegrationError(503, "OAuth token encryption is not configured.")
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise IntegrationError(503, "The stored provider credential cannot be decrypted.") from exc

    def _require_ready(self, config: ProviderConfig) -> None:
        if not config.configured:
            raise IntegrationError(503, f"{config.name} OAuth is not configured.")
        if self.cipher is None:
            raise IntegrationError(503, "OAuth token encryption is not configured.")

    def _config(self, provider: str) -> ProviderConfig:
        config = self.providers.get(provider.lower())
        if config is None:
            raise IntegrationError(404, "Unsupported source-control provider.")
        return config

    def _callback(self, provider: str) -> str:
        return f"{self.callback_base}/integrations/{provider}/callback"

    @staticmethod
    def _scopes(token: dict, config: ProviderConfig) -> list[str]:
        value = token.get("scope") or token.get("scopes")
        if isinstance(value, list): return value
        if isinstance(value, str): return [part for part in value.replace(",", " ").split() if part]
        return list(config.scopes)

    @staticmethod
    def _github_repo(item: dict) -> ProviderRepository:
        return ProviderRepository(id=str(item["id"]), provider="github", owner=item["owner"]["login"], name=item["name"], fullName=item["full_name"], description=item.get("description"), private=item["private"], defaultBranch=item.get("default_branch") or "main", webUrl=item["html_url"], cloneUrl=item["clone_url"], updatedAt=item.get("updated_at"), stars=item.get("stargazers_count") or 0)

    @staticmethod
    def _gitlab_repo(item: dict) -> ProviderRepository:
        return ProviderRepository(id=str(item["id"]), provider="gitlab", owner=item["path_with_namespace"].rsplit("/", 1)[0], name=item["path"], fullName=item["path_with_namespace"], description=item.get("description"), private=item.get("visibility") != "public", defaultBranch=item.get("default_branch") or "main", webUrl=item["web_url"], cloneUrl=item["http_url_to_repo"], updatedAt=item.get("last_activity_at"), stars=item.get("star_count") or 0)

    @staticmethod
    def _bitbucket_repo(item: dict) -> ProviderRepository:
        full_name = item["full_name"]
        workspace = item.get("workspace") or {}
        owner = workspace.get("slug") or full_name.partition("/")[0]
        clone_links = item.get("links", {}).get("clone", [])
        clone_url = next((link.get("href") for link in clone_links if link.get("name") == "https"), None)
        if not clone_url:
            raise IntegrationError(502, f"Bitbucket did not return an HTTPS clone URL for {full_name}.")
        return ProviderRepository(id=item["uuid"], provider="bitbucket", owner=owner, name=item["slug"], fullName=full_name, description=item.get("description"), private=item.get("is_private", False), defaultBranch=(item.get("mainbranch") or {}).get("name") or "main", webUrl=item["links"]["html"]["href"], cloneUrl=clone_url, updatedAt=item.get("updated_on"), stars=0)
