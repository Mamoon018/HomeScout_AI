# HomeScout Auth Backend

FastAPI login API with HTTPOnly cookie auth.

The browser talks only to the frontend origin. Vite's `/api` proxy forwards those
requests to this server, so `Set-Cookie` is stored on the frontend origin and
`SameSite=Strict` works.

## Environment variables

Copy `.env.example` to `.env` in this directory and set server-only values:

```bash
cp .env.example .env
```

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Supabase project URL (server-side only) |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable API key for the Supabase SDK client |
| `SUPABASE_JWT_AUDIENCE` | Optional. JWT `aud` claim expected during local verification (default `authenticated`) |

`.env` is gitignored. Do **not** use `VITE_` prefixes — those would be exposed to the frontend bundle. Do not put the service-role / secret key in this app or in the frontend.

## Local HTTPS setup (mkcert)

```bash
# Install mkcert, then from backend/
mkdir -p certs
mkcert -install
mkcert -cert-file certs/localhost+1.pem -key-file certs/localhost+1-key.pem localhost 127.0.0.1
```

## Run

```bash
cd backend
pip install -r requirements.txt
uvicorn src.app.main:app --host localhost --port 8000 \
  --ssl-keyfile=certs/localhost+1-key.pem \
  --ssl-certfile=certs/localhost+1.pem
```

Pair with the frontend HTTPS dev server (this is the origin the browser uses):

```bash
cd frontend
npm run dev:https
```

Login from the app uses `POST /api/auth/login` on the frontend origin. Do not
point the browser at `https://localhost:8000` for login.

## Cookie verification

A successful JSON body does not prove the session cookie landed. Check all three:

1. **Backend send logs** — after login you should see `session cookies sent` with `http_only=True secure=True same_site=strict`.
2. **Vite proxy logs** — `[auth-proxy] response` should include redacted `Set-Cookie` headers (`access_token=<redacted>`; `refresh_token=<redacted>`).
3. **Backend receive probe** — `GET /api/auth/session` (same origin, through the proxy) returns `{ "present": true, "matches_expected": true, "name": "access_token" }` when the access cookie is present and locally verifiable. The callback and home pages show this in the UI. In DevTools, the cookie is under Application → Cookies → `https://localhost:5173`. HttpOnly cookies never appear in `document.cookie`.

Endpoints:

- `POST /api/auth/login` — Supabase `sign_in_with_password`; sets `access_token` (`Path=/`) and `refresh_token` (`Path=/auth/refresh`) cookies on success
- `GET /api/auth/session` — reports whether the access cookie was sent back and verifies locally (never returns the token)
- `GET /api/auth/token-check` — diagnostic: locally verifies the access JWT (algorithm + `aud`). Not a production auth guard.

Use a real registered Supabase user when testing login.
