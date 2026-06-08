# Spécification — Connecteur n8n bidirectionnel pour ADA

**Projet :** ADA local  
**Branche cible :** `oscim/ada_local@univers`  
**Périmètre :** couche web / backend local ADA  
**Document :** spécification fonctionnelle et technique  
**Version :** 2.0  
**Date :** 2026-06-02  
**Remplace :** ADA_SPEC_N8N_BRIDGE-1.md

---

## Résumé des changements v1 → v2

| Point | v1 | v2 |
|---|---|---|
| Endpoint entrant n8n | `/api/integrations/n8n/events` (nouveau) | `/api/webhook/n8n` (existant) |
| Authentification entrante | HMAC obligatoire | Token webhook existant (`hmac.compare_digest`) |
| HMAC sur body | Obligatoire Phase 1 | Optionnel Phase 5 |
| Fallback n8n | Non spécifié | Documenté — déjà implémenté dans l'UI |
| `initiated_by` | Absent | Ajouté au payload sortant |
| `session_id` | `"web_chat"` fixe | `device_uid` + `conversation_id` |
| Auth membres foyer | Non spécifiée | Mécanique device_uid / QR code |

---

## 1. Résumé

ADA s'intègre à n8n via un **pont d'événements bidirectionnel** basé sur l'infrastructure webhook déjà en place.

```text
ADA → n8n : ADA déclenche des workflows n8n existants
n8n → ADA : n8n remonte des événements, statuts, leads, résultats
```

L'objectif n'est pas de faire d'ADA un générateur de workflows n8n.

```text
ADA = intelligence, contexte, mémoire, règles, décision, supervision
n8n = connecteurs, orchestration externe, workflows visuels, intégrations tierces
```

---

## 2. État existant au 2026-06-02

Avant de spécifier, voici ce qui est **déjà en place** :

### 2.1 Côté entrant — webhook ADA

`/api/webhook/{source}` est opérationnel avec :

- token `secrets.token_urlsafe(32)` persisté dans `settings.json`
- 3 modes détectés automatiquement sur la structure du payload
- comparaison token via `hmac.compare_digest()` (résistant timing attacks)
- n8n utilise déjà ce webhook (doc section 5.2)
- sources supportées : Domoticz, n8n, Home Assistant, Zigbee2MQTT, scripts

### 2.2 Côté sortant — appel n8n depuis ADA

L'UI Paramètres (onglet LLM) expose déjà :

- `URL N8N` : configurable, bouton Test
- `Fallback N8N` : toggle — "Utiliser N8N si fonction locale échoue"

Ces deux éléments signifient que le `N8nBridgeConnector` sortant est partiellement implémenté dans `web/pipeline.py` au niveau du dispatch tool-calling.

### 2.3 Routage sémantique

- Modèle d'embedding : `nomic-embed-text`
- Seuil de confiance : `0.45`
- Modèles Ollama disponibles : gemma4, mistral-small, starcoder2, deepseek-r1, llama3.1, qwen3, mistral, gemma3, llama3

---

## 3. Décision d'architecture

### 3.1 Un seul tuyau entrant

**Décision : ne pas créer `/api/integrations/n8n/events`.**

Le webhook existant `/api/webhook/n8n` couvre le besoin entrant. Créer un second endpoint crée un doublon sans valeur ajoutée pour la v1.

```text
/api/webhook/{source}   ← source de vérité unique pour tous les événements entrants
```

Si n8n a besoin de capacités supplémentaires (HMAC sur body, enveloppe normalisée enrichie), elles seront ajoutées **au webhook existant** en Phase 5, pas dans un endpoint parallèle.

### 3.2 Fallback n8n = feature de premier rang

Le toggle "Fallback N8N si fonction locale échoue" est une décision architecturale importante : n8n est un **plan B automatique** du pipeline tool-calling, pas seulement un destinataire d'événements.

```text
Pipeline ADA — dispatch tool-calling :
  1. Fonction locale ADA (executor)
  2. Plugin registry
  3. → Si échec et N8N_FALLBACK_ENABLED : appel n8n
  4. → Si n8n échoue aussi : message d'erreur LLM
```

### 3.3 ADA ne génère pas de workflows n8n

ADA ne doit pas :

```text
- créer ou modifier des workflows n8n
- activer/désactiver des workflows n8n
- générer du JSON n8n depuis un LLM
- devenir dépendant de la structure interne des workflows n8n
```

ADA doit :

```text
- envoyer des événements normalisés vers n8n
- recevoir des événements normalisés depuis n8n via le webhook existant
- sécuriser les échanges avec le token webhook
- journaliser tous les appels entrants et sortants dans Radar
- router les événements entrants vers ses modules internes
- rester opérationnel si n8n est indisponible
```

---

## 4. Authentification

### 4.1 Membres du foyer — device_uid

L'authentification des membres du foyer repose sur une mécanique **device_uid** similaire à WhatsApp Web :

```text
1. L'utilisateur scanne un QR code affiché par ADA
2. Le device reçoit un device_uid persistant
3. Toutes les sessions passent par ce device_uid
4. Pas de login/password — le device porte l'identité
```

```text
device_uid   = identifiant permanent du périphérique (généré au scan QR)
user_id      = membre du foyer associé à ce device (Aurélien, Marie, ...)
session_id   = device_uid + conversation_id
```

Implications pour la mémoire et le contexte :

```text
- chaque membre a sa mémoire isolée
- chaque conversation a son propre fil
- plusieurs périphériques du même membre = même user_id, conversations distinctes
- révocation : supprimer le device_uid
```

### 4.2 Machine-to-machine — webhook token

Les appels machine-to-machine (n8n, Domoticz, scripts) utilisent le **token webhook**, indépendant de la mécanique device_uid.

```text
Token webhook ≠ JWT membre
Token webhook = auth machine uniquement
```

Le token est transmis par :

| Méthode | Exemple |
|---|---|
| Query parameter | `?token=qAgwvKavHNoo...` |
| Header dédié | `X-Webhook-Token: qAgwvKavHNoo...` |
| Authorization Bearer | `Authorization: Bearer qAgwvKavHNoo...` |

### 4.3 Résumé des couches d'auth

| Couche | Mécanisme | Scope |
|---|---|---|
| Membres du foyer | device_uid + QR code | Interface web, chat, domotique personnelle |
| API interne | JWT optionnel | Routes `/api/*` protégées |
| Machine-to-machine | Token webhook | `/api/webhook/{source}` |
| n8n sortant | URL + token n8n configuré | Appels ADA → n8n |

---

## 5. Modèle d'événement standard

Tous les événements échangés entre ADA et n8n suivent une enveloppe commune.

### 5.1 Structure

```json
{
  "event_id": "evt_20260602_000001",
  "event_type": "domaine.action",
  "source": "ada",
  "target": "n8n",
  "timestamp": "2026-06-02T14:30:00+02:00",
  "idempotency_key": "portail_opened_20260602_143000",
  "correlation_id": "corr_abc123",
  "initiated_by": "device_uid_abc123",
  "payload": {},
  "metadata": {}
}
```

### 5.2 Champs obligatoires

| Champ | Type | Description |
|---|---|---|
| `event_id` | string | Identifiant unique de l'événement |
| `event_type` | string | Format `domaine.action` |
| `source` | string | `ada` ou `n8n` |
| `timestamp` | string | ISO 8601 |
| `payload` | object | Données utiles |

### 5.3 Champs recommandés

| Champ | Type | Description |
|---|---|---|
| `target` | string | Destinataire logique |
| `idempotency_key` | string | Clé anti-doublon |
| `correlation_id` | string | Chaînage entre événements liés |
| `initiated_by` | string | `device_uid` du membre ayant déclenché l'action, ou `"system"` pour les règles automatiques |
| `universe` | string | Contexte ADA actif : `home`, `opent`, `uscss`, `margep` |
| `metadata` | object | Informations techniques |

Le champ `initiated_by` permet à n8n de savoir si l'événement vient d'une règle automatique ou d'une demande explicite d'un membre du foyer, et d'adapter la réponse ou les logs.

### 5.4 Champs `metadata` recommandés côté ADA sortant

```json
"metadata": {
  "origin_module": "automation",
  "executor": "n8n_bridge",
  "requires_human_validation": false,
  "ada_version": "univers"
}
```

---

## 6. Taxonomie des événements

Convention : `domaine.action`

### 6.1 Domaines autorisés

```text
domotic       home, domotique, capteurs, règles
marketing     campagnes, contenus
social        posts, interactions
lead          qualification, CRM
crm           contacts, suivi
support       tickets, alertes clients
content       publications, documents
notification  envoi multi-canal
workflow      statuts n8n
system        santé, supervision
```

### 6.2 Événements courants

```text
domotic.device_triggered
domotic.alert_received
domotic.scene_activated
marketing.campaign_requested
marketing.campaign_prepared
marketing.campaign_approved
marketing.campaign_completed
marketing.campaign_failed
social.post_requested
social.post_published
social.post_failed
social.interaction_received
lead.created
lead.qualified
lead.rejected
crm.contact_created
crm.contact_updated
support.ticket_created
notification.send_requested
workflow.completed
workflow.failed
system.health_check
```

Les événements dont le domaine n'est pas dans la liste autorisée sont refusés avec HTTP 403 ou ignorés silencieusement selon la configuration.

---

## 7. Flux ADA → n8n (sortant)

### 7.1 Déclenchement

Deux chemins déclenchent un envoi vers n8n :

**Chemin 1 — Action de règle explicite**

Une règle ADA déclare une action de type `n8n_event` :

```json
{
  "type": "n8n_event",
  "event_type": "domotic.device_triggered",
  "payload": {
    "scenario": "portal_night_alert"
  }
}
```

**Chemin 2 — Fallback automatique pipeline**

Si une fonction locale échoue et que `N8N_FALLBACK_ENABLED = True`, le pipeline envoie automatiquement à n8n :

```json
{
  "event_type": "workflow.fallback_requested",
  "source": "ada",
  "payload": {
    "original_function": "control_light",
    "original_params": { "room": "salon", "state": "on" },
    "failure_reason": "executor_timeout"
  },
  "initiated_by": "device_uid_abc123"
}
```

### 7.2 Processus d'envoi

```text
1. ADA construit l'enveloppe d'événement standard
2. ADA ajoute initiated_by et universe depuis le contexte session
3. ADA signe la requête avec le token webhook (header X-ADA-Token)
4. ADA POST vers N8N_DEFAULT_WEBHOOK_URL
5. ADA journalise la réponse dans Radar
6. En cas d'erreur : retry selon N8N_MAX_RETRIES, puis log + notification interne
7. ADA ne plante jamais sur un échec n8n
```

### 7.3 Exemple complet — portail la nuit

```json
{
  "event_id": "evt_portal_20260602_231000",
  "event_type": "domotic.device_triggered",
  "source": "ada",
  "target": "n8n",
  "timestamp": "2026-06-02T23:10:00+02:00",
  "idempotency_key": "portal_opened_20260602_231000",
  "correlation_id": "corr_portal_001",
  "initiated_by": "system",
  "universe": "home",
  "payload": {
    "rule_id": "rule_portal_night_alert",
    "scenario": "portal_night_alert",
    "device": "portail",
    "state": "opened",
    "context": { "is_night": true }
  },
  "metadata": {
    "origin_module": "automation",
    "executor": "n8n_bridge"
  }
}
```

### 7.4 Exemple complet — campagne marketing

```json
{
  "event_id": "evt_campaign_20260602_001",
  "event_type": "marketing.campaign_requested",
  "source": "ada",
  "target": "n8n",
  "timestamp": "2026-06-02T17:00:00+02:00",
  "idempotency_key": "campaign_dolibarr_integrators_001",
  "correlation_id": "corr_campaign_001",
  "initiated_by": "device_uid_aurelien_phone",
  "universe": "margep",
  "payload": {
    "campaign_name": "Module Dolibarr pour intégrateurs",
    "channels": ["linkedin"],
    "target": "intégrateurs Dolibarr",
    "objective": "génération de leads",
    "content": {
      "title": "Nouveau module Dolibarr",
      "tone": "professionnel",
      "call_to_action": "Demander une démonstration"
    }
  },
  "metadata": {
    "origin_module": "marketing",
    "requires_human_validation": true
  }
}
```

---

## 8. Flux n8n → ADA (entrant)

### 8.1 Endpoint

```text
POST /api/webhook/n8n
```

Pas de nouvel endpoint. Le webhook existant est la source de vérité.

### 8.2 Authentification

Token webhook transmis via `X-Webhook-Token` (recommandé pour n8n) ou query `?token=`.

Voir `ADA_WEBHOOK.md` section 2 pour le détail complet.

### 8.3 Modes reconnus

Le webhook sélectionne automatiquement le mode selon la structure du payload :

| Structure | Mode | Traitement |
|---|---|---|
| contient `action` | Action directe | FunctionExecutor sans LLM |
| contient `event` sans `text` | Événement | Radar, fire & forget |
| contient `text` / `message` / `query` | Intent texte | Pipeline complet ADA + LLM |

### 8.4 Événements entrants n8n recommandés

Pour les retours de workflows n8n vers ADA, utiliser le mode événement :

```json
{
  "event": "workflow.completed",
  "workflow": "publish_linkedin_post",
  "correlation_id": "corr_campaign_001",
  "status": "completed",
  "result": {
    "post_url": "https://linkedin.com/..."
  },
  "duration_ms": 8420
}
```

Pour déclencher une réponse ADA visible par l'utilisateur, utiliser le mode intent texte :

```json
{
  "text": "La campagne LinkedIn est publiée. URL : https://linkedin.com/...",
  "universe": "margep"
}
```

### 8.5 Exemple complet — lead entrant

```json
POST /api/webhook/n8n?token=<token>
Content-Type: application/json

{
  "event": "lead.created",
  "correlation_id": "corr_lead_001",
  "name": "Jean Dupont",
  "company": "ABC Services",
  "email": "jean.dupont@example.com",
  "origin": "linkedin_campaign",
  "message": "Intéressé par une démonstration",
  "workflow": "linkedin_lead_capture"
}
```

ADA reçoit cet événement en mode fire & forget, l'enregistre dans Radar, et peut déclencher une règle interne (qualification lead, notification membre, création tâche).

---

## 9. Fallback n8n

### 9.1 Définition

Quand `N8N_FALLBACK_ENABLED = True` et qu'une fonction ADA locale échoue, le pipeline envoie automatiquement la demande à n8n avant de retourner une erreur à l'utilisateur.

### 9.2 Conditions de déclenchement

```text
- La fonction est dans la liste FUNCTIONS de config.py
- L'executor local retourne une erreur ou timeout
- N8N_FALLBACK_ENABLED = True
- N8N_BASE_URL est configuré et joignable
```

### 9.3 Format de la requête fallback vers n8n

```json
POST http://localhost:5678/webhook/ada-event

{
  "event_type": "workflow.fallback_requested",
  "source": "ada",
  "initiated_by": "device_uid_abc123",
  "universe": "home",
  "payload": {
    "original_function": "control_light",
    "original_params": { "room": "salon", "state": "on" },
    "failure_reason": "executor_timeout",
    "user_message": "Allume le salon"
  }
}
```

### 9.4 Format de réponse attendu de n8n

ADA attend un JSON avec un champ `reply` pour réinjecter la réponse dans le pipeline SSE :

```json
{
  "ok": true,
  "reply": "Lumière du salon allumée via n8n.",
  "result": { "success": true }
}
```

Si n8n retourne `ok: false` ou si la requête échoue, ADA génère une réponse d'erreur LLM standard — n8n ne bloque jamais le pipeline.

### 9.5 Comportement si n8n est indisponible

```text
- timeout après N8N_TIMEOUT_SECONDS
- log Radar : n8n_fallback_failed
- ADA continue avec réponse d'erreur locale
- aucun crash, aucun blocage du pipeline
- retry : N8N_MAX_RETRIES (défaut : 2)
```

---

## 10. Configuration

Les paramètres n8n s'intègrent dans `config.py` dans `MODULES_ENABLED` et un bloc dédié.

### 10.1 `MODULES_ENABLED`

```python
MODULES_ENABLED: dict = {
    "societe": True,
    "domotique": True,
    "proxmox": True,
    "rmm": True,
    "telephony": False,
    "margepro": True,
    "music": False,
    "n8n_bridge": True,       # ← active le connecteur sortant
    "n8n_fallback": True,     # ← active le fallback automatique pipeline
}
```

### 10.2 Bloc configuration n8n

```python
# --- N8N Bridge ---
N8N_BASE_URL             = "http://localhost:5678"
N8N_DEFAULT_WEBHOOK_URL  = "http://localhost:5678/webhook/ada-event"
N8N_TIMEOUT_SECONDS      = 10
N8N_MAX_RETRIES          = 2
N8N_VERIFY_SSL           = True

N8N_ALLOWED_EVENT_DOMAINS = [
    "domotic",
    "marketing",
    "social",
    "lead",
    "crm",
    "support",
    "content",
    "notification",
    "workflow",
    "system",
]
```

Le secret partagé (si activé en Phase 5) sera lu depuis une variable d'environnement, jamais stocké en clair dans `config.py` :

```python
N8N_WEBHOOK_SECRET = os.getenv("ADA_N8N_SECRET", "")
```

---

## 11. Composants techniques

### 11.1 `N8nBridgeConnector` — sortant

```python
class N8nBridgeConnector:
    def __init__(self, config, http_client=None, logger=None):
        pass

    def send_event(
        self,
        event_type: str,
        payload: dict,
        initiated_by: str = "system",
        universe: str | None = None,
        metadata: dict | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        pass

    def send_fallback(
        self,
        original_function: str,
        original_params: dict,
        failure_reason: str,
        user_message: str,
        initiated_by: str = "system",
        universe: str | None = None,
    ) -> dict:
        pass

    def _build_envelope(self, event_type: str, payload: dict, **kwargs) -> dict:
        pass

    def _build_headers(self) -> dict:
        pass
```

### 11.2 `N8nEventValidator` — entrant

Contrôles appliqués aux événements entrants depuis n8n :

```text
- présence de event ou text ou action (au moins un)
- si event présent : domaine autorisé
- taille maximale payload < 512 KB
- timestamp si présent : skew < N8N_MAX_CLOCK_SKEW_SECONDS (Phase 5)
```

### 11.3 `N8nEventRouter` — entrant

```python
class N8nEventRouter:
    def route(self, event: dict) -> dict:
        domain = event.get("event_type", event.get("event", "")).split(".")[0]

        handlers = {
            "lead":         self.lead_handler,
            "marketing":    self.marketing_handler,
            "domotic":      self.domotic_handler,
            "workflow":     self.workflow_handler,
            "crm":          self.crm_handler,
            "support":      self.support_handler,
            "notification": self.notification_handler,
            "social":       self.social_handler,
            "content":      self.content_handler,
            "system":       self.system_handler,
        }

        handler = handlers.get(domain, self.default_handler)
        return handler.handle(event)
```

Comportement du `default_handler` :

```text
- log structuré dans Radar
- aucune action métier
- retourne { "status": "logged", "action": "none" }
```

### 11.4 `N8nEventStore` — journalisation

Table SQLite `integration_events` :

```sql
CREATE TABLE integration_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    source           TEXT NOT NULL,
    target           TEXT,
    direction        TEXT NOT NULL,      -- outbound | inbound
    initiated_by     TEXT,               -- device_uid | "system"
    universe         TEXT,               -- home | opent | uscss | margep
    idempotency_key  TEXT,
    correlation_id   TEXT,
    status           TEXT NOT NULL,      -- pending|sent|received|processed|duplicate|failed|ignored
    payload_json     TEXT,
    metadata_json    TEXT,
    error_message    TEXT,
    created_at       TEXT NOT NULL,
    processed_at     TEXT
);

CREATE INDEX idx_ievents_event_id      ON integration_events(event_id);
CREATE INDEX idx_ievents_idempotency   ON integration_events(idempotency_key);
CREATE INDEX idx_ievents_correlation   ON integration_events(correlation_id);
CREATE INDEX idx_ievents_type          ON integration_events(event_type);
CREATE INDEX idx_ievents_initiated_by  ON integration_events(initiated_by);
CREATE INDEX idx_ievents_universe      ON integration_events(universe);
```

---

## 12. Intégration dans le pipeline web

### 12.1 Position dans `web/pipeline.py`

Le bridge n8n s'insère à deux points du pipeline :

```text
Étape 3 — Routage déterministe
  └── Si action de type n8n_event → N8nBridgeConnector.send_event()

Étape 7 — Dispatch plugin / n8n / executor
  └── Si executor local échoue ET N8N_FALLBACK_ENABLED
      └── N8nBridgeConnector.send_fallback()
      └── Si réponse ok → réinjecter reply dans SSE stream
      └── Si échec → continuer avec erreur LLM standard
```

### 12.2 Position dans `web/router_webhook.py`

Le router webhook existant est étendu avec :

```text
- validation du domaine si event_type présent (N8N_ALLOWED_EVENT_DOMAINS)
- extraction de correlation_id depuis le payload
- routage vers N8nEventRouter si event_type suit la convention domaine.action
- journalisation dans integration_events
```

### 12.3 Route à ajouter dans la table officielle

| Route | Méthode | Rôle |
|---|---|---|
| `/api/webhook/n8n` | POST | Endpoint entrant n8n (via webhook existant) |
| `/api/integrations/n8n/status` | GET | État du bridge : activé, URL, derniers événements |
| `/api/integrations/n8n/events` | GET | Liste paginée des événements `integration_events` |
| `/api/integrations/n8n/events/{event_id}/retry` | POST | Relance manuelle d'un événement sortant échoué |

---

## 13. Sécurité

### 13.1 Webhook token (actuel)

```text
- token généré avec secrets.token_urlsafe(32) — 256 bits d'entropie
- comparaison via hmac.compare_digest() — résistant timing attacks
- token jamais loggué
- rotation disponible : POST /api/webhook/config/rotate
```

### 13.2 Règles pour les événements entrants

```text
- domaine non autorisé → 403 ou ignore silencieux (configurable)
- payload > 512 KB → 400
- token invalide → 401 (retour immédiat sans traitement)
- secret jamais exposé dans les réponses d'erreur
```

### 13.3 Règles pour les événements sortants

```text
- URL n8n lue depuis config, jamais depuis le payload utilisateur
- initiated_by résolu depuis la session ADA, jamais depuis un champ utilisateur libre
- en cas d'erreur n8n, le message d'erreur retourné à l'utilisateur ne contient pas l'URL ni le token n8n
```

### 13.4 HMAC sur body (Phase 5 — optionnel)

Si activé, chaque appel ADA → n8n portera :

```text
X-ADA-Event-Id: evt_...
X-ADA-Timestamp: 2026-06-02T14:30:00+02:00
X-ADA-Signature: sha256=<hmac_sha256(secret, timestamp + "." + raw_body)>
```

Secret lu depuis variable d'environnement `ADA_N8N_SECRET`, jamais depuis `config.py` directement.

---

## 14. Logs et supervision Radar

### 14.1 Champs de log structuré

```text
timestamp
direction         outbound | inbound
event_id
event_type
source
target
initiated_by
universe
correlation_id
status
duration_ms
error_code
error_message
```

### 14.2 Règles de log

```text
- token et secrets : jamais loggués
- payload > 2 KB : tronqué dans les logs, complet en base
- erreurs n8n : loggées avec cause, sans exposer les credentials
- doublons idempotency : loggués avec statut "duplicate", non retraités
```

### 14.3 Événements Radar minimum

```text
n8n_event_sent          événement sortant envoyé avec succès
n8n_event_failed        événement sortant en erreur
n8n_fallback_triggered  fallback déclenché depuis le pipeline
n8n_fallback_ok         fallback réussi, réponse réinjectée
n8n_fallback_failed     fallback échoué, erreur LLM standard
n8n_event_received      événement entrant reçu
n8n_event_processed     événement entrant traité
n8n_event_duplicate     doublon détecté
n8n_event_rejected      domaine non autorisé
```

---

## 15. Cas d'usage détaillés

### 15.1 Domotique — portail la nuit

```text
Portail s'ouvre à 23h10
→ Règle ADA "rule_portal_night_alert" déclenchée
→ N8nBridgeConnector.send_event("domotic.device_triggered", {...}, initiated_by="system", universe="home")
→ n8n reçoit l'événement
→ n8n envoie une notification Telegram
→ n8n rappelle ADA : POST /api/webhook/n8n {"event":"workflow.completed", "correlation_id":"..."}
→ ADA journalise, Radar mis à jour
```

### 15.2 Marketing — campagne LinkedIn

```text
Aurélien (device_uid_phone) : "Prépare une campagne LinkedIn pour mon module Dolibarr"
→ ADA prépare le contenu, demande validation
→ Aurélien confirme
→ N8nBridgeConnector.send_event("marketing.campaign_requested", {...}, initiated_by="device_uid_phone", universe="margep")
→ n8n orchestre : brouillon LinkedIn, notification, rappel ADA
→ n8n : POST /api/webhook/n8n {"text":"La campagne est prête pour validation.", "universe":"margep"}
→ ADA envoie la notification à Aurélien via SSE
```

### 15.3 Lead entrant

```text
n8n reçoit un formulaire LinkedIn
→ n8n : POST /api/webhook/n8n {"event":"lead.created", "name":"Jean Dupont", ...}
→ ADA reçoit, N8nEventRouter → lead_handler
→ lead_handler crée une tâche dans le planificateur ADA
→ ADA notifie le membre concerné (selon universe / user_id)
→ Radar : n8n_event_processed
```

### 15.4 Fallback fonction locale

```text
Aurélien : "Allume le salon"
→ Pipeline ADA → tool-calling → control_light
→ executor local timeout après 5s
→ N8N_FALLBACK_ENABLED = True → send_fallback(...)
→ n8n exécute le workflow "control_light_fallback"
→ n8n répond {"ok": true, "reply": "Lumière salon allumée."}
→ ADA réinjecte dans le SSE stream
→ Aurélien voit la réponse normalement
```

---

## 16. Réponses HTTP

| Cas | Code | Body |
|---|---|---|
| Succès | 200 | `{"ok": true, "source": "n8n", ...}` |
| Doublon idempotency | 200 | `{"ok": true, "status": "duplicate"}` |
| Payload invalide | 400 | `{"detail": "Payload non reconnu"}` |
| Token invalide | 401 | `{"detail": "Token webhook invalide ou manquant"}` |
| Domaine non autorisé | 403 | `{"detail": "Event domain not allowed"}` |
| Bridge désactivé | 404 | `{"detail": "N8N bridge disabled"}` |
| Erreur interne | 500 | `{"detail": "Erreur interne ADA"}` |

---

## 17. Roadmap

### Phase 1 — Pont sortant minimal (complète ce qui existe)

```text
- N8nBridgeConnector avec initiated_by et universe
- Action de règle n8n_event documentée et testée
- Journalisation Radar des envois sortants
- Variables config.py N8N_BRIDGE_ENABLED, N8N_DEFAULT_WEBHOOK_URL
```

### Phase 2 — Fallback pipeline (formalise ce qui existe)

```text
- Documenter et tester le comportement N8N_FALLBACK_ENABLED
- Spécifier le contrat de réponse n8n attendu (champ reply)
- Journalisation Radar fallback_triggered / fallback_ok / fallback_failed
- Test timeout et retry
```

### Phase 3 — Routage métier entrant

```text
- N8nEventRouter avec tous les handlers de domaine
- Validation domaine sur /api/webhook/n8n
- Journalisation dans integration_events
- Handlers : domotic, marketing, lead, workflow, default
```

### Phase 4 — Supervision

```text
- Route GET /api/integrations/n8n/events (liste paginée)
- Route GET /api/integrations/n8n/status
- Affichage dans l'UI ADA (onglet Paramètres ou Plugins)
- Filtre par statut, type, direction, universe, initiated_by
- Relance manuelle d'un événement sortant échoué
```

### Phase 5 — Sécurité renforcée (optionnel)

```text
- HMAC SHA-256 sur le body sortant (X-ADA-Signature)
- Vérification signature sur les événements entrants n8n
- Protection anti-rejeu timestamp (N8N_MAX_CLOCK_SKEW_SECONDS)
- Idempotence stricte via integration_events
- Variable d'environnement ADA_N8N_SECRET
```

---

## 18. Critères d'acceptation

```text
A-01  ADA peut envoyer un événement normalisé vers n8n avec initiated_by et universe
A-02  ADA reçoit des événements n8n via /api/webhook/n8n sans nouvel endpoint
A-03  Le fallback n8n réinjecte correctement la réponse dans le SSE stream
A-04  Un échec n8n ne plante pas le pipeline ADA
A-05  Les événements sont journalisés dans integration_events
A-06  Les domaines non autorisés sont refusés
A-07  Le token webhook n'apparaît jamais dans les logs
A-08  ADA fonctionne si N8N_BRIDGE_ENABLED = False
A-09  Le device_uid de l'initiateur est tracé dans les événements sortants
A-10  La rotation du token webhook invalide immédiatement l'ancien token
```

---

## 19. Tests attendus

### 19.1 Tests unitaires

```text
- construction de l'enveloppe avec initiated_by et universe
- envoi sortant avec retry sur timeout
- validation domaine autorisé / refusé
- routage par domaine vers handler correct
- comportement default_handler
- format réponse fallback ok / ko
- idempotency_key : doublon non retraité
```

### 19.2 Tests d'intégration

```text
- ADA envoie un événement vers un webhook n8n de test
- n8n (ou simulateur) envoie un événement vers /api/webhook/n8n
- fallback déclenché sur timeout executor local
- réponse fallback n8n réinjectée dans SSE
- doublon idempotency_key
- N8N_BRIDGE_ENABLED = False
- n8n indisponible (timeout) → pipeline continue
```

### 19.3 Tests manuels

```text
1. Créer un workflow n8n avec Webhook → log payload reçu
2. Déclencher une règle ADA de type n8n_event
3. Vérifier que n8n reçoit l'événement avec initiated_by et universe
4. Créer un workflow n8n qui rappelle ADA via /api/webhook/n8n
5. Vérifier que ADA route l'événement et journalise
6. Simuler un timeout executor → vérifier fallback → vérifier SSE
7. Désactiver n8n → vérifier qu'ADA répond normalement
```

---

## 20. Points d'attention

**Garder ADA simple.** Le connecteur ne doit pas devenir un deuxième n8n. Toute logique d'orchestration complexe reste dans n8n.

**Ne pas rendre ADA dépendant de n8n.** n8n est un accélérateur, pas une dépendance cœur. `N8N_BRIDGE_ENABLED = False` doit produire un ADA 100% fonctionnel.

**`initiated_by` résolu côté ADA uniquement.** Jamais depuis un champ libre du payload utilisateur ou n8n — toujours depuis le contexte de session ADA.

**Un seul tuyau entrant.** `/api/webhook/n8n` est et reste la source de vérité. Ne pas créer de doublon.

**Le contrat de réponse fallback est strict.** n8n doit retourner `{"ok": true, "reply": "..."}`. Documenter ce contrat dans les workflows n8n côté utilisateur.

---

## 21. Synthèse

```text
- webhook existant /api/webhook/n8n = tuyau entrant officiel
- N8nBridgeConnector = tuyau sortant, enrichi avec initiated_by et universe
- fallback pipeline = feature de premier rang, déjà dans l'UI
- un seul secret = le token webhook existant (HMAC optionnel Phase 5)
- session_id = device_uid + conversation_id (mécanique QR code)
- journalisation dans integration_events avec colonnes initiated_by et universe
```

> ADA utilise n8n comme moteur d'orchestration externe via le webhook existant et un connecteur sortant enrichi. ADA reste responsable de l'intelligence, du contexte, de l'identité des membres et de la supervision. n8n reste responsable des intégrations et des workflows visuels.

---

## 22. Découverte dynamique des workflows ADA depuis l'API n8n

> **Implémenté dans** `core/n8n_executor.py` — méthodes `_discover_workflows()`, `get_function_definitions()`.

### 22.1 Principe

ADA interroge l'API REST n8n au démarrage pour lister les workflows actifs.
Tout workflow qui satisfait la **convention de nommage ADA** est automatiquement :

1. Découvert et analysé (extraction du path webhook depuis les nodes)
2. Exposé comme **fonction LLM** dans le pipeline tool-calling
3. Déclenché directement par `POST /webhook/<path>` quand le LLM l'appelle

**Aucun fichier de configuration côté ADA n'est requis.** Il suffit de créer le workflow dans n8n.

### 22.2 Convention de nommage

Un workflow est pris en compte par ADA si **au moins une** des conditions est vraie :

| Condition | Exemple |
|---|---|
| Le nom commence par `ADA` (insensible à la casse) | `ADA - Speed Test`, `ADA: Rapport hebdo` |
| Le workflow possède le tag `ada` | tag `ada` ajouté dans n8n |

Exemples de noms valides :

```text
ADA - Speed Test          ✓
ADA : Rapport hebdo       ✓
ADA Speed Test            ✓
ada test debit            ✓  (tag "ada" requis si le nom ne commence pas par ADA)
Speed Test                ✗  (ni préfixe ADA, ni tag ada)
```

### 22.3 Dérivation du nom de fonction LLM

Le nom de la fonction LLM est dérivé automatiquement depuis le **path du nœud Webhook** présent dans le workflow.

```text
Webhook node path   →  Nom de fonction LLM
ada-speed-test      →  ada_speed_test
speed-test          →  speed_test
rapport-hebdo       →  rapport_hebdo
```

**Règle** : le path du nœud webhook est slugifié (minuscules, caractères non-alphanumériques → tiret), puis les tirets sont remplacés par des underscores.

Si le workflow ne contient aucun nœud webhook, ADA applique le slug du nom du workflow comme fallback :

```text
"ADA - Speed Test"  →  slug  →  "ada-speed-test"  →  func  "ada_speed_test"
```

### 22.4 Dérivation du path webhook

Le path utilisé pour `POST /webhook/<path>` est extrait du nœud de type `n8n-nodes-base.webhook` présent dans le workflow.

**Priorité** :
1. `nodes[].parameters.path` du nœud webhook (valeur explicite dans n8n)
2. Slug du nom du workflow (fallback si aucun nœud webhook trouvé)

**Recommandation** : définir le path webhook explicitement dans le nœud n8n pour éviter le fallback. Convention recommandée :

```text
Nom du workflow       →  Path webhook recommandé
ADA - Speed Test      →  ada-speed-test
ADA : Rapport hebdo   →  ada-rapport-hebdo
ADA Scan Réseau       →  ada-scan-reseau
```

### 22.5 Description LLM

La description exposée au LLM pour chaque fonction est dérivée dans cet ordre de priorité :

1. `meta.templateNotes` du workflow (notes de template dans n8n) — **recommandé**
2. Fallback généré : `"Workflow n8n : <nom du workflow>. Appelle ce workflow via ADA."`

**Recommandation** : renseigner les `Template notes` du workflow dans n8n avec une description claire du rôle et des paramètres attendus. Ces notes sont directement injectées dans le prompt LLM.

Exemple de note efficace :

```text
Effectue un test de débit réseau (upload et download) et retourne les résultats en Mbit/s.
Aucun paramètre requis.
```

### 22.6 Cache et rafraîchissement

La découverte des workflows est mise en cache avec un TTL de **5 minutes**.

```text
Démarrage ADA       →  _discover_workflows() → appel API n8n → cache peuplé
5 min plus tard     →  prochain appel → cache expiré → redécouverte automatique
Nouveau workflow    →  visible dans ADA au maximum 5 min après activation dans n8n
```

Pour forcer une redécouverte immédiate sans redémarrer le serveur :

```python
from core.n8n_executor import n8n_executor
n8n_executor.invalidate_discovery_cache()
```

### 22.7 Enregistrement des webhooks

Lors de chaque découverte, les URLs de webhook sont enregistrées dans `_plugin_webhooks` sous **deux clés** pour maximiser la résolution :

```text
"ada-speed-test"  →  http://localhost:5678/webhook/ada-speed-test
"ada_speed_test"  →  http://localhost:5678/webhook/ada-speed-test
```

Ce double enregistrement garantit que `dispatch_action()` trouve l'URL que le nom contienne des tirets ou des underscores.

### 22.8 Flux complet — exemple "ADA - Speed Test"

```text
1. Dans n8n :
   - Créer le workflow "ADA - Speed Test"
   - Ajouter un nœud Webhook avec path = "ada-speedtest"
   - Activer le workflow

2. ADA démarre (ou 5 min s'écoulent) :
   - GET /api/v1/workflows → retourne le workflow
   - Filtre : nom commence par "ADA" ✓
   - Extraction du nœud webhook → path = "ada-speedtest"
   - func_name = "ada_speedtest"
   - webhook enregistré : http://localhost:5678/webhook/ada-speedtest

3. Utilisateur dans le chat ADA :
   "Lance un test de débit"

4. Pipeline ADA :
   - effective_functions inclut { name: "ada_speedtest", description: "..." }
   - LLM retourne tool_call { name: "ada_speedtest", arguments: {} }
   - Validation : "ada_speedtest" est dans known_func_names ✓
   - dispatch_action("ada_speedtest", {})
   - Aucun plugin ne gère "ada_speedtest"
   - Fallback → n8n_executor.call("ada_speedtest", {})
   - POST http://localhost:5678/webhook/ada-speedtest {"params": {}}
   - n8n exécute le workflow, retourne {"success": true, "message": "Download: 940 Mbit/s, Upload: 420 Mbit/s"}
   - ADA affiche le résultat dans le chat
```

### 22.9 Prérequis côté n8n

| Prérequis | Valeur |
|---|---|
| API REST n8n activée | Paramètres n8n → API → Enable Public API |
| Clé API n8n | Générée dans n8n → Settings → API Keys |
| Clé enregistrée dans ADA | `settings.json` → `n8n.api_key` |
| URL n8n | `settings.json` → `n8n.url` (défaut : `http://localhost:5678`) |
| Workflow actif | Le toggle "Active" doit être ON dans n8n |

### 22.10 Résolution des alias LLM

Le LLM peut halluciner des noms de fonctions proches des noms réels. ADA maintient une table d'alias dans `web/pipeline.py` (`_FUNC_ALIASES`) qui redirige silencieusement les variantes connues avant validation :

```python
# Exemples d'alias actifs
"proxmox_list_nodes"   → "vm_list"
"proxmox_nodes:list"   → "proxmox_instances_list"
"describe_proxmox_nodes" → "proxmox_instances_list"
"list_societes"        → "list_companies"
```

Un événement Radar `llm.function_alias_resolved` (level: info) est émis à chaque résolution d'alias.
Si le nom halluciné n'est ni dans la table d'alias ni dans les fonctions connues, un événement `llm.hallucinated_function` (level: warning) est émis et un message d'erreur est retourné à l'utilisateur.

### 22.11 Désactivation

Si `n8n.api_key` est absent de la configuration, la découverte est silencieusement désactivée.
`get_function_definitions()` retourne une liste vide, sans erreur ni avertissement bloquant.

