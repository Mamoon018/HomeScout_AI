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
| `CAPTCHA_ENABLED` | When `false`, login skips Turnstile verification (local dev). Defaults to `true`. |
| `LOG_LEVEL` | Application log level for `homescout.auth` (`INFO` or `DEBUG`). Set `DEBUG` locally to see verified token claims. |

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

## Endpoints

- `POST /api/auth/login` — Supabase `sign_in_with_password`; sets `access_token` (`Path=/`) and `refresh_token` (`Path=/auth/refresh`) cookies on success. JSON body is `{ "message", "user_id", "user_name" }`. Token values are never in the body.
- `POST /auth/refresh` — Exchanges the path-scoped refresh cookie for rotated session cookies. On failure, clears both cookies and returns `401`.

Use a real registered Supabase user when testing login.

## Refresh validation (production-like)

Access token **JWT expiry** comes from **Supabase JWT settings**, not backend env vars. The backend keeps the `access_token` **cookie** in the browser for the full session window (`access_cookie_max_age`, currently 30 days) even when the JWT inside expires sooner. That way, after the JWT expires the cookie is still sent, the API returns `code=token_expired`, and the frontend can refresh.

### 1. Shorten JWT expiry (dev/staging project only)

1. Supabase Dashboard → **Authentication → JWT Settings** (or **Settings → Auth → JWT expiry**).
2. Set **JWT expiry** to **300** seconds (5 minutes). Save.
3. Clear cookies or log in again so new sessions pick up the TTL.
4. Confirm in the **backend uvicorn terminal** after login (not the Vite frontend terminal):
   - `login succeeded user_id=... jwt_expires_in=300 access_cookie_max_age=2592000`
   - `session cookies sent ... jwt_expires_in=300 access_cookie_max_age=2592000 ...`

`LOG_LEVEL=INFO` logs refresh outcomes (`refresh succeeded`, `refresh rejected reason=...`). `LOG_LEVEL=DEBUG` additionally logs verified token claims on protected routes.

### 2. Manual checklist

Run backend + `npm run dev:https` in frontend. Watch the **backend terminal** (`homescout.auth` logs).

| Test | Steps | Expected terminal sequence |
|------|-------|----------------------------|
| **A — Happy path** | Login → open `/home` → wait 6+ min → reload `/home` | `identity rejected reason=token_expired` → `refresh succeeded user_id=... expires_in=300` → `session cookies sent ...` → welcome loads without login redirect |
| **B — Dedup** | After expiry, reload `/home` in two tabs at once | Exactly one `refresh succeeded` per expiry cycle |
| **C — Missing refresh** | Login → delete `refresh_token` cookie in DevTools → wait for access expiry → reload | `token_expired` → `refresh rejected reason=missing_token` → `session cookies cleared` → redirect to login |
| **D — Invalid refresh** | Login → tamper `refresh_token` cookie → wait for access expiry → reload | `token_expired` → `refresh rejected reason=invalid_token` → `session cookies cleared` → redirect to login |

The Vite dev server also logs `[auth-proxy]` lines for `/auth/refresh` (cookies redacted). Backend `homescout.auth` logs are the authoritative audit trail.

### 3. Revert after validation

1. Restore Supabase JWT expiry to the production value (typically **3600** seconds).
2. Keep `LOG_LEVEL=INFO` (or higher) in production — refresh logs are low-noise and useful for diagnosing auth issues.
3. Have users re-login once so cookies align with the restored TTL.
