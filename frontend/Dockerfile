# syntax=docker/dockerfile:1

# --- Stage 1: build the static bundle ---
FROM node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd AS build
WORKDIR /app

# Install dependencies against the lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

# Build the production bundle.
COPY . .
RUN npm run build

# --- Stage 2: serve with a hardened, non-root nginx ---
FROM nginxinc/nginx-unprivileged:1.31-alpine@sha256:6320020c7da8714feab524e02c08c5a1958675c4e68700e93a2fd8970b065786 AS runtime

# Runs as uid 101 (nginx) by default — no root.
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]

# Image's default entrypoint launches nginx in the foreground.
