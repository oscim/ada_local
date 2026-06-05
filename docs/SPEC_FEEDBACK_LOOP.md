# ADA — Spécification : Boucle de feedback, validation et auto-tuning

**Projet :** ADA local  
**Branche cible :** `univers`  
**Périmètre :** `web/pipeline.py`, panel chat SPA, couche web uniquement  
**Hors périmètre :** `main.py`, `/gui`, refactor LLM, entraînement de modèle  
**Document :** spécification fonctionnelle — Étape 4  
**Version :** 1.0  
**Date :** 2026-06-05  
**Dépendance amont :** `SPEC_RADAR_INTENT_MINING.md`, `SPEC_INTENT_DETECTION.md`, `SPEC_RADAR_INTEGRATION.md`

---

## 1. Contexte

ADA ne sait pas, après avoir répondu, si Aurélien est satisfait de cette réponse. Elle ne sait pas non plus si une action exécutée était bien celle voulue. Ce manque de signal de retour empêche tout apprentissage automatique progressif.

Ce document spécifie trois mécanismes complémentaires :

1. **Signal de satisfaction** — permettre à Aurélien d'indiquer si une réponse était bonne ou non.
2. **Validation des AutoSkills** — relier le signal de satisfaction à la validation ou l'invalidation d'un AutoSkill.
3. **Fichier des erreurs** — constituer un registre structuré des réponses échouées pour analyse et correction.

Ces trois mécanismes alimentent une boucle fermée : Radar → corpus → détection → feedback → corpus amélioré → détection améliorée.

---

## 2. Signal de satisfaction

### 2.1 Interface utilisateur

Chaque réponse ADA dans le panel chat affiche deux boutons discrets en bas à droite, à côté de l'indicateur de santé Radar :

```
[réponse ADA ...]
                        ● vert    👍  👎
```

- `👍` : réponse satisfaisante
- `👎` : réponse non satisfaisante

Ces boutons sont visibles au survol de la réponse (hover sur desktop, tap sur mobile). Ils ne doivent pas parasiter visuellement la lecture.

Après un clic, le bouton choisi est marqué comme actif (couleur pleine), l'autre s'estompe. Le signal est envoyé une seule fois par réponse.

### 2.2 Comportement du bouton `👎`

Après un clic `👎`, une zone de contexte optionnelle apparaît sous les boutons :

```
Qu'est-ce qui n'allait pas ?
[_________________________________]  Envoyer
```

Champ texte libre, 140 caractères max, facultatif. L'envoi se fait aussi bien avec le bouton qu'en appuyant sur Entrée. Si Aurélien ferme la zone sans remplir, le signal `negative` est envoyé sans commentaire.

### 2.3 Données transmises à l'API

```json
{
  "request_id": "req_abc123",
  "signal": "positive | negative",
  "comment": "optionnel, texte libre",
  "response_summary": "les 80 premiers caractères de la réponse ADA"
}
```

### 2.4 Route API

```
POST /api/feedback/response
```

Auth : JWT si activé.

Réponse :

```json
{
  "status": "recorded",
  "request_id": "req_abc123"
}
```

---

## 3. Traitement du signal de satisfaction

### 3.1 Mise à jour de `intent_corpus`

Pour chaque signal reçu, le record correspondant dans `intent_corpus` est mis à jour :

```sql
UPDATE intent_corpus
SET
    is_validated = 1,
    validated_at = NOW(),
    validated_action = detected_action,   -- confirmée si signal positif
    feedback_signal = 'positive' | 'negative',
    feedback_comment = '...'
WHERE request_id = ?;
```

Pour un signal négatif, `validated_action` reste `NULL`.

### 3.2 Mise à jour de l'index d'intention

Après un signal **positif** :

- L'enregistrement est ajouté à l'index TF-IDF (ou renforce le poids si déjà présent).
- `IntentDetector.add_to_index(record)` est appelé sans reconstruction complète.

Après un signal **négatif** :

- L'enregistrement est retiré de l'index TF-IDF s'il y était présent.
- Il est marqué comme exclu dans `intent_corpus` (`index_excluded = 1`).
- Si cet enregistrement avait alimenté un AutoSkill, ce dernier est marqué pour révision.

### 3.3 Reconstruction complète différée

Après 10 signaux positifs ou 3 signaux négatifs accumulés depuis la dernière reconstruction, une reconstruction complète de l'index est déclenchée en tâche de fond.

Le seuil est configurable (`FEEDBACK_REBUILD_TRIGGER_POSITIVE`, `FEEDBACK_REBUILD_TRIGGER_NEGATIVE`).

---

## 4. Validation des AutoSkills

### 4.1 Lien entre réponse et AutoSkill

Quand un AutoSkill est injecté dans le pipeline pour une requête donnée, l'événement Radar `autoskills.injected` contient la liste des AutoSkills utilisés.

Ces informations sont déjà propagées via `request_id`. Elles sont extraites lors du traitement du feedback.

### 4.2 Signal positif → validation AutoSkill

Si la réponse a utilisé un AutoSkill et reçoit un signal positif :

```sql
UPDATE autoskills
SET
    validated_count = validated_count + 1,
    last_validated_at = NOW()
WHERE id = ?;
```

Un AutoSkill validé N fois (seuil configurable, défaut 3) est promu au statut `confirmed`. Il bénéficie d'une priorité d'injection plus élevée dans les prochaines requêtes similaires.

### 4.3 Signal négatif → révision AutoSkill

Si la réponse a utilisé un AutoSkill et reçoit un signal négatif :

```sql
UPDATE autoskills
SET
    rejected_count = rejected_count + 1,
    last_rejected_at = NOW()
WHERE id = ?;
```

Si `rejected_count` ≥ seuil (défaut 2) :

- L'AutoSkill est marqué `status = 'under_review'`.
- Il n'est plus injecté automatiquement jusqu'à révision manuelle ou réhabilitation.
- Un événement Radar `autoskill.flagged` est émis.

### 4.4 Route de révision manuelle

```
GET  /api/autoskills/under_review     → liste des AutoSkills en révision
POST /api/autoskills/{id}/rehabilitate → remet à zéro rejected_count, status = 'active'
POST /api/autoskills/{id}/disable      → désactive définitivement
```

---

## 5. Fichier des erreurs

### 5.1 Objectif

Constituer un registre exploitable de toutes les réponses problématiques, qu'elles soient :

- signalées manuellement par Aurélien (signal `👎`) ;
- détectées automatiquement par le Radar (hallucination, timeout, erreur).

### 5.2 Table `error_log`

```sql
CREATE TABLE error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,              -- 'user_feedback' | 'radar_auto'
    error_type TEXT NOT NULL,          -- 'negative_feedback' | 'hallucinated_function' | 'timeout' | 'action_failed' | 'entity_not_found'
    raw_text TEXT,                     -- formulation utilisateur
    detected_action TEXT,              -- action tentée
    error_detail TEXT,                 -- message d'erreur ou commentaire utilisateur
    autoskill_ids TEXT,                -- JSON array des AutoSkill IDs impliqués
    radar_events_json TEXT,            -- snapshot des événements Radar liés
    resolution TEXT,                   -- NULL | 'autoskill_flagged' | 'index_excluded' | 'manual_fix'
    resolved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_el_error_type ON error_log(error_type);
CREATE INDEX idx_el_source ON error_log(source);
CREATE INDEX idx_el_timestamp ON error_log(timestamp);
CREATE INDEX idx_el_resolution ON error_log(resolution);
```

### 5.3 Alimentation automatique (source `radar_auto`)

Les événements Radar suivants déclenchent automatiquement un enregistrement dans `error_log` :

| Événement Radar | `error_type` généré |
|---|---|
| `llm.hallucinated_function` | `hallucinated_function` |
| `intent.entity_resolution_failed` | `entity_not_found` |
| `n8n.call.failed` | `action_failed` |
| `llm.timeout` | `timeout` |
| `proxmox.backup.failed` | `action_failed` |

### 5.4 Alimentation manuelle (source `user_feedback`)

Quand Aurélien envoie un signal `👎`, un enregistrement `error_log` est créé avec :

```
source = 'user_feedback'
error_type = 'negative_feedback'
error_detail = commentaire optionnel
```

### 5.5 Routes API

| Route | Méthode | Auth | Rôle |
|---|---|---|---|
| `/api/errors` | GET | JWT | Liste paginée des erreurs |
| `/api/errors/stats` | GET | JWT | Agrégats par type, par action, par période |
| `/api/errors/{id}` | GET | JWT | Détail d'une erreur |
| `/api/errors/{id}/resolve` | POST | JWT | Marque une erreur comme résolue |
| `/api/errors/export` | GET | JWT | Export CSV ou JSON |

### Paramètres de filtrage pour `/api/errors`

```
limit        : int (défaut 50, max 500)
offset       : int (défaut 0)
source       : user_feedback | radar_auto
error_type   : string
resolution   : null | autoskill_flagged | index_excluded | manual_fix
since        : ISO 8601
```

### Format `/api/errors/stats`

```json
{
  "total": 142,
  "unresolved": 38,
  "by_type": {
    "negative_feedback": 62,
    "hallucinated_function": 44,
    "entity_not_found": 18,
    "action_failed": 12,
    "timeout": 6
  },
  "top_failing_actions": [
    {"action": "arm_alarm", "count": 18},
    {"action": "get_camera_feed", "count": 12}
  ],
  "trend_7d": [
    {"date": "2026-05-30", "count": 8},
    {"date": "2026-05-31", "count": 5}
  ]
}
```

---

## 6. Composant `FeedbackProcessor`

```python
class FeedbackProcessor:
    def __init__(self, intent_store, autoskill_store, error_store, intent_detector, radar, logger=None):
        pass

    def process_response_feedback(self, request_id: str, signal: str, comment: str | None = None) -> dict:
        """Traite un signal 👍/👎 envoyé depuis le chat."""
        pass

    def process_radar_error(self, event: dict) -> None:
        """Traite un événement Radar d'erreur → alimente error_log automatiquement."""
        pass

    def flag_autoskill(self, autoskill_id: str, reason: str) -> None:
        """Marque un AutoSkill pour révision."""
        pass

    def get_pending_rebuild_count(self) -> int:
        """Retourne le nombre de signaux en attente de reconstruction d'index."""
        pass
```

---

## 7. Événements Radar émis

| Type | Level | Condition |
|---|---|---|
| `feedback.positive.recorded` | info | Signal positif enregistré |
| `feedback.negative.recorded` | info | Signal négatif enregistré |
| `feedback.index_updated` | info | Index TF-IDF mis à jour après signal |
| `feedback.index_rebuilt` | info | Reconstruction complète déclenchée |
| `autoskill.validated` | info | AutoSkill promu après N validations |
| `autoskill.flagged` | warning | AutoSkill mis en révision après rejets |
| `error_log.created` | info | Entrée error_log créée (auto ou manuelle) |
| `error_log.resolved` | info | Erreur marquée comme résolue |

---

## 8. Interface SPA — modifications

### 8.1 Boutons de feedback dans le message ADA

Chaque `div.msg-ada` reçoit un footer de feedback :

```html
<div class="msg-feedback">
  <button class="fb-btn fb-positive" data-request-id="req_xxx" title="Réponse utile">👍</button>
  <button class="fb-btn fb-negative" data-request-id="req_xxx" title="Réponse incorrecte">👎</button>
</div>
```

Comportement CSS :

- Boutons invisibles par défaut (`opacity: 0`).
- Visibles au hover de `.msg-ada` (`opacity: 0.5`).
- Après clic : bouton choisi à `opacity: 1`, bouton rejeté à `opacity: 0.2`.

### 8.2 Zone de commentaire `👎`

```html
<div class="fb-comment-area" style="display:none">
  <textarea maxlength="140" placeholder="Qu'est-ce qui n'allait pas ? (optionnel)"></textarea>
  <button class="fb-send">Envoyer</button>
  <button class="fb-skip">Ignorer</button>
</div>
```

Apparaît sous le message après clic `👎`. Envoi déclenche `POST /api/feedback/response`.

### 8.3 Indicateur de santé enrichi

L'indicateur de santé existant (vert/orange/rouge) affiché par `SPEC_RADAR_INTEGRATION.md` est enrichi :

- Si signal `👍` enregistré → bordure verte subtile sur l'indicateur.
- Si signal `👎` enregistré → bordure rouge subtile.
- Le tooltip de l'indicateur affiche : `X événements Radar · Feedback : ✓ positif`.

---

## 9. Configuration

```python
FEEDBACK_ENABLED = True
FEEDBACK_AUTOSKILL_VALIDATE_THRESHOLD = 3    # validations pour promouvoir confirmed
FEEDBACK_AUTOSKILL_REJECT_THRESHOLD = 2      # rejets pour under_review
FEEDBACK_REBUILD_TRIGGER_POSITIVE = 10       # signaux positifs avant rebuild index
FEEDBACK_REBUILD_TRIGGER_NEGATIVE = 3        # signaux négatifs avant rebuild index
FEEDBACK_ERROR_LOG_AUTO_RADAR = True         # alimentation auto depuis Radar
FEEDBACK_ERROR_LOG_RETENTION_DAYS = 90
```

---

## 10. Critères d'acceptation

### A-001 — Signal de satisfaction
- `POST /api/feedback/response` enregistre le signal dans `intent_corpus` et `error_log`.
- Un signal positif met à jour l'index TF-IDF sans reconstruction complète.
- Un signal négatif retire l'enregistrement de l'index.
- L'interface affiche les boutons 👍/👎 sur chaque réponse ADA.

### A-002 — AutoSkills
- Un AutoSkill reçoit un signal positif lorsqu'il est impliqué dans une réponse bien notée.
- Un AutoSkill est marqué `under_review` après `FEEDBACK_AUTOSKILL_REJECT_THRESHOLD` rejets.
- La route de réhabilitation manuelle fonctionne.

### A-003 — Fichier des erreurs
- Les événements Radar d'erreur alimentent `error_log` automatiquement.
- Le signal `👎` crée également une entrée `error_log`.
- `/api/errors/stats` retourne les agrégats corrects.
- `/api/errors/export` produit un fichier téléchargeable.

### A-004 — Observabilité
- Chaque signal enregistré émet un événement Radar.
- Chaque AutoSkill flaggé émet un événement Radar `warning`.

### A-005 — Non-régression
- Désactiver `FEEDBACK_ENABLED` ne modifie pas le comportement du pipeline.
- L'absence de signal n'empêche pas ADA de fonctionner normalement.

### A-006 — Performance
- `POST /api/feedback/response` répond en moins de 100ms.
- La mise à jour incrémentale de l'index ne dépasse pas 50ms.

---

## 11. Fichiers à créer ou modifier

| Fichier | Action |
|---|---|
| `core/feedback/feedback_processor.py` | Créer — traitement signaux et Radar auto |
| `core/feedback/error_store.py` | Créer — SQLite store `error_log` |
| `web/router_feedback.py` | Créer — routes `/api/feedback/*` et `/api/errors/*` |
| `web/router_autoskills.py` | Modifier — ajouter routes révision AutoSkills |
| `web/server.py` | Modifier — inclure router_feedback, démarrer FeedbackProcessor |
| `web/pipeline.py` | Modifier — annoter les réponses avec `request_id` et AutoSkill IDs |
| `config.py` | Modifier — ajouter variables `FEEDBACK_*` |
| SPA frontend | Modifier — boutons 👍/👎, zone commentaire, indicateur enrichi |

---

## 12. Priorités d'implémentation

1. Table `error_log` + alimentation automatique depuis événements Radar
2. Route `POST /api/feedback/response` + enregistrement signal
3. Mise à jour `intent_corpus` (is_validated, feedback_signal)
4. Mise à jour incrémentale index TF-IDF après signal
5. Liaison AutoSkill ↔ feedback (validated_count, rejected_count)
6. Flagging AutoSkill sous révision + route de réhabilitation
7. Boutons 👍/👎 dans le panel chat SPA
8. Zone de commentaire après `👎`
9. `/api/errors/stats` et `/api/errors/export`
10. Reconstruction différée de l'index après N signaux
