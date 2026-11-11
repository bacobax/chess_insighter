# syntax=docker/dockerfile:1
#
# Web image: builds the React Router SPA (ssr: false) and serves it with Caddy,
# which also terminates HTTPS and reverse-proxies /api (HTTP + WebSockets) to the
# backend. The Caddyfile is mounted from deploy/Caddyfile by docker-compose.yml.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
# VITE_API_BASE_URL stays unset: the API is served from the same origin under /api.
RUN npm run build

FROM caddy:2.10-alpine
COPY --from=build /app/build/client /srv
