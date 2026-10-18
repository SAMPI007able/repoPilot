# OIDC sign-in setup for TestForge

The app already has the core OIDC flow implemented:

- the frontend uses oidc-client-ts for Authorization Code + PKCE sign-in and callback handling
- the callback route is wired in the Vue router
- the backend verifies the incoming access token signature, issuer, audience, and expiration
- the backend maps the OIDC identity to an internal TestForge user on first login

What remains is provider configuration and environment wiring.

## 1. Choose an OIDC provider

A provider such as Auth0, Okta, Keycloak, or Azure AD works well. The examples below use Auth0-style values because the current frontend defaults are Auth0-compatible.

## 2. Create an application in your identity provider

Create a web application with these settings:

- Allowed callback URLs:
  - http://127.0.0.1:5173/auth/callback
  - http://localhost:5173/auth/callback
- Allowed logout URLs:
  - http://127.0.0.1:5173
  - http://localhost:5173
- Allowed grant types:
  - Authorization Code
- PKCE:
  - enabled

## 3. Enable the identity methods you want

For GitHub, Google, and email sign-in, enable the corresponding connections in your provider:

- GitHub social connection
- Google social connection
- Email/password or database connection for email sign-in

If you are using Auth0, the defaults in this repo are:

- GitHub connection: github
- Google connection: google-oauth2
- Email connection: Username-Password-Authentication

If your tenant uses different connection names, update the frontend values accordingly.

## 4. Configure backend environment variables

Copy the canonical environment file and fill in your provider values:

```powershell
copy .env.example .env
```

Set these values in the repository-root `.env`:

```env
AUTH_MODE=oidc
OIDC_ISSUER=https://<your-tenant>.auth0.com/
OIDC_AUDIENCE=https://api.testforge.example.com
OIDC_JWKS_URL=https://<your-tenant>.auth0.com/.well-known/jwks.json

# Optional resend action for unverified users
AUTH0_VERIFICATION_RESEND_ENABLED=true
AUTH0_MANAGEMENT_CLIENT_ID=<machine-to-machine-client-id>
AUTH0_MANAGEMENT_CLIENT_SECRET=<machine-to-machine-client-secret>
AUTH0_VERIFICATION_CLIENT_ID=<your-web-client-id>
```

Notes:

- OIDC_ISSUER must match the issuer claim in the provider-issued token.
- OIDC_AUDIENCE must match the expected audience claim in the token.
- OIDC_JWKS_URL must point to the JWKS endpoint for signature validation.
- For resend support, authorize the Machine-to-Machine application for the
  Auth0 Management API with only `update:users`, and enable Auth0's Verification
  Email template. Keep the management secret on the backend only.

## 5. Configure frontend environment variables

The frontend reads the same repository-root `.env` during local development:

```powershell
copy .env.example .env
```

Set these values in the repository-root `.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_AUTH_MODE=oidc
VITE_OIDC_AUTHORITY=https://<your-tenant>.auth0.com/
VITE_OIDC_CLIENT_ID=<your-web-client-id>
VITE_OIDC_AUDIENCE=https://api.testforge.example.com
VITE_OIDC_REDIRECT_URI=http://127.0.0.1:5173/auth/callback
VITE_OIDC_SCOPE=openid profile email
VITE_OIDC_CONNECTION_PARAMETER=connection
VITE_OIDC_GITHUB_CONNECTION=github
VITE_OIDC_GOOGLE_CONNECTION=google-oauth2
VITE_OIDC_EMAIL_CONNECTION=Username-Password-Authentication
```

## 6. Start the services

Start the backend:

```powershell
$env:PYTHONPATH="backend"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173 and use the Sign in button.

## 7. Test the sign-in methods

Verify each method:

1. GitHub
   - click Continue with GitHub
   - authenticate with your GitHub account
   - confirm the app returns to the home page and the signed-in user appears

2. Google
   - click Continue with Google
   - authenticate with your Google account
   - confirm the app returns to the home page

3. Email
   - click Continue with email
   - authenticate through your provider's email/password or database connection
   - confirm the app returns to the home page

## 8. Confirm the backend sees the user

After login, call:

```powershell
curl http://127.0.0.1:8000/me -H "Authorization: Bearer <access-token>"
```

The backend should return the current user record for the signed-in identity.

## Troubleshooting

- If sign-in redirects back with an error, verify the callback URL exactly matches the provider configuration.
- If the provider rejects the sign-in request, confirm the client ID and authority values are correct.
- If the email flow fails, verify the email connection name matches your tenant's configured database connection.
- If the provider uses a different parameter name for social logins, update VITE_OIDC_CONNECTION_PARAMETER and the connection values accordingly.
- If `/me` returns `AUTH_TOKEN_AUDIENCE_REQUIRED`, set `VITE_OIDC_AUDIENCE` to exactly the same API identifier as backend `OIDC_AUDIENCE`, rebuild the frontend, clear the old session, and sign in again. Auth0 otherwise issues an opaque token intended only for `/userinfo`.
- Use one browser origin consistently. `http://127.0.0.1:5173` and `http://localhost:5173` have separate browser storage. The configured redirect URI must use the same origin from which sign-in starts.
- OAuth transaction state is stored separately from access tokens and consumed once. Reloading an already completed callback resumes from the validated OIDC user instead of attempting to consume state twice.
