#!/usr/bin/env sh
set -eu

seed_dir() {
  src="$1"
  dst="$2"
  mkdir -p "$dst"
  # Si le bind-mount est vide, on recopie le contenu embarqué dans l'image.
  if [ -d "$src" ] && [ -z "$(ls -A "$dst" 2>/dev/null || true)" ] && [ -n "$(ls -A "$src" 2>/dev/null || true)" ]; then
    echo "[ADA Docker] Initialisation de $dst depuis $src"
    cp -a "$src"/. "$dst"/ || true
  fi
}

mkdir -p       "${ADA_DATA_DIR:-/app/data}"       "${ADA_SKILLS_DIR:-/app/skills}"       "${ADA_DOCUMENTS_DIR:-/app/documents}"       "${ADA_RAG_DIR:-/app/rag}"       "${ADA_MODELS_DIR:-/app/models}"       "${ADA_CACHE_DIR:-/app/.cache}"       "${ADA_CERTS_DIR:-/app/web/certs}"

seed_dir /opt/ada-seed/data "${ADA_DATA_DIR:-/app/data}"
seed_dir /opt/ada-seed/skills "${ADA_SKILLS_DIR:-/app/skills}"
seed_dir /opt/ada-seed/documents "${ADA_DOCUMENTS_DIR:-/app/documents}"
seed_dir /opt/ada-seed/rag "${ADA_RAG_DIR:-/app/rag}"
seed_dir /opt/ada-seed/models "${ADA_MODELS_DIR:-/app/models}"
seed_dir /opt/ada-seed/web/certs "${ADA_CERTS_DIR:-/app/web/certs}"

# Prépare les dossiers SQLite usuels.
mkdir -p "$(dirname "${INTENT_MINING_DB_PATH:-${ADA_DATA_DIR:-/app/data}/intent_corpus.sqlite}")"
mkdir -p "$(dirname "${RADAR_DB_PATH:-${ADA_DATA_DIR:-/app/data}/radar/events.sqlite}")"

echo "[ADA Docker] ADA_WEB_PORT=${ADA_WEB_PORT:-7654} ADA_WEB_SSL=${ADA_WEB_SSL:-false}"
echo "[ADA Docker] OLLAMA_URL=${OLLAMA_URL:-non défini}"
echo "[ADA Docker] Données: ${ADA_DATA_DIR:-/app/data}, skills: ${ADA_SKILLS_DIR:-/app/skills}, docs: ${ADA_DOCUMENTS_DIR:-/app/documents}, rag: ${ADA_RAG_DIR:-/app/rag}"

exec "$@"
