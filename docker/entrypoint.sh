#!/usr/bin/env sh
set -eu

mkdir -p \
  /app/data \
  /app/skills \
  /app/documents \
  /app/rag \
  /app/models \
  /app/.cache \
  /app/web/certs

seed_if_empty() {
  src="$1"
  dst="$2"
  label="$3"

  if [ -d "$src" ] && [ -z "$(ls -A "$dst" 2>/dev/null)" ]; then
    echo "[ADA Docker] Initialisation de $label..."
    cp -a "$src"/. "$dst"/ 2>/dev/null || true
  fi
}

seed_if_empty /opt/ada-seed/data /app/data "data"
seed_if_empty /opt/ada-seed/skills /app/skills "skills"
seed_if_empty /opt/ada-seed/documents /app/documents "documents"
seed_if_empty /opt/ada-seed/rag /app/rag "rag"
seed_if_empty /opt/ada-seed/models /app/models "models"
seed_if_empty /opt/ada-seed/web/certs /app/web/certs "certificats"

exec "$@"