ARG PYTHON_IMAGE_TAG=3.14-slim
ARG UV_VERSION=0.12.10

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv_bin
FROM python:${PYTHON_IMAGE_TAG} AS builder

COPY --from=uv_bin /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-editable

COPY src/ src/
RUN uv sync --locked --no-dev --no-editable

FROM python:${PYTHON_IMAGE_TAG} AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    FORGE_HOST=0.0.0.0 \
    FORGE_PORT=8895 \
    FORGE_SANDBOX_ROOT=/sandbox \
    FORGE_MEMORY_DB=/sandbox/forge_memory.db

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ffmpeg poppler-utils && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser && \
    mkdir -p /sandbox /app && \
    chown -R appuser:appuser /sandbox /app

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

USER appuser
EXPOSE 8895
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import os, socket; s = socket.create_connection(('127.0.0.1', int(os.environ.get('FORGE_PORT', '8895'))), timeout=3); s.close()"]
CMD ["/app/.venv/bin/studio-forge-mcp"]
