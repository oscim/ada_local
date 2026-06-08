
# user data 
ADA_EXTERNAL_DATA_DIR=/home/aurelien/ada-data

# --- ADA Web ---
ADA_HOST=0.0.0.0
ADA_WEB_PORT=7654
ADA_PUBLISHED_WEB_PORT=7654

# Recommandé en Docker derrière LAN/reverse-proxy : HTTP simple.
# Mettre true pour générer/servir un certificat autosigné persistant dans ./web/certs.
ADA_WEB_SSL=false

# Port HTTP interne callback. Mettre 0 si inutile.
ADA_HTTP_CALLBACK_PORT=0
ADA_PUBLISHED_CALLBACK_PORT=7655

# --- Données persistantes ADA ---
# Ces chemins sont internes au conteneur. docker-compose.yml les relie à ./data, ./skills, etc.
ADA_DATA_DIR=/app/data
ADA_SKILLS_DIR=/app/skills
ADA_DOCUMENTS_DIR=/app/documents
ADA_RAG_DIR=/app/rag
ADA_MODELS_DIR=/app/models
ADA_CACHE_DIR=/app/.cache
ADA_CERTS_DIR=/app/web/certs

# Bases internes
INTENT_MINING_DB_PATH=/app/data/intent_corpus.sqlite
RADAR_DB_PATH=/app/data/radar/events.sqlite

# --- Ollama externe ---
# Cas LAN : http://192.168.1.50:11434/api
# Cas hôte Docker : http://host.docker.internal:11434/api
OLLAMA_URL=http://192.168.1.50:11434/api
RESPONDER_MODEL=mistral:latest
MARKETING_MODEL=mistral:latest

# --- n8n externe ou LAN ---
# Cas LAN : http://192.168.1.60:5678
# Cas hôte Docker : http://host.docker.internal:5678
N8N_BASE_URL=http://192.168.1.60:5678
N8N_DEFAULT_WEBHOOK_URL=http://192.168.1.60:5678/webhook/ada-event
N8N_VERIFY_SSL=true
N8N_TIMEOUT_SECONDS=10

# --- Audio / assistant vocal ---
# Recommandé false dans Docker tant que les périphériques audio ne sont pas explicitement montés.
VOICE_ASSISTANT_ENABLED=false
