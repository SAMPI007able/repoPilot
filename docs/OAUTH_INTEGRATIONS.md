# Source-control OAuth setup

TestForge keeps provider tokens in the backend database encrypted with Fernet. The browser receives only provider metadata and repository records; access and refresh tokens are never returned to the frontend.

## 1. Create the provider applications

Register one OAuth application/consumer in each provider account and configure these exact local callback URLs:

- GitHub: `http://127.0.0.1:8000/integrations/github/callback`
- GitLab: `http://127.0.0.1:8000/integrations/gitlab/callback`
- Bitbucket: `http://127.0.0.1:8000/integrations/bitbucket/callback`

These source-control applications are separate from identity-provider applications used for sign-in. In particular, when Auth0 provides **Sign in with GitHub**, keep its GitHub OAuth App and `https://<auth0-domain>/login/callback` unchanged. Create a second GitHub OAuth App for TestForge repository access and give that second app the backend callback above. Do not add a second GitHub social connection in Auth0.

For production, replace the origin with the public HTTPS API origin and set `OAUTH_CALLBACK_BASE_URL` to the same origin.

Provider permissions:

- GitHub OAuth App: `repo read:user`. GitHub's classic `repo` scope includes write capabilities; use a GitHub App with repository Contents read permission if repository-selective, read-only access is mandatory.
- GitLab OAuth application: `read_user api read_repository`. `read_repository` enables private Git-over-HTTP and file reads.
- Bitbucket OAuth consumer: enable `account` and `repository` read scopes in the consumer configuration.

After creating the Bitbucket OAuth consumer, a workspace administrator must select **Grant access** for that consumer in the workspace's OAuth consumer settings. User approval authorizes the account, while this separate workspace grant makes the workspace and its private repositories visible to the token.

Bitbucket repository discovery uses the supported `GET /user/workspaces` endpoint and then lists repositories through `GET /repositories/{workspace}`. Both response types are paginated, and TestForge follows Bitbucket's `next` links while restricting pagination to the Bitbucket API origin.

References: [GitHub OAuth authorization](https://docs.github.com/en/apps/oauth-apps/using-oauth-apps/authorizing-oauth-apps), [GitHub scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps), [GitLab OAuth scopes](https://docs.gitlab.com/integration/oauth_provider/), and [Bitbucket OAuth 2](https://developer.atlassian.com/cloud/bitbucket/rest/intro/).

## 2. Configure secrets

Generate a stable encryption key once:

```shell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set these backend environment variables. Never rotate the encryption key without re-encrypting or removing existing connections.

```dotenv
OAUTH_TOKEN_ENCRYPTION_KEY=<generated-key>
OAUTH_CALLBACK_BASE_URL=http://127.0.0.1:8000
FRONTEND_URL=http://127.0.0.1:5173
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_CLIENT_SECRET=
GITLAB_OAUTH_CLIENT_ID=
GITLAB_OAUTH_CLIENT_SECRET=
BITBUCKET_OAUTH_CLIENT_ID=
BITBUCKET_OAUTH_CLIENT_SECRET=
```

For local Uvicorn and Docker Compose, place these values in the repository-root `.env` described by [the deployment environment guide](DEPLOYMENT_ENVIRONMENT.md). `backend/.env` remains a temporary Compose compatibility fallback only; root values take precedence.

## 3. Start and verify

```shell
docker compose up --build
```

Sign in to TestForge, select **Connect** for a configured provider, approve access, and return to the home page. Authorized private repositories appear as cards. **Build workspace** imports the selected repository using an ephemeral bearer header and then removes the checkout through the existing workspace cleanup flow.

The integration API also supports listing connections, disconnecting, listing repositories, reading a file, and importing a repository under `/integrations`.
