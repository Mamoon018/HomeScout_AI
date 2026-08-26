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

Use a real registered Supabase user when testing login.
