# ADA — Référentiel de codage

> Ce fichier est la source de vérité pour coder sur le projet ADA avec Continue.  
> Périmètre : couche `/web` uniquement. `main.py` et `/gui` sont hors périmètre.  
> Branche de référence : `oscim/ada_local@univers`

---

## 1. Identité du projet

ADA est un système de pilotage unifié local. Il couvre :

- la domotique personnelle (univers `home`)
- l'infrastructure IT d'une ESN (univers `opent` — OpenTechno)
- la supervision d'un organisme (univers `uscss` — USCSS)
- le suivi commercial (univers `margep` — Marge Pro)

Le LLM utilisé est **Mistral via Ollama**, tournant en local. Il n'y a pas d'appel à des API cloud payantes dans le cœur du système.

---

## 2. Stack technique

| Couche | Techno |
|---|---|
| Serveur web | FastAPI (Python) |
| Transport chat | Server-Sent Events (SSE) |
| LLM | Ollama (Mistral par défaut) |
| Authentification | JWT optionnel |
| Domotique | Domoticz |
| Infrastructure | Proxmox, RMM custom |
| Automatisation externe | n8n (pont événementiel) |
| Stockage | SQLite (local) |
| Fichiers statiques | montés via FastAPI `StaticFiles` |

---

## 3. Structure des fichiers — couche `/web`

```
web/
├── server.py          # Application FastAPI, routes principales, startup
├── pipeline.py        # Traitement conversationnel, routing, LLM
├── router_auth.py     # Authentification JWT
├── router_plugins.py  # Plugins, univers, actions, confirmation
├── router_societe.py  # Routes société / clients (conditionné par MODULES_ENABLED)
├── router_webhook.py  # Webhooks entrants universels
config.py              # Configuration globale, FUNCTIONS, MODULES_ENABLED, Radar
```

**Règle de fichiers :**

- `server.py` = exposition HTTP et startup uniquement
- `pipeline.py` = logique de traitement, jamais de définition de route
- les `router_*.py` = un domaine = un router
- `config.py` = source de vérité des constantes, pas de logique métier

---

## 4. Route principale `/api/chat`

### Entrée attendue

```json
{
  "message": "texte utilisateur",
  "history": [],
  "plugin_context": "home|opent|uscss|margep",
  "context_id": "optionnel — sous-contexte ou société",
  "session_id": "optionnel — identifiant session réel"
}
```

**Règles :**

- `plugin_context` = univers actif, filtre les capacités et plugins visibles
- `context_id` = sous-contexte interne à l'univers (client, VM, espace documentaire…)
- `company_context` = champ legacy, maintenu en compatibilité uniquement, ne pas utiliser dans le nouveau code
- `session_id` doit être un identifiant réel par utilisateur/session, pas `"web_chat"` fixe

### Sortie SSE

Format cible :

```
data: {"type":"thinking", "text":"..."}
data: {"type":"text", "text":"..."}
data: {"type":"image", "url":"..."}
data: {"type":"confirm_required", "func":"...", "message":"...", "params":{}, "cmd":"..."}
data: {"type":"error", "message":"..."}
data: [DONE]
```

**Règle absolue :** tout flux SSE doit se terminer par `[DONE]`, y compris en cas d'erreur.

Compatibilité temporaire à maintenir :

- `{"text": "..."}` sans champ `type` reste valide côté client existant
- `{"thinking": "..."}` idem
- `{"img_url": "..."}` idem
- `{"__type": "confirm_required", ...}` idem

Ne pas supprimer la compatibilité sans coordination frontend.

---

## 5. Pipeline de traitement (`pipeline.py`)

### Ordre de traitement — ne pas modifier la priorité

1. Nettoyage du message
2. Émission Radar (observabilité)
3. **Routage déterministe prioritaire** (dans cet ordre) :
   - ajout URL de surveillance infra
   - recherche web explicite (agent Playwright)
   - état infrastructure
   - liste VM/CT Proxmox
   - backup Proxmox → confirmation obligatoire
   - start/stop/reboot VM/CT → confirmation obligatoire
   - analyse caméra
   - état entités domotiques
   - contrôle direct domotique
   - création de timer
4. Enrichissement du contexte conversationnel
5. Routage sémantique (`semantic_route`)
6. Tool-calling si route `function_gemma`
7. Dispatch plugin / n8n / executor
8. Streaming réponse SSE
9. Sauvegarde mémoire
10. Mise à jour AutoSkills

**Règle :** si un routage déterministe produit une réponse complète, on ne passe pas au LLM.

### Construction du contexte

Quand le LLM est sollicité, le contexte est construit dans cet ordre :

1. System prompt ADA
2. Historique — 20 derniers messages maximum
3. Contexte domotique si pertinent
4. Skills via `skill_manager`
5. AutoSkills SQLite
6. RAG documentaire
7. Mémoire long terme
8. Message utilisateur courant

**Règle :** la mémoire long terme ne doit jamais devenir une instruction système prioritaire.

---

## 6. Univers et contextes

### Valeurs valides de `plugin_context`

| Valeur | Univers | Couleur interface |
|---|---|---|
| `home` | Maison / domotique | `#7c5cfc` |
| `opent` | OpenTechno / infra | `#00d4ff` |
| `uscss` | USCSS | `#00ff9d` |
| `margep` | Marge Pro | `#ff9500` |

### Règle d'utilisation

- `plugin_context` filtre les plugins actifs, les quick prompts et les capacités exposées au LLM
- `context_id` filtre les données métier dans l'univers (client RMM, VM, espace documentaire…)
- Le pipeline doit utiliser `plugin_context` en priorité, pas `company_context`

### `MODULES_ENABLED` — clés connues

```python
MODULES_ENABLED = {
    "societe": bool,
    "domotique": bool,      # → univers home
    "proxmox": bool,        # → univers opent
    "rmm": bool,            # → univers opent
    "telephony": bool,
    "margepro": bool,       # → univers margep
    "music": bool,
}
```

**Règle :** toujours vérifier `MODULES_ENABLED[clé]` avant d'enregistrer un router ou d'exposer une route liée à un module.

---

## 7. Confirmation des actions sensibles

### Actions nécessitant confirmation obligatoire

- Backup Proxmox
- Start / Stop / Reboot VM ou CT
- Restore Proxmox
- Toute function avec `x_confirm_required=True`

### Route unique

La route de confirmation est **uniquement** dans `router_plugins.py` :

```
POST /api/plugins/confirm
```

Ne pas créer ou maintenir de doublon dans `server.py`. Si une route Proxmox spécifique est nécessaire, la nommer `/api/proxmox/confirm` et la déléguer au même mécanisme.

### Format carte de confirmation (SSE)

```json
{
  "type": "confirm_required",
  "func": "vm_backup",
  "message": "Lancer le backup de la VM compta ?",
  "params": {"vmid": 112, "storage": "nas-backup"},
  "cmd": "proxmox vzdump 112 --compress zstd --storage nas-backup"
}
```

**Règle :** une action sensible ne doit jamais être exécutée avant réception d'un POST de confirmation utilisateur.

---

## 8. Webhooks

### Endpoint entrant

```
POST /api/webhook/{source}
```

Modes de payload supportés :

- intention texte → champs `text`, `message`, `query`, `queryText` → passe dans le pipeline
- action directe → champs `action` + `params` → journalisé + exécuté selon policy
- événement pur → champ `event` sans texte → alimente Radar sans LLM

### Sécurité webhooks

- Un webhook sans token valide retourne `401`
- Toute action webhook est journalisée Radar
- La rotation du token se fait via `POST /api/webhook/config/rotate`

---

## 9. Connecteur n8n (`N8nBridge`)

ADA utilise n8n uniquement comme pont événementiel. ADA ne génère, ne modifie et ne synchronise jamais de workflows n8n.

### Événement standard (enveloppe commune)

```json
{
  "event_id": "evt_...",
  "event_type": "domaine.action",
  "source": "ada|n8n",
  "target": "n8n|ada",
  "timestamp": "ISO 8601",
  "idempotency_key": "...",
  "correlation_id": "...",
  "payload": {},
  "metadata": {}
}
```

### Domaines autorisés

```python
N8N_ALLOWED_EVENT_DOMAINS = [
    "domotic", "marketing", "social", "lead",
    "crm", "support", "content", "notification",
    "workflow", "system"
]
```

### Endpoint entrant ADA pour n8n

```
POST /api/integrations/n8n/events
```

Traitement obligatoire dans l'ordre :

1. Vérification signature HMAC SHA-256
2. Vérification timestamp (anti-rejeu, skew max 300s)
3. Vérification idempotence
4. Validation schéma
5. Routing vers module ADA
6. Journalisation
7. Réponse HTTP normalisée

### Config n8n

```python
N8N_BRIDGE_ENABLED = False          # désactivé par défaut
N8N_BASE_URL = "http://localhost:5678"
N8N_DEFAULT_WEBHOOK_URL = "http://localhost:5678/webhook/ada-event"
N8N_WEBHOOK_SECRET = ""
N8N_TIMEOUT_SECONDS = 10
N8N_MAX_RETRIES = 2
N8N_MAX_CLOCK_SKEW_SECONDS = 300
N8N_VERIFY_SSL = True
```

**Règle :** si `N8N_BRIDGE_ENABLED = False`, ADA ne tente aucun appel n8n et continue à fonctionner normalement.

---

## 10. Sécurité — règles absolues

| Règle | Détail |
|---|---|
| `shell_exec` désactivé par défaut | Si exposé, réservé admin uniquement |
| Secrets masqués | Aucun token, secret, cookie ou API key dans les logs ou les réponses SSE |
| Actions destructives | Toujours `x_confirm_required=True` |
| Auth JWT | Activée si `auth.enabled=True` — routes publiques listées ci-dessous |
| Webhooks | Protégés par token dédié, pas par JWT |

### Routes publiques (pas de JWT requis)

```
/
/manifest.json
/sw.js
/api/status
/static/*
/api/auth/*
/api/webhook/*
```

---

## 11. Observabilité Radar

Le pipeline émet des événements Radar. La config est dans `config.py`.

### Événements minimum à émettre

- Réception requête chat
- Début appel LLM
- Fin appel LLM
- Réponse envoyée
- Confirmation créée / confirmée / annulée / expirée
- Action plugin demandée / validée / exécutée / échouée
- Événement webhook reçu

### Convention

- Chaque `/api/chat` doit avoir un `request_id` unique
- Ce `request_id` doit être transmis dans les événements SSE de debug en mode développeur
- Les events n8n entrants/sortants doivent être journalisés avec `direction`, `status`, `duration_ms`

---

## 12. Mémoire et session

- `session_id` doit être un identifiant réel par utilisateur et par conversation, pas la valeur fixe `"web_chat"`
- Format cible : `{user_id}_{browser_session_id}_{conversation_id}`
- La consolidation mémoire reste déclenchable via `POST /api/memory/consolidate`
- La mémoire long terme ne doit jamais surclasser le system prompt ni devenir une instruction prioritaire

---

## 13. Conventions de code

### Nommage

- Routes : kebab-case → `/api/plugins/quick-prompts`
- Variables Python : snake_case
- Constantes config : UPPER_SNAKE_CASE
- IDs événements : préfixe fonctionnel → `evt_`, `corr_`, `req_`

### Réponses HTTP

| Cas | Code |
|---|---:|
| Succès | 200 |
| Doublon idempotent | 200 |
| Payload invalide | 400 |
| Signature invalide / auth | 401 |
| Domaine non autorisé | 403 |
| Bridge désactivé | 404 |
| Erreur interne | 500 |

### SSE

- Toujours fermer avec `[DONE]`
- Toujours wrapper les erreurs dans un événement SSE, pas en crash silencieux
- Ne jamais exposer de stack trace dans un événement SSE en production

### Imports et dépendances

- Ne pas importer `pipeline.py` depuis les routers — le router appelle `server.py` qui appelle le pipeline
- `config.py` est importable partout mais ne doit pas importer de modules métier
- `FUNCTIONS` dans `config.py` est la liste officielle pour le tool-calling web

---

## 14. Décisions ouvertes (à ne pas implémenter avant arbitrage)

| ID | Sujet |
|---|---|
| D-001 | Migration complète de `company_context` vers `plugin_context` + `context_id` |
| D-002 | Suppression du doublon `/api/plugins/confirm` dans `server.py` |
| D-003 | Séparation officielle `web_search` vs agent Playwright (`web_agent_search`) |
| D-004 | `session_id` réel par utilisateur/session |
| D-005 | Exposition de `shell_exec` dans la couche web — permissions requises |
| D-006 | Source de vérité unique entre `MODULES_ENABLED` et `settings.modules.<key>` |

Ne pas implémenter ces points sans une décision explicite dans le ticket ou la spec associée.

---

## 15. Fichiers de spec de référence

| Fichier | Contenu |
|---|---|
| `ada_web_routes_traitement_interne_spec.md` | Routes HTTP, pipeline, univers, confirmations, sécurité |
| `ADA_SPEC_N8N_BRIDGE-1.md` | Pont n8n bidirectionnel, événements, sécurité, composants |

Ces fichiers font autorité. En cas de conflit entre ce fichier `ada.md` et une spec, la spec gagne.
