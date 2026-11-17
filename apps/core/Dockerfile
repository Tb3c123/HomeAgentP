# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOMEAGENTP_CORE_HOST=0.0.0.0 \
    HOMEAGENTP_CORE_PORT=8311

# Create unprivileged user and group (UID/GID 10001)
RUN groupadd -g 10001 homeagentp && \
    useradd -u 10001 -g 10001 -m -s /usr/sbin/nologin homeagentp && \
    mkdir -p /app /data /config/scripts /config/reports && \
    chown -R 10001:10001 /app /data /config

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8311

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8311/api/v1/health', timeout=3)" || exit 1

CMD ["uvicorn", "homeagentp_core.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8311"]
