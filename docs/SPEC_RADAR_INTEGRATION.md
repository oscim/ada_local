# ADA — Spécification : Intégration Radar dans le serveur principal et l'interface chat

**Projet :** ADA local  
**Branche cible :** `univers`  
**Périmètre :** `/web/server.py`, Radar collecteur, panel chat SPA  
**Hors périmètre :** refactor du cœur Radar, modification du format d'événement  
**Date :** 2026-06-04

---

## 1. Contexte et problème actuel

Le Radar ADA est aujourd'hui un script Python indépendant, lancé manuellement, qui ouvre son propre serveur HTTP sur un port dédié (ex: 8787). Il expose une page HTML standalone consommant un flux SSE local.

Conséquences :

- Radar doit être démarré séparément d'ADA, manuellement
- Il n'est pas accessible depuis la SPA principale
- Il ne peut pas être intégré dans le panel chat
- Il n'est pas utilisable en production, seulement en dev
- Son port séparé pose des problèmes de CORS et d'authentification

---

## 2. Objectif

Intégrer Radar comme composant natif de la couche web ADA :

- Démarrage automatique en parallèle du serveur principal
- Exposition des données via routes FastAPI dans `/web/server.py`
- Onglet Radar dans le panel chat de la SPA, filtré par conversation courante
- Indicateur de santé visuel par réponse ADA

---

## 3. Intégration au démarrage principal

### 3.1 Principe

Le collecteur Radar doit démarrer en tâche de fond au lancement de `web/server.py`, sans bloquer la boucle principale FastAPI.

### 3.2 Mécanisme recommandé

Utiliser le `lifespan` FastAPI (ou `startup` event) pour démarrer le collecteur Radar comme tâche asyncio :

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrages existants : mémoire, profils, plugins, RAG...
    asyncio.create_task(radar_collector.start())
    yield
    await radar_collector.stop()
```

Le collecteur Radar tourne en arrière-plan sur la même boucle asyncio que FastAPI. Aucun port supplémentaire n'est ouvert.

### 3.3 Ce qui change dans le script Radar actuel

- Supprimer le serveur HTTP standalone du script Radar
- Conserver uniquement le collecteur d'événements et le store en mémoire (ou SQLite)
- Exposer le store via une interface interne appelable par les routes FastAPI

### 3.4 Ce qui ne change pas

- Le format des événements Radar (id, type, level, module, message, metadata, timestamp)
- La logique d'émission depuis le pipeline
- Les événements existants déjà instrumentés

---

## 4. Routes API Radar

Ajouter un router dédié `/web/router_radar.py` inclus dans `server.py`.

### 4.1 Table des routes

| Route | Méthode | Auth | Rôle |
|---|---|---|---|
| `/api/radar/events` | GET | JWT | Liste paginée des événements |
| `/api/radar/events/stream` | GET | JWT | Flux SSE temps réel |
| `/api/radar/events/{event_id}` | GET | JWT | Détail d'un événement |
| `/api/radar/events/conversation/{request_id}` | GET | JWT | Événements d'une conversation |
| `/api/radar/stats` | GET | JWT | Agrégats : compteurs par type, par level, par module |
| `/api/radar/clear` | POST | JWT + admin | Vide le store Radar |

### 4.2 Paramètres de filtrage pour `/api/radar/events`

```
limit       : int (défaut 50, max 500)
offset      : int (défaut 0)
level       : info | warning | error
type        : string (ex: llm.hallucinated_function)
module      : string (ex: router_n8n)
request_id  : string
since       : ISO 8601
```

### 4.3 Format de réponse événement

```json
{
  "id": "evt_0f940ede95f34ce8b51c",
  "timestamp": "2026-06-02T15:59:54.744Z",
  "level": "info",
  "type": "timer.fired",
  "module": "router_n8n",
  "message": "Timer déclenché (délai : 10 min)",
  "metadata": {
    "label": "Timer",
    "delay_minutes": 10,
    "context": null
  },
  "request_id": "req_xxx"
}
```

### 4.4 Format SSE `/api/radar/events/stream`

```
data: {"id": "evt_...", "type": "llm.call.completed", "level": "info", ...}

data: {"id": "evt_...", "type": "llm.hallucinated_function", "level": "warning", ...}
```

Filtre optionnel par `request_id` en query param pour n'émettre que les événements d'une conversation donnée.

---

## 5. Onglet Radar dans le panel chat

### 5.1 Principe

Le panel chat droit de la SPA ajoute un deuxième onglet **Radar** à côté de l'onglet **Chat** existant.

```
┌─────────────────────────────────┐
│  ADA          mistral · local   │
├──────────────┬──────────────────┤
│   💬 Chat    │   ⚡ Radar       │
├──────────────┴──────────────────┤
│                                 │
│  [contenu de l'onglet actif]    │
│                                 │
└─────────────────────────────────┘
```

### 5.2 Comportement de l'onglet Radar

Par défaut, l'onglet Radar affiche les événements de la **conversation courante uniquement**, filtrés par le `request_id` de la dernière réponse ADA.

Un toggle permet de basculer en vue globale (flux complet temps réel).

Les événements sont affichés en liste chronologique inversée (plus récent en haut), avec :

- Timestamp court (HH:MM:SS)
- Level coloré : info (bleu), warning (orange), error (rouge)
- Type de l'événement
- Message court
- Flèche pour expandre les métadonnées

### 5.3 Indicateur de santé par réponse

Chaque réponse ADA dans l'onglet Chat affiche un petit indicateur en bas à droite :

```
● vert    : aucun warning ni erreur dans les événements Radar liés
● orange  : au moins un warning (ex: llm.hallucinated_function)
● rouge   : au moins une erreur ou timeout
```

Cet indicateur est cliquable — il bascule automatiquement sur l'onglet Radar filtré sur la conversation correspondante.

### 5.4 Événements à mettre en évidence

Les événements suivants doivent être visuellement distincts dans la liste Radar :

| Type | Affichage |
|---|---|
| `llm.hallucinated_function` | Badge warning orange — "Fonction inconnue" |
| `llm.call.completed` | Badge info bleu — durée en ms |
| `n8n.call.success` | Badge vert — workflow exécuté |
| `n8n.call.failed` | Badge rouge — échec workflow |
| `timer.fired` | Badge info — label + délai |
| `autoskills.injected` | Badge info discret — nb skills injectés |
| `rag.search.completed` | Badge info discret |

---

## 6. Liaison request_id entre chat et Radar

Pour que le filtrage par conversation fonctionne, chaque appel `/api/chat` doit générer et propager un `request_id` unique.

### 6.1 Génération

```python
request_id = f"req_{uuid4().hex[:16]}"
```

Généré au début du traitement dans le pipeline, transmis à tous les événements Radar émis pendant cette requête.

### 6.2 Transmission au frontend

Le `request_id` doit être inclus dans le flux SSE de réponse chat :

```
data: {"type": "meta", "request_id": "req_abc123"}
```

Émis en premier événement SSE, avant le premier chunk de texte. Le frontend le stocke et l'utilise pour filtrer le Radar.

### 6.3 Cohérence avec la spec `/api/chat`

Ce point est aligné avec la spécification `SPEC_WEB_ROUTES.md` (D-001 à D-006) et le critère A-001 qui demande un `request_id` par conversation.

---

## 7. Store Radar

### 7.1 Option retenue : SQLite

Le store Radar utilise SQLite (cohérent avec AutoSkills et le reste du projet).

Table recommandée :

```sql
CREATE TABLE radar_events (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    type TEXT NOT NULL,
    module TEXT,
    message TEXT,
    metadata_json TEXT,
    request_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_radar_request_id ON radar_events(request_id);
CREATE INDEX idx_radar_type ON radar_events(type);
CREATE INDEX idx_radar_level ON radar_events(level);
CREATE INDEX idx_radar_timestamp ON radar_events(timestamp);
```

### 7.2 Rétention

Les événements sont conservés par défaut 30 jours. Un job de purge tourne au démarrage si le volume dépasse un seuil configurable.

```python
RADAR_RETENTION_DAYS = 30
RADAR_MAX_EVENTS = 50000
```

---

## 8. Sécurité

- Toutes les routes `/api/radar/*` sont protégées par JWT si `auth.enabled=True`
- `/api/radar/clear` requiert un flag admin supplémentaire
- Les métadonnées des événements ne doivent jamais contenir de tokens, secrets ou mots de passe — filtrage à l'émission dans le collecteur
- Le flux SSE Radar n'est pas accessible depuis `/api/webhook/*` (pas de route publique)

---

## 9. Critères d'acceptation

### A-001 — Démarrage automatique
- Radar démarre avec `web/server.py` sans script séparé
- Aucun port supplémentaire n'est ouvert
- Le démarrage Radar n'empêche pas le démarrage FastAPI en cas d'erreur

### A-002 — Routes API
- `/api/radar/events` retourne une liste paginée filtrée
- `/api/radar/events/stream` émet des événements SSE en temps réel
- `/api/radar/events/conversation/{request_id}` retourne uniquement les événements de la conversation

### A-003 — Onglet Radar dans le chat
- L'onglet Radar est visible et accessible dans le panel chat
- Par défaut il affiche les événements de la conversation courante
- Le toggle global/conversation fonctionne
- Les événements warning et error sont visuellement distincts

### A-004 — Indicateur de santé
- Chaque réponse ADA affiche un indicateur coloré
- L'indicateur reflète fidèlement les événements Radar liés
- Le clic sur l'indicateur bascule sur l'onglet Radar filtré

### A-005 — request_id
- Chaque appel `/api/chat` génère un `request_id` unique
- Le `request_id` est émis en premier dans le SSE chat
- Tous les événements Radar liés à cette requête portent ce `request_id`

### A-006 — Rétention
- Les événements plus vieux que 30 jours sont purgés automatiquement
- Le volume maximal est respecté

---

## 10. Fichiers à créer ou modifier

| Fichier | Action |
|---|---|
| `web/router_radar.py` | Créer — routes FastAPI Radar |
| `web/server.py` | Modifier — inclure router_radar, démarrer collecteur en lifespan |
| `web/radar_collector.py` | Modifier — supprimer serveur HTTP standalone, exposer store interne |
| `web/radar_store.py` | Créer (si séparé) — SQLite store + requêtes |
| SPA frontend | Modifier — ajouter onglet Radar, indicateur santé, liaison request_id |

---

## 11. Priorités d'implémentation

1. Intégration du collecteur au lifespan FastAPI — suppression du port dédié
2. Routes `/api/radar/events` et `/api/radar/events/stream`
3. Propagation du `request_id` dans le pipeline et le SSE chat
4. Onglet Radar dans le panel chat
5. Indicateur de santé par réponse
6. Route `/api/radar/events/conversation/{request_id}`
7. Store SQLite et rétention automatique
