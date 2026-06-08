# Dockerisation ADA — v3

Objectif : faire tourner ADA Web dans Docker, tout en gardant ADA indépendant d'Ollama, de n8n et du GPU.

## Principe retenu

Le conteneur ADA est jetable. Il contient le code applicatif, les dépendances Python et les dossiers nécessaires pour démarrer même sans volume externe.

En revanche, il est fortement recommandé d'externaliser les données suivantes :

```text
./data              → bases SQLite, Radar, intent corpus, feedback
./skills            → skills principaux et autoskills
./documents         → base documentaire brute
./rag               → index RAG / embeddings / vector store
./models            → uniquement si ADA garde des modèles locaux
./web/certs         → certificats HTTPS auto-signés persistants
```

Le `docker-compose.yml` fourni monte ces dossiers depuis l'hôte. Le `Dockerfile` crée aussi ces dossiers dans l'image afin que le conteneur reste fonctionnel en mode simple/test.

## Ollama

Ollama n'est pas embarqué dans ADA Docker.

ADA doit uniquement connaître l'URL d'Ollama :

```env
OLLAMA_URL=http://192.168.1.50:11434/api
```

Exemples :

```env
# Ollama sur une autre machine du LAN
OLLAMA_URL=http://192.168.1.50:11434/api

# Ollama sur l'hôte Docker
OLLAMA_URL=http://host.docker.internal:11434/api
```

## n8n

Même principe : n8n est externe.

```env
N8N_BASE_URL=http://192.168.1.60:5678
N8N_DEFAULT_WEBHOOK_URL=http://192.168.1.60:5678/webhook/ada-event
```

## Installation recommandée

À la racine du dépôt ADA :

```bash
cp .env.docker.example .env.docker
mkdir -p data skills documents rag models web/certs
git apply patches/config-env.patch
git apply patches/web-server-env.patch
docker compose --env-file .env.docker build
docker compose --env-file .env.docker up -d
docker compose logs -f ada
```

Accès par défaut :

```text
http://localhost:7654
```

## Mode test sans externalisation

Pour tester un conteneur totalement autonome, sans bind-mounts :

```bash
cp .env.docker.example .env.docker
git apply patches/config-env.patch
git apply patches/web-server-env.patch
docker compose --env-file .env.docker -f docker-compose.internal-data.yml up -d --build
```

Attention : dans ce mode, les données écrites dans le conteneur disparaissent à la suppression du conteneur.

## Mécanisme de seed

Quand `./skills`, `./data`, `./documents`, `./rag`, `./models` ou `./web/certs` sont montés mais vides, `docker/entrypoint.sh` recopie le contenu embarqué dans l'image depuis `/opt/ada-seed/...`.

Cela évite qu'un bind-mount vide masque les skills ou dossiers présents dans l'image.

## HTTPS

Par défaut, Docker utilise HTTP :

```env
ADA_WEB_SSL=false
ADA_HTTP_CALLBACK_PORT=0
```

Le port callback n'est pas exposé par défaut. Pour l'activer, régler `ADA_HTTP_CALLBACK_PORT=7655`, puis lancer avec l'override :

```bash
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.callback.yml up -d
```

Pour garder le comportement HTTPS autosigné :

```env
ADA_WEB_SSL=true
ADA_HTTP_CALLBACK_PORT=7655
```

Les certificats seront générés dans :

```text
./web/certs
```

## GPU

Aucun fichier GPU n'est fourni volontairement.

La carte graphique, CUDA, RTX Ada ou autre ne sont pas un sujet pour ADA Docker dans cette architecture. Le calcul LLM est porté par Ollama, qui peut être sur le LAN, sur l'hôte ou sur une autre machine.

## Fichiers fournis

```text
Dockerfile
docker-compose.yml
docker-compose.internal-data.yml
docker-compose.callback.yml
.dockerignore
.env.docker.example
docker/entrypoint.sh
requirements.docker-full.txt
requirements.docker-web.txt
patches/config-env.patch
patches/web-server-env.patch
patched/config.py
patched/web_server.py
external-data/
```

## Notes sur les dépendances

`requirements.docker-full.txt` reprend les dépendances actuelles.

`requirements.docker-web.txt` est une base plus légère indicative pour itération future. Pour le premier passage, utiliser le `requirements.txt` du dépôt reste le choix le plus sûr.
