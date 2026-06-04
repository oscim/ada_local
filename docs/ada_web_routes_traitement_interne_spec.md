Tous les projets
ADA


Comment puis-je vous aider ?

    Configuration Continue pour Ada
    Dernier message il y a 5 minutes
    ADA token improvements and use cases
    Dernier message il y a 8 heures
    Webhook et audit réseau
    Dernier message avant-hier
    Optimisation du routage sémantique multi-agents
    Dernier message avant-hier
    Incomplete conversation
    Dernier message avant-hier
    Secure cookie configuration issue
    Dernier message il y a 3 jours
    Tests de validation des comportements du LLM
    Dernier message il y a 3 jours
    Domotique programmable en langage naturel
    Dernier message il y a 3 jours
    401 Unauthorized API authentication error
    Dernier message il y a 3 jours
    Contrôle et spécifications pour agents de codage
    Dernier message il y a 3 jours
    Maintenance
    Dernier message il y a 3 jours
    Modulariser les plugins et intégration profonde
    Dernier message il y a 4 jours
    Hermes agent et ses capacités d'apprentissage autonome
    Dernier message il y a 4 jours
    Restructurer Ada autour de pôles thématiques
    Dernier message il y a 4 jours
    Ajouter des modèles LLM à Ollama
    Dernier message il y a 5 jours
    Architecture modulaire avec notion de société
    Dernier message il y a 6 jours
    Restructuration du skill domotique Ada
    Dernier message il y a 6 jours
    Système d'authentification multi-utilisateur avec QR code
    Dernier message il y a 6 jours
    Plateforme Ada pour supervision multi-entreprises
    Dernier message il y a 6 jours
    Configuration web modulaire pour ADA avec onglets
    Dernier message il y a 6 jours
    Déploiement n8n sur serveur ADA
    Dernier message 18 mai
    Allô voisin pour la communication
    Dernier message 17 mai
    NucBox M7 Ultra mini PC gaming
    Dernier message 16 mai
    Automatisation des communications Marge Pro
    Dernier message 16 mai
    Problème d'affichage de lien dans annonce couvreur
    Dernier message 16 mai
    Externaliser les données du Docker
    Dernier message 15 mai
    Pourquoi choisir ADA plutôt que n8n
    Dernier message 14 mai
    Automatiser la gestion des réseaux sociaux
    Dernier message 14 mai
    Agent autonome avec accès internet et gestion d'erreurs
    Dernier message 14 mai
    Marge+ : gestion financière pour restaurateurs
    Dernier message 14 mai

Instructions

Nosu travaillons la couche web /web pas de main.py ni /gui tu ne code pas tu écrit des spec. note ou fichier en .md https://github.com/oscim/ada_local/blob/univers/config.py https://github.com/oscim/ada_local/blob/univers/
Fichiers
2 % de la capacité du projet utilisée

ada_web_routes_traitement_interne_spec.md
# ADA — État actuel et spécification de cadrage
## Couche `/web` — routes HTTP et traitement interne
 
Date : 2026-06-01  
Branche de référence : `oscim/ada_local@univers`  
Périmètre : **uniquement `/web`**, les routes web, le pipeline web et les specs de comportement.  
Hors périmètre : `main.py`, `/gui`, refactor de code, implémentation.
 
---
 
## 1. Résumé exécutif
 
La couche web ADA est déjà structurée autour d'un serveur FastAPI situé dans `/web/server.py` et d'un pipeline de traitement conversationnel dans `/web/pipeline.py`.
 
Le serveur web assure actuellement :
 
- l'exposition de la PWA / SPA ;
- l'API chat en Server-Sent Events ;
- l'authentification optionnelle par JWT ;
- les routes plugins et univers ;
- les webhooks entrants ;
- les routes infrastructure, documents, société, mémoire, planificateur, domotique, paramètres et Ollama ;
- l'initialisation au démarrage de la mémoire, des profils, des plugins, des skills, du RAG documentaire et du polling infrastructure.
Le traitement interne web repose sur une priorité forte donnée aux routes déterministes avant passage LLM : recherche web Playwright, infra, Proxmox, caméras, domotique, timers, puis seulement ensuite semantic router, tool-calling et génération Ollama.
 
L'état global est donc avancé, mais il reste plusieurs points à spécifier proprement : contrat officiel `/api/chat`, usage réel de `plugin_context` / univers, conflit potentiel sur `/api/plugins/confirm`, sécurité des actions sensibles, isolation mémoire/session et table officielle des routes.
 
---
 
## 2. Sources analysées
 
Fichiers de référence consultés :
 
- `config.py`, branche `univers`
- `web/server.py`, branche `univers`
- `web/pipeline.py`, branche `univers`
- `web/router_plugins.py`, branche `univers`
- `web/router_auth.py`, branche `univers`
- `web/router_societe.py`, branche `univers`
- `web/router_webhook.py`, branche `univers`
---
 
## 3. Architecture web actuelle
 
### 3.1. Rôle de `/web/server.py`
 
`web/server.py` est le point d'exposition HTTP principal de la couche web.
 
Il porte :
 
- l'application FastAPI `ADA Mobile` ;
- le middleware d'authentification ;
- le montage des fichiers statiques ;
- les routes PWA ;
- la route `/api/chat` ;
- les routes dashboard, mémoire, planificateur, briefing, domotique, infrastructure, paramètres et Ollama ;
- l'inclusion de routers spécialisés : auth, profiles, plugins, webhook, infra, documents, société.
### 3.2. Rôle de `/web/pipeline.py`
 
`web/pipeline.py` est le cœur du traitement interne web.
 
Il reçoit un message depuis `/api/chat` ou depuis un webhook texte, puis applique les étapes suivantes :
 
1. nettoyage du message ;
2. émission d'événements Radar ;
3. routage déterministe prioritaire ;
4. enrichissement du contexte ;
5. routage sémantique ;
6. tool-calling si nécessaire ;
7. dispatch plugin / n8n / executor ;
8. streaming de la réponse ;
9. sauvegarde mémoire ;
10. mise à jour éventuelle des AutoSkills.
### 3.3. Rôle de `config.py`
 
`config.py` contient les éléments transverses utilisés par la couche web :
 
- configuration Radar ;
- modèle de réponse ;
- URL Ollama ;
- modèle marketing ;
- chargement dynamique du contexte MargePro depuis `skills/margepro/SKILL.md` ;
- liste `FUNCTIONS` exposée au tool-calling ;
- flags `MODULES_ENABLED`.
---
 
## 4. Routes web actuellement identifiées
 
### 4.1. Routes PWA / statiques
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/` | GET | Sert le shell HTML de la SPA/PWA. |
| `/manifest.json` | GET | Sert le manifest PWA. |
| `/sw.js` | GET | Sert le service worker. |
| `/favicon.ico` | GET | Retourne 204. |
| `/static/*` | GET | Sert les assets statiques avec `Cache-Control: no-cache`. |
 
### 4.2. Routes de santé et dashboard
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/status` | GET | Retourne l'état ADA et l'état Ollama. |
| `/api/dashboard` | GET | Retourne état Ollama, modèle, CPU, RAM, disque, VRAM éventuelle. |
| `/api/dashboard/home` | GET | Retourne météo, tâches, appareils Domoticz récents et dernière news. |
 
### 4.3. Route chat principale
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/chat` | POST | Entrée conversationnelle web principale. Réponse en SSE. |
 
Contrat actuel d'entrée :
 
```text
message: string
history: list[dict]
company_context: string | null
plugin_context: string | null
context_id: string | null
```
 
Contrat actuel de sortie SSE :
 
```text
data: {"text": "..."}
 
data: {"thinking": "..."}
 
data: {"img_url": "..."}
 
data: {"__type": "confirm_required", ...}
 
data: {"error": "..."}
 
data: [DONE]
```
 
Spécification à stabiliser :
 
- `plugin_context` doit être le champ officiel pour l'univers actif côté interface.
- `context_id` doit être le champ officiel pour le sous-contexte : société, client, instance, espace documentaire, etc.
- `company_context` doit rester en compatibilité mais ne plus être le champ principal.
- Toute réponse SSE doit finir par `[DONE]`, y compris en cas d'erreur.
### 4.4. Routes plugins et univers
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/plugins` | GET | Liste des plugins actifs. |
| `/api/plugins/catalog` | GET | Catalogue des modules, actifs ou non, avec état `enabled` et `loaded`. |
| `/api/plugins/universes` | GET | Groupement des plugins par univers. |
| `/api/plugins/kpis/all` | GET | KPIs agrégés de tous les plugins actifs. |
| `/api/plugins/{plugin_id}/kpis` | GET | KPIs d'un plugin. |
| `/api/plugins/quick-prompts/all` | GET | Quick prompts globaux, filtrables par univers. |
| `/api/plugins/{plugin_id}/quick-prompts` | GET | Quick prompts d'un plugin, filtrables par contexte. |
| `/api/plugins/context/system-prompt` | GET | Prompt système combiné des plugins actifs. |
| `/api/plugins/{plugin_id}/action` | POST | Exécute une action sur un plugin spécifique. |
| `/api/plugins/dispatch` | POST | Dispatch global action → plugin → n8n → fallback. |
| `/api/plugins/confirm` | POST | Exécution après confirmation. |
 
Point de vigilance : `/api/plugins/confirm` est défini à la fois dans `server.py` et dans `router_plugins.py`. Il faut choisir une source de vérité unique.
 
### 4.5. Routes webhooks
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/webhook/config` | GET | Retourne le token webhook et les formats attendus. |
| `/api/webhook/config/rotate` | POST | Régénère le token webhook. |
| `/api/webhook/{source}` | POST | Entrée universelle pour Domoticz, n8n, Home Assistant, Alexa, etc. |
 
Modes de payload supportés :
 
- intention texte : `text`, `message`, `query`, `queryText` ;
- action directe : `action` + `params` ;
- événement pur : `event` sans texte.
### 4.6. Routes société
 
Le router société est conditionné par `MODULES_ENABLED["societe"]`.
 
Routes principales identifiées :
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/societe/companies` | GET | Liste les sociétés. |
| `/api/societe/companies/{company_id}` | GET | Détail société. |
| `/api/societe/companies` | POST | Crée une société. |
| `/api/societe/companies/{company_id}` | PUT | Met à jour une société. |
 
Le router contient aussi des modèles pour métriques, timeline, documents et connecteur Dolibarr. Les routes détaillées doivent être inventoriées dans une spec dédiée `SPEC_SOCIIETE_WEB.md`.
 
### 4.7. Routes planificateur
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/tasks` | GET | Liste les tâches. |
| `/api/tasks` | POST | Ajoute une tâche. |
| `/api/tasks/{task_id}` | PATCH | Change l'état d'une tâche. |
| `/api/tasks/{task_id}` | DELETE | Supprime une tâche. |
| `/api/planner/alarms` | GET | Liste les alarmes. |
| `/api/planner/alarms` | POST | Ajoute une alarme. |
| `/api/planner/alarms/{alarm_id}` | DELETE | Supprime une alarme. |
| `/api/planner/timers` | GET | Liste les timers actifs. |
| `/api/planner/timers` | POST | Ajoute un timer. |
| `/api/planner/timers/{label}` | DELETE | Supprime un timer. |
 
### 4.8. Routes mémoire
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/memory/stats` | GET | Statistiques mémoire. |
| `/api/memory/recent` | GET | Souvenirs récents. |
| `/api/memory/consolidated` | GET | Mémoire consolidée. |
| `/api/memory/search` | POST | Recherche mémoire. |
| `/api/memory/{memory_id}` | DELETE | Suppression mémoire. |
| `/api/memory/consolidate` | POST | Lance une consolidation mémoire. |
 
Point de vigilance : le pipeline utilise actuellement un `session_id` fixe `web_chat`. Pour un mode multi-utilisateur ou multi-session, il faut spécifier un identifiant de session web réel.
 
### 4.9. Routes briefing
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/briefing/feed` | GET | Flux RSS filtré et mis en cache. |
| `/api/briefing/config` | GET | Configuration sources + mots-clés. |
| `/api/briefing/config` | POST | Mise à jour sources + mots-clés. |
 
### 4.10. Routes domotique / pages
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/page/home` | GET | Entités domotiques unifiées et providers. |
| `/api/page/infrastructure` | GET | Résumé infrastructure. |
| `/api/entity/{entity_id}/toggle` | POST | Contrôle direct d'une entité. |
| `/api/scene/{scene_name}` | POST | Activation d'une scène. |
 
### 4.11. Routes paramètres et Ollama
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/settings` | GET | Retourne tous les paramètres courants. |
| `/api/settings` | POST | Met à jour un paramètre. |
| `/api/ollama/models` | GET | Liste les modèles Ollama installés. |
| `/api/ollama/pull` | POST | Pull d'un modèle avec progression SSE. |
| `/api/ollama/models/{model_name}` | DELETE | Supprime un modèle Ollama. |
 
### 4.12. Routes infrastructure personnalisée
 
| Route | Méthode | Rôle |
|---|---:|---|
| `/api/infra/endpoints` | GET | Liste des endpoints personnalisés. |
| `/api/infra/endpoints` | POST | Ajoute un endpoint. |
| `/api/infra/endpoints/{name}/tags` | PATCH | Met à jour les tags. |
| `/api/infra/endpoints/{name}` | DELETE | Supprime un endpoint. |
| `/api/infra/services` | GET | Liste les services built-in. |
| `/api/infra/services/{name}/hidden` | PATCH | Masque ou affiche un service. |
| `/api/infra/services/{name}/tags` | PATCH | Met à jour les tags d'un service. |
| `/api/infra/services/{name}/universe` | PATCH | Associe un service à un univers. |
| `/api/infra/endpoints/{name}/universe` | PATCH | Associe un endpoint à un univers. |
 
---
 
## 5. Pipeline interne actuel
 
### 5.1. Entrée
 
Le pipeline public est `process_message(message, history, company_context, plugin_context, context_id)`.
 
Le message est nettoyé puis traité dans l'ordre suivant.
 
### 5.2. Routages déterministes prioritaires
 
Le pipeline donne la priorité aux cas suivants avant toute génération LLM :
 
1. ajout d'une URL à la surveillance infrastructure ;
2. recherche web explicite via agent Playwright ;
3. demande d'état infrastructure ;
4. liste VM/CT Proxmox ;
5. backup Proxmox avec confirmation ;
6. start/stop/reboot VM/CT avec confirmation ;
7. analyse ou affichage caméra ;
8. état des entités domotiques ;
9. contrôle direct domotique ;
10. création de timer.
Ce choix est cohérent : les actions métier et domotiques doivent être déterministes dès que possible, et le LLM doit surtout servir à comprendre les cas ambigus ou à formuler une réponse.
 
### 5.3. Recherche web interne
 
La recherche web n'utilise pas seulement un tool `web_search`. Les phrases déclenchant une recherche web explicite appellent directement un agent Playwright headless.
 
Le flux prévu :
 
1. détection d'un trigger web ;
2. message initial `Recherche sur le web en cours` ;
3. exécution de l'agent navigateur ;
4. navigation / extraction / synthèse ;
5. sauvegarde mémoire ;
6. retour streaming au client.
Spécification à clarifier :
 
- le tool `web_search` existe encore dans `FUNCTIONS` ;
- le pipeline contient aussi une voie directe Playwright ;
- il faut définir quelle voie est officielle pour la couche web.
Proposition de spec :
 
- `web_search` = recherche simple, compatible dispatcher/tools ;
- `web_agent_search` = recherche approfondie nécessitant navigation, sources multiples ou extraction de page ;
- le frontend doit afficher un état de progression identique pour les deux.
### 5.4. Contexte conversationnel
 
Si aucun routage déterministe ne termine la réponse, le pipeline construit un contexte :
 
1. system prompt ADA ;
2. historique limité aux 20 derniers messages ;
3. contexte domotique si la question concerne les entités ;
4. skills via `skill_manager`; 
5. AutoSkills SQLite ;
6. RAG documentaire ;
7. mémoire long terme ;
8. message utilisateur courant.
### 5.5. Routage sémantique
 
Le pipeline appelle ensuite `semantic_route(user_text)`.
 
Comportements attendus :
 
- `function_gemma` : passage par tool-calling complet ;
- `qwen_thinking` : génération directe avec pensée ;
- autre route : génération directe standard.
### 5.6. Tool-calling web
 
En route `function_gemma`, le pipeline :
 
1. combine `config.FUNCTIONS` et les functions des plugins actifs ;
2. construit un prompt de dispatch ;
3. demande au modèle de sélectionner un outil ;
4. récupère `tool_calls` ;
5. applique deux fallbacks si le modèle répond en texte brut ;
6. exécute `passthrough` si demandé ;
7. détecte les actions à confirmation ;
8. dispatch l'action vers plugin registry puis n8n ;
9. retourne le message plugin formaté sans hallucination LLM si l'action réussit ;
10. en cas d'échec, demande au LLM de reformuler uniquement l'erreur.
---
 
## 6. Univers et contextes
 
### 6.1. État actuel
 
Le serveur accepte déjà :
 
- `plugin_context` : univers actif ;
- `context_id` : sous-contexte ;
- `company_context` : compatibilité historique.
Les plugins exposent aussi leur `universe`, et `/api/plugins/universes` retourne les plugins regroupés par univers.
 
Les modules activables sont déclarés dans `MODULES_ENABLED`, avec notamment :
 
- `societe` ;
- `domotique` → univers `home` ;
- `proxmox` → univers `opent` ;
- `rmm` → univers `opent` ;
- `telephony` ;
- `margepro` → univers `margep` ;
- `music`.
### 6.2. Point important à corriger dans la spec
 
Aujourd'hui, le pipeline calcule un contexte effectif ainsi :
 
```text
context effectif = context_id OU company_context OU None
```
 
`plugin_context` est bien reçu, mais il n'est pas le premier champ utilisé pour le prompt système et le tool-calling. Il sert davantage de fallback de domaine pour AutoSkills.
 
Spécification proposée :
 
```text
universe = plugin_context
context_id = context_id
legacy_company_context = company_context
```
 
Règle :
 
- `plugin_context` filtre les capacités visibles, les quick prompts et les plugins actifs dans le chat ;
- `context_id` filtre les données métier internes à un univers ;
- `company_context` ne doit plus être utilisé que comme alias legacy de `context_id` pour la société/infra.
---
 
## 7. Confirmation des actions sensibles
 
### 7.1. État actuel
 
Les confirmations existent à deux niveaux :
 
- dans le pipeline, pour les fonctions dont la définition contient `x_confirm_required` ;
- en déterministe pour backup Proxmox et power VM/CT ;
- via `/api/plugins/confirm` après clic utilisateur.
### 7.2. Problème à arbitrer
 
`/api/plugins/confirm` existe dans deux endroits :
 
- une version dans `server.py`, limitée explicitement à certaines actions Proxmox ;
- une version dans `router_plugins.py`, générique plugin registry puis n8n.
Spec à décider :
 
- soit route unique générique dans `router_plugins.py`, avec contrôle d'autorisation centralisé ;
- soit route spécialisée Proxmox dans `server.py`, mais alors renommer en `/api/proxmox/confirm`.
Recommandation : garder `/api/plugins/confirm` dans `router_plugins.py` comme source de vérité unique, et porter les règles d'autorisation dans le registre plugin ou dans une policy `ActionPolicy`.
 
---
 
## 8. Sécurité et auth
 
### 8.1. Auth web
 
Le middleware JWT est actif seulement si `auth.enabled=True`.
 
Routes publiques :
 
- `/` ;
- `/manifest.json` ;
- `/sw.js` ;
- `/api/status` ;
- `/static/*` ;
- `/api/auth/*` ;
- `/api/webhook/*`.
Les webhooks restent publics vis-à-vis du JWT mais protégés par un token dédié.
 
### 8.2. Points de vigilance
 
- `shell_exec` est défini dans `FUNCTIONS` comme exécution système large. Cette fonction doit être considérée critique.
- Les actions Proxmox power/backup/restore doivent toujours exiger confirmation.
- Les webhooks action directe doivent être limités par token, source et idéalement allowlist d'actions.
- Le dashboard et les paramètres ne doivent pas être accessibles sans auth en environnement exposé.
Spec minimale :
 
- toute action destructive ou système doit déclarer `x_confirm_required=True` ;
- toute action shell doit être désactivée par défaut ou réservée admin ;
- toute action webhook doit être journalisée Radar ;
- aucune erreur ne doit exposer token, secret, cookie ou API key.
---
 
## 9. Observabilité Radar
 
La couche web contient déjà une console d'événements Radar configurée dans `config.py`.
 
Le pipeline émet au minimum :
 
- réception de requête RAG/chat ;
- fin de recherche documentaire ;
- début d'appel LLM ;
- fin d'appel LLM ;
- réponse envoyée.
Spec recommandée :
 
- ajouter un `request_id` unique à chaque `/api/chat` ;
- transmettre ce `request_id` dans les événements SSE de debug si mode développeur ;
- journaliser les confirmations : créée, confirmée, annulée, expirée ;
- journaliser les actions plugin : demandée, validée, exécutée, échouée.
---
 
## 10. Écarts / décisions ouvertes
 
### D-001 — Contrat officiel de contexte chat
 
Décision à prendre : remplacer progressivement `company_context` par :
 
```text
plugin_context = univers actif
context_id = sous-contexte actif
```
 
### D-002 — Source de vérité confirmation
 
Décision à prendre : supprimer le doublon `/api/plugins/confirm` ou le renommer.
 
### D-003 — Recherche web simple vs agent web
 
Décision à prendre : préciser quand utiliser `web_search` et quand utiliser l'agent Playwright.
 
### D-004 — Isolation mémoire web
 
Décision à prendre : remplacer `session_id = "web_chat"` par un identifiant réel :
 
```text
session_id = user_id + browser_session_id + conversation_id
```
 
### D-005 — Actions shell
 
Décision à prendre : `shell_exec` doit-il être visible dans la couche web ? Si oui, sous quelles permissions ?
 
### D-006 — Activation des modules
 
Décision à prendre : harmoniser `MODULES_ENABLED` et `settings.modules.<key>`.
 
Le catalogue utilise les settings en priorité, mais l'enregistrement au startup dépend probablement du mécanisme de registre. Il faut documenter la source de vérité finale.
 
---
 
## 11. Spécification cible courte
 
### 11.1. `/api/chat`
 
Entrée cible :
 
```json
{
  "message": "texte utilisateur",
  "history": [],
  "plugin_context": "home|opent|margep|...",
  "context_id": "optionnel",
  "session_id": "optionnel"
}
```
 
Sortie cible SSE :
 
```text
data: {"type":"thinking", "text":"..."}
 
data: {"type":"text", "text":"..."}
 
data: {"type":"image", "url":"..."}
 
data: {"type":"confirm_required", "func":"...", "message":"...", "params":{}, "cmd":"..."}
 
data: {"type":"error", "message":"..."}
 
data: [DONE]
```
 
Compatibilité actuelle à maintenir temporairement :
 
- `text` au lieu de `type=text` ;
- `thinking` au lieu de `type=thinking` ;
- `img_url` au lieu de `type=image` ;
- carte brute `__type=confirm_required`.
### 11.2. `/api/plugins/universes`
 
Doit retourner les univers actifs et leurs plugins chargés.
 
Contrat cible :
 
```json
{
  "home": [
    {"id":"domotique", "label":"Domotique", "icon":"🏠", "color":"#..."}
  ],
  "opent": [
    {"id":"proxmox", "label":"Infrastructure", "icon":"🖥️", "color":"#..."}
  ]
}
```
 
### 11.3. `/api/plugins/quick-prompts/all?universe=...`
 
Doit retourner uniquement les quick prompts de l'univers actif.
 
### 11.4. Confirmation
 
Contrat cible :
 
```json
{
  "func": "vm_backup",
  "params": {"vmid": 101, "storage": "local"},
  "request_id": "req_xxx"
}
```
 
Réponse :
 
```json
{
  "success": true,
  "message": "...",
  "data": {}
}
```
 
---
 
## 12. Critères d'acceptation
 
### A-001 — Chat SSE
 
- `/api/chat` retourne toujours `text/event-stream`.
- Chaque réponse finit par `[DONE]`.
- Les erreurs sont envoyées en événement SSE, pas en crash silencieux.
### A-002 — Univers actif
 
- Le frontend transmet toujours `plugin_context`.
- Le pipeline utilise `plugin_context` pour filtrer/injecter les capacités plugin.
- Les quick prompts changent selon l'univers actif.
### A-003 — Sous-contexte
 
- `context_id` filtre les données société, infra, documentaire ou autre sous-domaine.
- `company_context` reste compatible mais est documenté comme legacy.
### A-004 — Confirmation
 
- Toute action avec `x_confirm_required` retourne une carte de confirmation.
- La confirmation passe par une route unique.
- L'action n'est jamais exécutée avant clic utilisateur.
### A-005 — Webhooks
 
- Un webhook sans token valide retourne 401.
- Un webhook `text/message/query` passe dans le pipeline.
- Un webhook `action` est journalisé et limité selon policy.
- Un webhook `event` alimente Radar sans déclencher de réponse LLM inutile.
### A-006 — Mémoire
 
- Chaque conversation web dispose d'un `session_id` isolé.
- La mémoire long terme ne devient jamais une instruction système prioritaire.
- La consolidation mémoire reste déclenchable depuis l'API.
### A-007 — Sécurité actions critiques
 
- `shell_exec` désactivé par défaut ou admin-only.
- Proxmox power/restore/reboot/backup demandent confirmation.
- Les tokens et secrets sont masqués dans les logs et Radar.
---
 
## 13. Fichiers Markdown recommandés à créer dans le dépôt
 
1. `docs/web/SPEC_WEB_ROUTES.md`  
   Table officielle des routes HTTP, payloads, réponses, auth.
2. `docs/web/SPEC_WEB_PIPELINE.md`  
   Ordre de traitement interne, routage déterministe, LLM, tools, mémoire.
3. `docs/web/SPEC_WEB_UNIVERSES.md`  
   Contrat `plugin_context`, `context_id`, quick prompts, plugins actifs.
4. `docs/web/SPEC_WEB_CONFIRMATIONS.md`  
   Actions sensibles, carte de confirmation, route unique, expiration.
5. `docs/web/SPEC_WEB_SECURITY.md`  
   Auth, webhook, shell, permissions, logs sensibles.
---
 
## 14. Priorités de documentation
 
Priorité 1 : formaliser `/api/chat` et le format SSE.  
Priorité 2 : formaliser `plugin_context` et `context_id`.  
Priorité 3 : arbitrer `/api/plugins/confirm`.  
Priorité 4 : écrire la matrice officielle des routes `/web`.  
Priorité 5 : écrire la spec sécurité des actions sensibles.  
Priorité 6 : documenter les routes société, infra et documents dans des specs dédiées.
 
