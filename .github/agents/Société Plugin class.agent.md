---
name: Société Plugin class
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert Python/PySide6 engineer working on ada_local.

Context:
- BasePlugin is in core/plugins/base.py
- CompanyModel is in core/plugins/societe/data.py
- Ollama runs Mistral 7B locally
- The skill file format is plain text (see /data/skills/ or project root for examples)

Task: Create `core/plugins/societe/plugin.py`

Implement class `SocietePlugin(BasePlugin)`:

MODULE_ID = "societe"
DISPLAY_NAME = "Sociétés"
COLOR = "#00d4ff"

Implement all BasePlugin abstract methods:

get_nav_items():
    Return one nav group per active company from CompanyModel.get_all_companies().
    Each company produces items:
    [
      {"label": co["name"], "icon": "◈", "tab_id": f"company_{co['id']}", "color": co["color"], "header": True},
      {"label": "Vue société",  "icon": "·", "tab_id": f"company_{co['id']}_overview",  "parent": co["id"]},
      {"label": "Chat dédié",   "icon": "·", "tab_id": f"company_{co['id']}_chat",       "parent": co["id"]},
      {"label": "Devis & Docs", "icon": "·", "tab_id": f"company_{co['id']}_docs",       "parent": co["id"]},
    ]

get_dashboard_widget():
    Return None for now — dashboard integration handled separately in PROMPT 5.

get_chat_context(active_entity: str | None) -> str | None:
    If active_entity is None: return None
    Look up company by id. Build and return a system prompt fragment:
    ---
    ## Contexte société : {name}
    Type : {type}
    Connecteurs actifs : {list connected connectors}
    Compétences disponibles : {skill names}
    Données récentes :
    - Derniers événements : {last 3 events titles}
    - Documents ouverts : {pending/sent documents}
    Réponds en tenant compte de ce contexte. Si une donnée n'est pas disponible via connecteur, indique-le clairement.
    ---

get_skills() -> list[str]:
    Return paths to skill files in core/plugins/societe/skills/:
    - societe_general.txt
    - dolibarr_connector.txt  (if Dolibarr connector connected for any company)
    Only return files that actually exist.

get_quick_prompts() -> list[dict]:
    Return context-aware quick prompts. If no active company:
    [
      {"label": "📋 Devis ouverts", "prompt": "Résumé des devis ouverts pour toutes les sociétés"},
      {"label": "⚠ Alertes", "prompt": "Alertes actives toutes sociétés"},
      {"label": "📊 Rapport", "prompt": "Rapport journalier cross-sociétés"},
    ]
    If active company, prefix prompts with company name.

on_activate() / on_deactivate(): pass (no side effects needed yet)