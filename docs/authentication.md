# Authentication configuration

Chess Insighter stores account, session, verification, and report-ownership documents in the versioned local database at `.cache/app_db.json`. Computed report artifacts remain separate JSON cache documents and are referenced by owner-bound report IDs.

Copy `.env.example` to `.env` and configure:

- `AUTH_JWT_SECRET`: a random value of at least 32 bytes. The checked-in development fallback must never be used for a deployment.
- `FRONTEND_URL`: the public frontend origin used in verification links.
- `AUTH_COOKIE_SECURE`: set to `true` when the frontend and API are served over HTTPS.
- `RESEND_API_KEY`: Resend API key with permission to send email.
- `RESEND_FROM_EMAIL`: sender using a domain verified in Resend.

During development, Vite proxies same-origin `/api` and WebSocket requests to `VITE_DEV_API_PROXY_TARGET` (default `http://localhost:8000`). For a split-origin deployment, set `VITE_API_BASE_URL` explicitly and retain credentialed CORS support.

## Account lifecycle

1. Registration creates a pending user and a 24-hour verification record.
2. Resend delivers the one-time link to `/verify-email`.
3. The verification page activates the account; the waiting sign-up tab receives the state over its short-lived WebSocket subscription.
4. Login creates a seven-day JWT cookie backed by a revocable server-side session document.
5. Logout revokes the session and clears both the session and CSRF cookies.

Password recovery and social login are intentionally not included in this milestone.
