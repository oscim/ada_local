# ADA web container. Ollama is intentionally external.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ADA_HOST=0.0.0.0 \
    ADA_WEB_PORT=7654 \
    ADA_WEB_SSL=false \
    ADA_HTTP_CALLBACK_PORT=0 \
    ADA_DATA_DIR=/app/data \
    ADA_SKILLS_DIR=/app/skills \
    ADA_DOCUMENTS_DIR=/app/documents \
    ADA_RAG_DIR=/app/rag \
    ADA_MODELS_DIR=/app/models \
    ADA_CACHE_DIR=/app/.cache \
    ADA_CERTS_DIR=/app/web/certs

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    ca-certificates \
    libffi-dev \
    libssl-dev \
    portaudio19-dev \
    ffmpeg \
    libsndfile1 \
    libgl1 \
    libglib2.0-0 \
    libxkbcommon0 \
    libegl1 \
    libx11-6 \
    libxcb1 \
    libxrender1 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
COPY requirements.docker*.txt /tmp/
ARG ADA_REQUIREMENTS_FILE=/tmp/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r "${ADA_REQUIREMENTS_FILE}" \
    && python -m playwright install --with-deps chromium

COPY . /app
COPY default /opt/ada-seed
COPY docker/entrypoint.sh /usr/local/bin/ada-entrypoint

RUN chmod +x /usr/local/bin/ada-entrypoint \
    && mkdir -p /app/data /app/skills /app/documents /app/rag /app/models /app/.cache /app/web/certs \
    && mkdir -p /opt/ada-seed/data /opt/ada-seed/skills /opt/ada-seed/documents /opt/ada-seed/rag /opt/ada-seed/models /opt/ada-seed/web/certs

EXPOSE 7654 7655

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD sh -c 'case "${ADA_WEB_SSL:-false}" in 1|true|TRUE|yes|YES|on|ON) proto=https; curl_flags="-fsSk" ;; *) proto=http; curl_flags="-fsS" ;; esac; curl $curl_flags "${proto}://127.0.0.1:${ADA_WEB_PORT:-7654}/" >/dev/null'

ENTRYPOINT ["/usr/local/bin/ada-entrypoint"]
CMD ["python", "web_server.py"]
