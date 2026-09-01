# syntax=docker/dockerfile:1

# --- Stage 1: builder — compile TypeScript + Vite production bundle ---
FROM node:22-alpine AS builder

WORKDIR /app

# Cache-friendly: dependency manifests alone first
COPY package.json package-lock.json .
RUN npm ci

# App source + configs required by `tsc -b && vite build`
COPY tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY vite.config.ts tailwind.config.ts index.html ./
COPY public ./public
COPY src ./src

# Vite inlines env at build time (see vite.config.ts envPrefix: VITE_, SUPABASE_, SITE_KEY_)
# Pass via: docker build --build-arg SUPABASE_PROJECT_URL=... etc.
ARG SUPABASE_PROJECT_URL
ARG SUPABASE_PUBLIC_API_KEY
ARG SITE_KEY_CAPTCHA
ARG VITE_CAPTCHA_ENABLED
ENV SUPABASE_PROJECT_URL=$SUPABASE_PROJECT_URL \
    SUPABASE_PUBLIC_API_KEY=$SUPABASE_PUBLIC_API_KEY \
    SITE_KEY_CAPTCHA=$SITE_KEY_CAPTCHA \
    VITE_CAPTCHA_ENABLED=$VITE_CAPTCHA_ENABLED

RUN npm run build


# --- Stage 2: runtime — HTTPS reverse proxy + static SPA ---
FROM nginxinc/nginx-unprivileged:alpine AS runtime

# Backend proxy target on the Docker internal network (override at runtime if needed)
ENV BACKEND_UPSTREAM=http://backend:8000

# TLS certs: mount at runtime (not baked into the image)
#   /etc/nginx/certs/cert.pem
#   /etc/nginx/certs/key.pem
# Port mapping (host → container) is configured in docker-compose (next step):
#   443 → 8443 (HTTPS), 8080 → 8080 (HTTP redirect to HTTPS)

# nginxinc entrypoint renders /etc/nginx/templates/*.template via envsubst
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080 8443

CMD ["nginx", "-g", "daemon off;"]
