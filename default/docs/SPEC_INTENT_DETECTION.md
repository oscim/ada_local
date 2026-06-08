# ADA — Spécification : Détection d'intention dans le pipeline web

**Projet :** ADA local  
**Branche cible :** `univers`  
**Périmètre :** `web/pipeline.py`, couche web uniquement  
**Hors périmètre :** `main.py`, `/gui`, refactor LLM, entraînement de modèle  
**Document :** spécification fonctionnelle — Étape 2  
**Version :** 1.0  
**Date :** 2026-06-05  
**Dépendance amont :** `SPEC_RADAR_INTENT_MINING.md`  
**Dépendance aval :** `SPEC_FEEDBACK_LOOP.md`

---

## 1. Contexte

Le pipeline web actuel résout les intentions de deux manières :

1. Routages déterministes codés en dur (liste de mots-clés ou patterns fixes en position 1-10).
2. Tool-calling LLM via `function_gemma` pour les cas non couverts.

Cette architecture a une limite identifiée : le routage déterministe est générique et ne prend pas en compte les formulations réelles d'Aurélien. Le LLM, lui, prend du temps et consomme des tokens même pour des actions triviales.

Ce document spécifie l'insertion d'une couche de **détection d'intention légère et personnalisée**, alimentée par le corpus `intent_corpus` produit à l'Étape 1, en position 2 dans le pipeline — après la détection d'univers, avant le routage déterministe existant.

---

## 2. Principe général

La détection d'intention est un **matcher rapide** qui :

- compare la requête entrante aux formulations déjà vues et validées dans `intent_corpus` ;
- retourne une action candidate si le score de similarité dépasse un seuil ;
- délègue au pipeline existant si aucune correspondance n'est trouvée.

Elle n'est **pas** un modèle de classification général. Elle est personnalisée, apprise depuis les données réelles d'Aurélien, et améliore avec le temps.

---

## 3. Position dans le pipeline

Le pipeline actuel de `web/pipeline.py` traite les requêtes dans cet ordre :

```
0. Nettoyage du message
1. Émission événement Radar (rag.query.received)
2. [NOUVEAU] Détection d'intention légère ← insertion ici
3. Routage déterministe prioritaire (URL, web, infra, Proxmox, domotique, timer...)
4. Enrichissement du contexte
5. Routage sémantique
6. Tool-calling
7. Dispatch plugin / n8n / executor
8. Streaming réponse
9. Sauvegarde mémoire
10. Mise à jour AutoSkills
```

La détection d'intention en position 2 court-circuite les étapes 3 à 7 si une correspondance certaine est trouvée. En cas de doute, elle passe la main sans modifier le comportement existant.

---

## 4. Algorithme de matching

### 4.1 Approche retenue : similarité cosinus sur TF-IDF

Pas de modèle externe. Pas d'embedding neuronal dans la première version.

L'index est construit sur les `normalized_text` du corpus `intent_corpus`, limité aux enregistrements avec `outcome IN ('success', 'confirmed')`.

TF-IDF est calculé à partir du corpus au chargement, puis mis à jour incrémentalement à chaque nouvel enregistrement validé.

### 4.2 Seuils

| Score | Décision |
|---|---|
| ≥ 0.92 | Correspondance certaine — court-circuit pipeline |
| 0.75 – 0.91 | Correspondance probable — proposée mais non court-circuit |
| < 0.75 | Pas de correspondance — pipeline normal |

Les seuils sont configurables via `config.py`.

### 4.3 Résultat du matching

```python
@dataclass
class IntentMatch:
    matched: bool
    confidence: float          # 0.0 – 1.0
    action: str                # nom de la function FUNCTIONS
    params: dict               # paramètres résolus
    source_request_id: str     # request_id du corpus ayant matché
    source_text: str           # formulation originale du corpus
    is_certain: bool           # True si confidence >= seuil haut
```

---

## 5. Résolution des paramètres

Quand une correspondance est trouvée, les paramètres de l'action candidate sont extraits depuis `detected_params_json` du corpus.

Ces paramètres doivent être **re-contextualisés** sur la requête courante avant exécution.

### 5.1 Règles de re-contextualisation

Le matcher identifie les entités variables dans la formulation originale et tente de les résoudre dans la requête courante.

Exemple :

```
Corpus : "allume la lumière du salon" → action=control_light, room=salon
Requête : "allume la lumière de la cuisine"
```

Le matcher détecte que `salon` ≠ `cuisine` et met à jour `room=cuisine` dans les paramètres avant exécution.

Les entités variables supportées en v1 :

- pièce / zone domotique
- identifiant VM / CT Proxmox
- label de timer
- nom de client RMM

Si la re-contextualisation échoue (entité non résolue), la correspondance est déclassée en `is_certain=False`.

### 5.2 Résolution des entités domotiques

Le matcher interroge le service unifié domotique (déjà disponible dans le pipeline) pour valider que l'entité extraite est connue.

Si l'entité est inconnue du service : `is_certain=False`, fallback pipeline.

---

## 6. Comportement selon le niveau de confiance

### 6.1 Correspondance certaine (`is_certain=True`)

```
1. Émettre événement Radar : intent.matched (level=info)
2. Exécuter l'action directement via le dispatcher existant
3. Streamer la réponse
4. Émettre événement Radar : intent.executed
5. Passer en étape 9 (sauvegarde mémoire)
```

Aucune génération LLM. Aucun tool-calling. Réponse en ~50ms.

### 6.2 Correspondance probable (`is_certain=False`, confidence ≥ 0.75)

```
1. Émettre événement Radar : intent.candidate (level=info)
2. Continuer le pipeline normalement (étapes 3-7)
3. Annoter la réponse finale avec la candidature (pour feedback ultérieur)
```

Le pipeline existant reste maître. La candidature est mémorisée pour l'Étape 4.

### 6.3 Aucune correspondance

Pipeline existant, comportement inchangé. Émettre événement Radar : `intent.no_match` (level=info, discret).

---

## 7. Événements Radar émis

| Type | Level | Condition |
|---|---|---|
| `intent.matched` | info | Correspondance certaine trouvée |
| `intent.executed` | info | Action exécutée depuis le matcher |
| `intent.candidate` | info | Correspondance probable, pipeline continue |
| `intent.no_match` | info | Aucune correspondance |
| `intent.entity_resolution_failed` | warning | Entité non résolue lors de re-contextualisation |
| `intent.index_rebuilt` | info | Index TF-IDF reconstruit |

Format commun :

```json
{
  "type": "intent.matched",
  "level": "info",
  "module": "intent_detector",
  "message": "Intention détectée : control_light (confidence 0.96)",
  "metadata": {
    "action": "control_light",
    "confidence": 0.96,
    "source_request_id": "req_abc123",
    "corpus_size": 1420
  },
  "request_id": "req_xyz789"
}
```

---

## 8. Composant `IntentDetector`

### 8.1 Interface

```python
class IntentDetector:
    def __init__(self, intent_store, function_registry, entity_resolver=None, logger=None):
        pass

    def load_index(self) -> None:
        """Charge et vectorise le corpus depuis intent_store."""
        pass

    def rebuild_index(self) -> None:
        """Reconstruit l'index complet — déclenché après mise à jour du corpus."""
        pass

    def detect(self, normalized_text: str, universe: str | None = None) -> IntentMatch:
        """Retourne la meilleure correspondance ou IntentMatch(matched=False)."""
        pass

    def add_to_index(self, record: dict) -> None:
        """Ajoute un enregistrement validé à l'index sans reconstruction complète."""
        pass
```

### 8.2 Chargement et cycle de vie

- L'index est chargé au démarrage de `web/server.py` en tâche de fond (ne bloque pas FastAPI).
- Si le corpus est vide au démarrage, le détecteur est désactivé silencieusement.
- L'index est reconstruit après chaque validation de feedback (Étape 4) ou après une extraction batch (Étape 1).
- La reconstruction se fait en arrière-plan, l'index précédent reste actif pendant ce temps.

### 8.3 Filtrage par univers

Si `plugin_context` (univers actif) est fourni dans la requête, le matcher filtre le corpus aux enregistrements du même univers avant de calculer la similarité.

Cela réduit le risque de collision inter-univers (ex. "affiche les VMs" ne doit pas matcher "affiche les capteurs").

---

## 9. Intégration dans `web/pipeline.py`

### 9.1 Appel dans le pipeline

```python
async def process_message(message, history, plugin_context, context_id, session_id, request_id):
    # Étape 0 : nettoyage
    message = clean_message(message)

    # Étape 1 : Radar
    await radar.emit("rag.query.received", {"message": message}, request_id=request_id)

    # Étape 2 : Détection d'intention (NOUVEAU)
    if INTENT_DETECTION_ENABLED and intent_detector.is_ready():
        normalized = normalize_text(message)
        match = intent_detector.detect(normalized, universe=plugin_context)

        if match.matched and match.is_certain:
            await radar.emit("intent.matched", {...}, request_id=request_id)
            result = await dispatcher.execute(match.action, match.params)
            await radar.emit("intent.executed", {...}, request_id=request_id)
            yield format_response(result)
            await memory.save(session_id, message, result)
            return  # court-circuit

        elif match.matched:
            await radar.emit("intent.candidate", {...}, request_id=request_id)
            # Mémoriser la candidature pour le feedback
            pipeline_context["intent_candidate"] = match

    # Étapes 3-10 : pipeline existant inchangé
    ...
```

### 9.2 Règle de non-régression

Le détecteur ne doit jamais lever d'exception qui bloquerait le pipeline. Tout échec interne doit être attrapé, loggé en Radar, et le pipeline doit continuer normalement.

```python
try:
    match = intent_detector.detect(normalized, universe=plugin_context)
except Exception as e:
    await radar.emit("intent.error", {"error": str(e)}, level="warning", request_id=request_id)
    match = IntentMatch(matched=False, ...)
```

---

## 10. Configuration

```python
INTENT_DETECTION_ENABLED = True
INTENT_DETECTION_THRESHOLD_CERTAIN = 0.92
INTENT_DETECTION_THRESHOLD_CANDIDATE = 0.75
INTENT_DETECTION_MAX_CORPUS_SIZE = 5000   # enregistrements chargés dans l'index
INTENT_DETECTION_UNIVERSE_FILTER = True   # filtrer par univers actif
INTENT_DETECTION_INDEX_REBUILD_ON_FEEDBACK = True
```

---

## 11. Contraintes de performance

- Le matching doit compléter en moins de **30ms** pour un corpus de 2000 entrées.
- L'index TF-IDF est conservé en mémoire — pas de requête SQLite à chaque appel.
- La reconstruction de l'index (batch) doit se faire en moins de **2 secondes** pour 5000 entrées.
- Le détecteur est singleton, partagé entre les requêtes concurrentes (thread-safe en lecture).

---

## 12. Critères d'acceptation

### A-001 — Intégration pipeline
- Le détecteur est appelé en position 2, après `rag.query.received`.
- Un échec du détecteur ne bloque jamais le pipeline.
- Le court-circuit fonctionne : une action certaine ne déclenche pas le LLM.

### A-002 — Qualité de matching
- Le matching retourne `is_certain=True` uniquement si confidence ≥ seuil configuré.
- Le filtrage par univers est actif si `plugin_context` est fourni.
- La re-contextualisation met à jour les paramètres variables correctement.

### A-003 — Performance
- Détection en moins de 30ms pour un corpus de 2000 entrées.
- L'index se charge en tâche de fond sans bloquer le démarrage.

### A-004 — Observabilité
- Chaque détection (positive ou négative) émet un événement Radar.
- L'indicateur de santé Radar reflète correctement les `intent.entity_resolution_failed`.

### A-005 — Non-régression
- Les routages déterministes existants continuent à fonctionner si le détecteur est désactivé.
- Désactiver `INTENT_DETECTION_ENABLED` remet le pipeline dans l'état exact d'avant.

---

## 13. Fichiers à créer ou modifier

| Fichier | Action |
|---|---|
| `core/intent/intent_detector.py` | Créer — matcher TF-IDF, re-contextualisation |
| `core/intent/entity_resolver.py` | Créer (ou réutiliser si existant) — résolution entités |
| `web/pipeline.py` | Modifier — insertion étape 2 |
| `web/server.py` | Modifier — chargement index au démarrage |
| `config.py` | Modifier — ajouter variables `INTENT_DETECTION_*` |

---

## 14. Priorités d'implémentation

1. `IntentDetector` — vectorisation TF-IDF + matching cosinus
2. Intégration pipeline (court-circuit `is_certain=True`)
3. Filtrage par univers
4. Re-contextualisation des paramètres variables
5. Résolution des entités domotiques
6. Événements Radar pour chaque cas
7. Reconstruction incrémentale de l'index (post-feedback)
