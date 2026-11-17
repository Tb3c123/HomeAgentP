# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS builder

WORKDIR /build

COPY package.json package-lock.json tsconfig.json vite.config.ts index.html ./
COPY src ./src

RUN npm ci && npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

USER 101:101

EXPOSE 8310

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8310/api/v1/health || exit 1
