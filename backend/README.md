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
| `DUMMY_EMAIL` | Demo login email (server-side only) |
| `DUMMY_PASSWORD` | Demo login password (server-side only) |
| `ACCESS_TOKEN` | Token set in HttpOnly cookie on success |

`.env` is gitignored. Do **not** use `VITE_` prefixes — those would be exposed to the frontend bundle.

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

1. **Backend send logs** — after login you should see `access_token cookie sent` with `http_only=True secure=True same_site=strict`.
2. **Vite proxy logs** — `[auth-proxy] response` should include a redacted `Set-Cookie` (`access_token=<redacted>; HttpOnly; Secure; SameSite=strict`).
3. **Backend receive probe** — `GET /api/auth/session` (same origin, through the proxy) returns `{ "present": true, "matches_expected": true, "name": "access_token" }`. The callback and home pages show this in the UI. In DevTools, the cookie is under Application → Cookies → `https://localhost:5173`. HttpOnly cookies never appear in `document.cookie`.

Endpoints:

- `POST /api/auth/login` — dummy credential check; sets the cookie on success
- `GET /api/auth/session` — reports whether the cookie was sent back (never returns the token)

Use the email and password from your local `backend/.env` when testing login.
