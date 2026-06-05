# ADA — Spécification : Extraction des intentions depuis le Radar

**Projet :** ADA local  
**Branche cible :** `univers`  
**Périmètre :** exploitation du store Radar existant, pipeline web  
**Hors périmètre :** implémentation du moteur d'intention, interface UI, refactor pipeline  
**Document :** spécification fonctionnelle — Étape 1  
**Version :** 1.0  
**Date :** 2026-06-05  
**Dépendance amont :** `SPEC_RADAR_INTEGRATION.md`  
**Dépendance aval :** `SPEC_INTENT_DETECTION.md`, `SPEC_FEEDBACK_LOOP.md`

---

## 1. Contexte

Le Radar ADA journalise chaque requête conversationnelle sous le type `rag.query.received`. Ces événements représentent le corpus réel des formulations utilisées par Aurélien dans son contexte, sa langue et ses habitudes propres.

À date, ce corpus est sous-exploité : il sert uniquement à l'observabilité. Il n'est pas utilisé pour améliorer la compréhension des intentions ni pour alimenter les AutoSkills.

Ce document spécifie comment extraire, structurer et valoriser ce corpus pour construire ensuite la détection d'intention d'ADA.

---

## 2. Objectif

Produire, depuis le store Radar, un corpus structuré de triplets :

```
formulation → action détectée → résultat (succès / échec / inconnu)
```

Ce corpus est la matière première de deux composants aval :

- la détection d'intention (Étape 2 — `SPEC_INTENT_DETECTION.md`)
- la boucle de feedback et auto-tuning (Étape 4 — `SPEC_FEEDBACK_LOOP.md`)

---

## 3. Sources de données disponibles dans le Radar

### 3.1 Événement `rag.query.received`

Émis à chaque requête `/api/chat`. Contient :

```json
{
  "type": "rag.query.received",
  "message": "texte brut de la requête utilisateur",
  "request_id": "req_xxx",
  "timestamp": "...",
  "module": "pipeline"
}
```

C'est la source principale des formulations brutes.

### 3.2 Événement `llm.call.completed`

Émis à la fin d'un appel LLM. Contient la durée et le modèle. Permet de savoir si une réponse a bien été produite.

### 3.3 Événements d'action exécutée

Selon la fonction résolue, différents événements sont émis :

```
control_light.executed
timer.fired
proxmox.backup.started
n8n.call.success
autoskills.injected
```

Ces événements, corrélés par `request_id`, permettent de déterminer quelle action a été déclenchée en réponse à quelle formulation.

### 3.4 Événement `llm.hallucinated_function`

Indique qu'une fonction demandée par le LLM n'existe pas. Signal négatif fort : la formulation n'a pas abouti à une action valide.

### 3.5 Événements de confirmation

```
confirm_required.created
confirm_required.confirmed
confirm_required.cancelled
```

Permettent de savoir si une action a été validée ou refusée par l'utilisateur.

---

## 4. Pipeline d'extraction

### 4.1 Unité d'analyse : la conversation

L'unité d'analyse est le `request_id`. Pour chaque `request_id`, on collecte l'ensemble des événements Radar associés et on en déduit un enregistrement d'intention.

### 4.2 Structure d'un enregistrement d'intention extrait

```json
{
  "request_id": "req_abc123",
  "timestamp": "2026-06-01T14:30:00+02:00",
  "raw_text": "allume la lumière du salon",
  "detected_action": "control_light",
  "detected_params": {
    "action": "on",
    "room": "salon"
  },
  "outcome": "success",
  "outcome_source": "control_light.executed",
  "has_hallucination": false,
  "confirm_required": false,
  "confirm_result": null,
  "duration_ms": 812,
  "universe": "home"
}
```

Champ `outcome` : valeurs possibles

| Valeur | Condition |
|---|---|
| `success` | Événement d'action exécutée présent, aucune hallucination |
| `hallucinated` | Événement `llm.hallucinated_function` présent |
| `cancelled` | Confirmation créée puis annulée |
| `confirmed` | Confirmation créée puis validée |
| `llm_only` | Aucune action exécutée, réponse LLM seule (passthrough) |
| `unknown` | Données insuffisantes pour conclure |

### 4.3 Règles de corrélation

Pour un `request_id` donné :

1. Chercher `rag.query.received` → extraire `raw_text`.
2. Chercher tous les événements du même `request_id`.
3. Si un événement d'action est présent → `outcome = success`, extraire `detected_action`.
4. Si `llm.hallucinated_function` est présent → `outcome = hallucinated`.
5. Si `confirm_required.cancelled` est présent → `outcome = cancelled`.
6. Si `confirm_required.confirmed` est présent → `outcome = confirmed`.
7. Si seul `llm.call.completed` est présent → `outcome = llm_only`.
8. Sinon → `outcome = unknown`.

L'ordre de priorité en cas de superposition : `hallucinated` > `cancelled` > `confirmed` > `success` > `llm_only` > `unknown`.

---

## 5. Normalisation du texte brut

Avant l'indexation, chaque `raw_text` doit être normalisé :

- passage en minuscules ;
- suppression de la ponctuation finale ;
- suppression des espaces multiples ;
- conservation de la casse interne (noms propres, entités) ;
- PAS de stemming ni de lemmatisation à ce stade.

La normalisation doit rester réversible : le texte original est toujours conservé dans `raw_text`.

---

## 6. Table de stockage

Nom proposé : `intent_corpus`

```sql
CREATE TABLE intent_corpus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    detected_action TEXT,
    detected_params_json TEXT,
    outcome TEXT NOT NULL,
    outcome_source TEXT,
    has_hallucination INTEGER NOT NULL DEFAULT 0,
    confirm_required INTEGER NOT NULL DEFAULT 0,
    confirm_result TEXT,
    duration_ms INTEGER,
    universe TEXT,
    is_validated INTEGER NOT NULL DEFAULT 0,
    validated_at TEXT,
    validated_action TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_ic_action ON intent_corpus(detected_action);
CREATE INDEX idx_ic_outcome ON intent_corpus(outcome);
CREATE INDEX idx_ic_universe ON intent_corpus(universe);
CREATE INDEX idx_ic_timestamp ON intent_corpus(timestamp);
CREATE INDEX idx_ic_validated ON intent_corpus(is_validated);
```

Les champs `is_validated`, `validated_at`, `validated_action` sont réservés à l'Étape 4 (feedback humain).

---

## 7. Composant `IntentMiner`

### 7.1 Interface

```python
class IntentMiner:
    def __init__(self, radar_store, intent_store, logger=None):
        pass

    def run_full_extraction(self, since: str | None = None) -> dict:
        """Extrait tous les request_id non encore traités depuis le Radar."""
        pass

    def extract_for_request(self, request_id: str) -> dict | None:
        """Extrait et stocke l'enregistrement pour un request_id donné."""
        pass

    def get_corpus_stats(self) -> dict:
        """Retourne des agrégats sur le corpus extrait."""
        pass
```

### 7.2 Déclenchement

Le `IntentMiner` peut être déclenché :

- manuellement via une route API (voir section 8) ;
- automatiquement au démarrage d'ADA si le flag est activé ;
- en tâche de fond périodique (ex. toutes les heures) si activé.

Il ne doit jamais bloquer le pipeline conversationnel.

### 7.3 Idempotence

L'extraction est idempotente : un `request_id` déjà présent dans `intent_corpus` n'est pas retraité, sauf si le flag `force=True` est passé.

---

## 8. Routes API

Ajouter un router `/web/router_intent.py` inclus dans `server.py`.

| Route | Méthode | Auth | Rôle |
|---|---|---|---|
| `/api/intent/corpus` | GET | JWT | Liste paginée des enregistrements |
| `/api/intent/corpus/stats` | GET | JWT | Agrégats : actions, outcomes, univers |
| `/api/intent/corpus/extract` | POST | JWT | Déclenche une extraction manuelle |
| `/api/intent/corpus/{request_id}` | GET | JWT | Détail d'un enregistrement |
| `/api/intent/corpus/{request_id}` | DELETE | JWT | Supprime un enregistrement |

### Paramètres de filtrage pour `/api/intent/corpus`

```
limit         : int (défaut 50, max 500)
offset        : int (défaut 0)
outcome       : success | hallucinated | cancelled | confirmed | llm_only | unknown
action        : string
universe      : string
is_validated  : bool
since         : ISO 8601
```

### Format de réponse `/api/intent/corpus/stats`

```json
{
  "total": 1962,
  "by_outcome": {
    "success": 1420,
    "llm_only": 310,
    "hallucinated": 98,
    "cancelled": 42,
    "confirmed": 72,
    "unknown": 20
  },
  "by_action": {
    "control_light": 480,
    "passthrough": 310,
    "set_timer": 210,
    "web_search": 185
  },
  "by_universe": {
    "home": 820,
    "opent": 640,
    "margep": 180,
    "unknown": 322
  },
  "top_hallucinated_functions": [
    {"function": "get_camera_feed", "count": 34},
    {"function": "arm_alarm", "count": 28}
  ],
  "extraction_coverage": 0.94
}
```

Le champ `extraction_coverage` = ratio de `request_id` Radar ayant un enregistrement dans `intent_corpus`.

---

## 9. Rapport d'extraction

Après chaque extraction manuelle ou périodique, un événement Radar est émis :

```json
{
  "type": "intent_miner.extraction.completed",
  "level": "info",
  "module": "intent_miner",
  "message": "Extraction terminée",
  "metadata": {
    "processed": 124,
    "skipped_existing": 1838,
    "new_records": 124,
    "errors": 2,
    "duration_ms": 340
  }
}
```

---

## 10. Configuration

```python
INTENT_MINING_ENABLED = True
INTENT_MINING_AUTO_RUN_ON_STARTUP = True
INTENT_MINING_PERIODIC_INTERVAL_MINUTES = 60
INTENT_MINING_DB_PATH = "data/intent_corpus.db"  # ou même DB que Radar si partagée
```

---

## 11. Critères d'acceptation

### A-001 — Extraction
- `IntentMiner.run_full_extraction()` traite tous les `request_id` Radar sans enregistrement existant.
- Chaque enregistrement contient au minimum `raw_text`, `outcome`, `timestamp`.
- L'extraction est idempotente.

### A-002 — Qualité du corpus
- Le champ `detected_action` est renseigné pour au moins 70% des enregistrements `outcome=success`.
- `has_hallucination` est correctement positionné pour tous les `request_id` portant un événement `llm.hallucinated_function`.

### A-003 — API
- `/api/intent/corpus/stats` répond en moins de 200ms.
- `/api/intent/corpus/extract` retourne immédiatement un `job_id` et traite en tâche de fond.

### A-004 — Observabilité
- Chaque extraction émet un événement Radar `intent_miner.extraction.completed`.
- Les erreurs d'extraction (request_id non résolvable) sont loggées sans planter.

### A-005 — Sécurité
- Aucune données personnelle ni secret ne transite dans le corpus.
- Les routes sont protégées par JWT si `auth.enabled=True`.

---

## 12. Fichiers à créer ou modifier

| Fichier | Action |
|---|---|
| `core/intent/intent_miner.py` | Créer — logique d'extraction et corrélation |
| `core/intent/intent_store.py` | Créer — SQLite store `intent_corpus` |
| `web/router_intent.py` | Créer — routes API |
| `web/server.py` | Modifier — inclure router_intent |
| `config.py` | Modifier — ajouter variables `INTENT_MINING_*` |

---

## 13. Priorités d'implémentation

1. Store SQLite `intent_corpus` + schéma
2. Corrélation `request_id` → enregistrement (extraction unitaire)
3. Extraction batch depuis le Radar complet
4. Route `/api/intent/corpus/stats`
5. Route `/api/intent/corpus/extract` (tâche de fond)
6. Événement Radar à la fin d'extraction
7. Extraction périodique automatique
