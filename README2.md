# Pack Docker ADA v3

Version corrigée selon les contraintes :

- ADA Docker ne gère pas le GPU.
- Ollama est externe et uniquement déclaré par `OLLAMA_URL`.
- n8n est externe et uniquement déclaré par `N8N_BASE_URL` / `N8N_DEFAULT_WEBHOOK_URL`.
- Les dossiers de données existent dans l'image pour un démarrage simple.
- L'externalisation de `data`, `skills`, `documents`, `rag`, `models` et `web/certs` est fortement recommandée.

Lire : `docs/ADA_DOCKERISATION.md`.
