# ADA — Spécification : Intent Pipeline

**Projet :** ADA local  
**Branche cible :** `univers`  
**Périmètre :** `web/pipeline.py`, `config.py`, couche web uniquement  
**Hors périmètre :** `main.py`, `/gui`, entraînement de modèle  
**Remplace :** `SPEC_INTENT_DETECTION.md`, `SPEC_STRUCTURED_OUTPUT.md`  
**Document :** spécification fonctionnelle  
**Version :** 1.0  
**Date :** 2026-06-05  
**Dépendances :** `SPEC_RADAR_INTEGRATION.md`, `ADA_SPEC_N8N_BRIDGE.md`

---

## 1. Contexte et décision architecturale

Le pipeline web actuel repose sur deux mécanismes pour résoudre les intentions :

1. Routages déterministes codés en dur — listes de mots-clés, patterns fixes.
2. Tool-calling LLM via `FUNCTIONS` avec fallbacks textuels.

Ces deux mécanismes ont la même limite fondamentale : ils sont **interprétatifs**. Le pipeline devine l'intention depuis le texte. Les mots-clés sont implicitement monolingues. Les fallbacks textuels sont fragiles.

La décision prise ici est de remplacer cette logique par un pipeline en trois couches qui sépare clairement trois responsabilités distinctes :

- **comprendre** ce que l'utilisateur veut
- **résoudre** vers les vraies entités des systèmes connectés
- **exécuter** via le pipeline existant

Les mots-clés codés en dur disparaissent. Le système devient naturellement multilingue — la langue n'intervient qu'entre l'utilisateur et le LLM. Tout ce qui suit travaille sur des identifiants.

---

## 2. Vue d'ensemble du pipeline

```
Requête utilisateur (toute langue)
        ↓
[ Couche 1 — Extraction LLM ]
  Appel LLM avec prompt minimal
  Produit un bloc JSON sémantique :
  intent + action + params sémantiques + response + confidence
        ↓ bloc valide et confidence ≥ seuil
[ Couche 2 — Entity Resolver ]
  Mappe les params sémantiques vers les vrais identifiants
  Domoticz, Proxmox, Dolibarr, RMM...
  Résolution fuzzy locale, sans LLM
        ↓ entités résolues
[ Couche 3 — Pipeline existant ]
  Reçoit intent + params résolus
  Dispatch, confirmation, exécution, mémoire
  Comportement inchangé
```

**Règle fondamentale :** si la Couche 1 ne produit pas un bloc valide avec une confiance suffisante, le pipeline existant est appelé directement dans son état actuel. Rien ne casse.

---

## 3. Couche 1 — Extraction LLM

### 3.1 Rôle

Le LLM reçoit la requête de l'utilisateur et un prompt système minimal. Il produit un bloc JSON décrivant l'intention sémantique. Il ne connaît pas la liste des entités existantes — ce n'est pas son rôle.

### 3.2 Prompt système

Le prompt système de la Couche 1 est court et stable. Il ne contient pas de listes d'entités. Il contient :

- la description du schéma JSON attendu
- la liste des domaines d'action possibles
- des exemples few-shot par domaine
- la règle de confidence

```
Tu es un extracteur d'intention pour un assistant domotique et infrastructure.

Tu réponds UNIQUEMENT en JSON valide, sans texte avant ni après.

Schéma :
{
  "intent": "<description courte de l'intention>",
  "domain": "<home|infra|crm|media|system|unknown>",
  "action": "<verbe sémantique : control, query, create, delete, backup, ...>",
  "params": {
    "entity": "<nom tel que formulé par l'utilisateur>",
    "state": "<on|off|dim|..., si applicable>",
    "value": "<valeur numérique ou textuelle, si applicable>"
  },
  "response": "<réponse courte à afficher si aucune résolution n'est nécessaire>",
  "confidence": <0.0 à 1.0>
}

Règles :
- params.entity = ce que l'utilisateur a dit, pas une interprétation
- confidence = ta certitude sur l'intention, pas sur l'entité
- si la requête est conversationnelle, domain = "system", action = "passthrough"
- répondre dans la langue de l'utilisateur dans le champ response
```

### 3.3 Schéma de sortie

```json
{
  "intent": "allumer la lumière du salon",
  "domain": "home",
  "action": "control",
  "params": {
    "entity": "salon",
    "state": "on"
  },
  "response": "",
  "confidence": 0.96
}
```

```json
{
  "intent": "backup de la VM compta",
  "domain": "infra",
  "action": "backup",
  "params": {
    "entity": "compta"
  },
  "response": "",
  "confidence": 0.93
}
```

```json
{
  "intent": "question conversationnelle",
  "domain": "system",
  "action": "passthrough",
  "params": {},
  "response": "Les backups de la nuit sont tous réussis, 18 sur 18.",
  "confidence": 1.0
}
```

### 3.4 Appel Ollama

```python
payload = {
    "model": config.INTENT_MODEL,   # configurable, défaut = RESPONDER_MODEL
    "messages": [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": message}
    ],
    "stream": False,
    "format": "json"
}
```

Le stream est désactivé pour la Couche 1 — on attend le bloc complet avant de continuer. La latence est acceptable car le prompt est court et le contexte minimal.

### 3.5 Seuils

| Condition | Décision |
|---|---|
| `confidence` ≥ 0.85 et `domain` != unknown | Passe en Couche 2 |
| `action` = passthrough | Réponse directe, Couches 2 et 3 ignorées |
| `confidence` < 0.85 ou JSON invalide | Fallback pipeline existant |

---

## 4. Couche 2 — Entity Resolver

### 4.1 Rôle

L'Entity Resolver reçoit les params sémantiques de la Couche 1 et les mappe vers les vrais identifiants des systèmes connectés. Il travaille localement, sans LLM, sur des index construits depuis les APIs externes.

C'est ici que vit la connaissance des entités réelles. Pas dans le prompt.

### 4.2 Principe de résolution

Pour chaque `params.entity` reçu, le resolver :

1. identifie le domaine depuis `domain`
2. interroge l'index correspondant
3. cherche la correspondance par matching fuzzy sur les noms et aliases
4. retourne l'identifiant réel si la correspondance dépasse le seuil

```python
@dataclass
class ResolvedEntity:
    found: bool
    identifier: str | None     # identifiant réel dans le système source
    source: str | None         # "domoticz", "proxmox", "dolibarr", "rmm"
    display_name: str | None   # nom tel qu'il apparaît dans la source
    confidence: float
    candidates: list[dict]     # autres candidats si ambiguïté
```

### 4.3 Sources et stratégies de synchronisation

Chaque source a sa propre stratégie de synchronisation de l'index local.

| Source | Contenu de l'index | Stratégie |
|---|---|---|
| Domoticz / HA | entités, scènes, groupes | polling périodique configurable |
| Proxmox | nœuds déclarés dans ADA, VMs et CTs lus via API | event-driven pour les nœuds, polling pour VMs/CTs |
| Dolibarr | sociétés, contacts | polling périodique |
| RMM | clients, devices | polling périodique |

**Proxmox — cas particulier :**

Les nœuds sont déclarés dans ADA — leur ajout ou suppression dans la configuration ADA met à jour l'index immédiatement. Les VMs et CTs vivent dans Proxmox — ils sont lus via l'API au polling.

**Domoticz / HA — cas particulier :**

La configuration vit entièrement dans l'outil externe. ADA ne reçoit pas d'événements de configuration. Le polling est la seule stratégie viable. Si l'outil supporte les webhooks sortants sur changement de configuration, ils peuvent alimenter un rebuild déclenché.

### 4.4 Rebuild de l'index

Trois déclencheurs possibles :

```
1. Automatique — polling périodique selon config par source
2. Event-driven — ajout ou suppression d'un connecteur dans ADA
3. Manuel — commande utilisateur ou bouton dans l'interface
```

Commande naturelle :

```
"ADA, mets à jour ton contexte"  →  rebuild complet de tous les index
"ADA, recharge la domotique"     →  rebuild index Domoticz uniquement
```

Le rebuild se fait en arrière-plan. L'index précédent reste actif pendant ce temps.

### 4.5 Gestion des ambiguïtés

Si le resolver trouve plusieurs candidats proches, il ne demande pas "quelle entité ?" de manière générique. Il propose les candidats identifiés :

```
Utilisateur : "allume la lumière du bureau"
Resolver    : deux candidats — "bureau_rdc" et "bureau_r1", confidence 0.71 chacun
ADA         : "Tu veux dire le bureau du rez-de-chaussée ou celui du premier ?"
```

Si un seul candidat avec confidence ≥ seuil : exécution directe, pas de question.

### 4.6 Seuils Entity Resolver

| Score | Décision |
|---|---|
| ≥ 0.85 | Résolution certaine — dispatch direct |
| 0.60 – 0.84 | Ambiguïté — proposer les candidats |
| < 0.60 | Non trouvé — réponse "entité inconnue" |

---

## 5. Couche 3 — Pipeline existant

### 5.1 Rôle

Le pipeline existant reçoit en entrée :

- l'intent résolu
- l'action sémantique
- les params avec identifiants réels

Il exécute via les dispatchers existants — Domoticz, Proxmox, n8n bridge, etc. Son comportement est inchangé. Il n'a pas besoin de savoir qu'il est appelé depuis l'Intent Pipeline ou directement.

### 5.2 Fallback

Si la Couche 1 échoue ou la confidence est insuffisante, le pipeline existant est appelé avec le message original, exactement comme aujourd'hui. Aucune régression possible.

---

## 6. Contrat JSON entre les couches

```
Couche 1 → Couche 2
{
  "intent": string,
  "domain": string,
  "action": string,
  "params": { "entity": string, "state"?: string, "value"?: string },
  "confidence": float
}

Couche 2 → Couche 3
{
  "intent": string,
  "domain": string,
  "action": string,
  "params": {
    "entity_raw": string,       // ce que l'utilisateur a dit
    "entity_id": string,        // identifiant réel dans la source
    "entity_source": string,    // "domoticz" | "proxmox" | ...
    "state"?: string,
    "value"?: string
  },
  "confidence_intent": float,
  "confidence_entity": float
}
```

---

## 7. Événements Radar

| Type | Level | Émis par |
|---|---|---|
| `intent.extracted` | info | Couche 1 — bloc JSON produit |
| `intent.passthrough` | info | Couche 1 — réponse directe |
| `intent.low_confidence` | info | Couche 1 — fallback pipeline |
| `intent.invalid_json` | warning | Couche 1 — JSON malformé |
| `entity.resolved` | info | Couche 2 — entité trouvée |
| `entity.ambiguous` | info | Couche 2 — plusieurs candidats |
| `entity.not_found` | info | Couche 2 — aucune correspondance |
| `entity.index_rebuilt` | info | Couche 2 — rebuild terminé |
| `intent.pipeline.fallback` | info | Global — bascule pipeline legacy |

---

## 8. Configuration

```python
# --- Intent Pipeline ---
INTENT_PIPELINE_ENABLED = True
INTENT_MODEL = RESPONDER_MODEL          # modèle pour la Couche 1, configurable indépendamment

INTENT_CONFIDENCE_THRESHOLD = 0.85     # seuil Couche 1 pour passer en Couche 2
ENTITY_CONFIDENCE_THRESHOLD = 0.85     # seuil Couche 2 pour dispatch direct
ENTITY_AMBIGUITY_THRESHOLD = 0.60      # seuil en dessous = entité inconnue

# Polling par source (secondes)
ENTITY_SYNC_INTERVAL_DOMOTICZ = 300    # 5 minutes
ENTITY_SYNC_INTERVAL_PROXMOX = 600     # 10 minutes
ENTITY_SYNC_INTERVAL_DOLIBARR = 3600   # 1 heure
ENTITY_SYNC_INTERVAL_RMM = 600         # 10 minutes
```

---

## 9. Critères d'acceptation

### A-001 — Non-régression
- `INTENT_PIPELINE_ENABLED = False` remet le pipeline dans son état exact d'avant.
- Tout échec de la Couche 1 ou 2 bascule silencieusement sur le pipeline legacy.

### A-002 — Multilingue
- Une requête en anglais, français, ou toute autre langue produit le même bloc JSON en Couche 1.
- L'Entity Resolver ne voit jamais la langue de l'utilisateur.

### A-003 — Pas de mots-clés codés en dur
- Aucun pattern ou mot-clé de routage dans le pipeline pour les actions domotiques et infra.
- Le verbe utilisé par l'utilisateur n'influe pas sur la résolution de l'entité.

### A-004 — Entity Resolver
- Une entité connue avec confidence ≥ seuil est résolue sans question à l'utilisateur.
- Une ambiguïté produit une question ciblée avec les candidats identifiés.
- Une entité inconnue produit un message clair, pas une hallucination.

### A-005 — Synchronisation
- L'ajout d'un nœud Proxmox dans ADA met à jour l'index immédiatement.
- Le polling se déclenche selon les intervalles configurés.
- Un rebuild manuel fonctionne via commande naturelle ou interface.

### A-006 — Radar
- Chaque requête produit au minimum un événement Radar de décision dans la Couche 1.
- Les rebuilds d'index sont tracés.

---

## 10. Fichiers à créer ou modifier

| Fichier | Action |
|---|---|
| `core/intent/intent_extractor.py` | Créer — appel LLM Couche 1, validation bloc JSON |
| `core/intent/entity_resolver.py` | Créer — matching fuzzy, gestion index par source |
| `core/intent/entity_index.py` | Créer — construction et mise à jour des index par source |
| `web/pipeline.py` | Modifier — insertion Couches 1 et 2 avant pipeline existant |
| `web/server.py` | Modifier — démarrage des pollings d'index au lifespan |
| `config.py` | Modifier — variables `INTENT_PIPELINE_*` et `ENTITY_SYNC_*` |
| `web/prompts/intent_system.txt` | Créer — prompt système Couche 1, à itérer |

---

## 11. Priorités d'implémentation

1. Prompt système Couche 1 + few-shot par domaine — itération manuelle avant tout code
2. `IntentExtractor` — appel Ollama format:json, validation schéma
3. Insertion Couche 1 dans pipeline avec fallback
4. `EntityIndex` — structure de l'index et polling par source
5. `EntityResolver` — matching fuzzy sur l'index
6. Insertion Couche 2 dans pipeline
7. Événements Radar
8. Commandes de rebuild manuel
