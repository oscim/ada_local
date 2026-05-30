---
name: Plugin Registery
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

Define what this custom agent does, including its behavior, capabilities, You are an expert Python/PySide6 engineer.

Context:
- Project: ada_local — a local AI assistant (Python, PySide6, QFluentWidgets, Ollama)
- The HTML file `ada-dashboard-societe.html` shows the target UI with a multi-company module
- Current structure: core/, gui/tabs/, gui/components/, config.py, main.py
- config.py has MODULES_ENABLED = {} (to be added)

Task: Create the plugin/module registry system.

Create the following files:

1. `core/plugins/__init__.py` — empty

2. `core/plugins/base.py` — Abstract base class `BasePlugin` with:
   - Abstract properties: MODULE_ID: str, DISPLAY_NAME: str, COLOR: str (hex)
   - Abstract methods:
     - get_nav_items() -> list[dict]  # {"label": str, "icon": str, "tab_id": str}
     - get_dashboard_widget() -> QWidget | None
     - get_chat_context(active_entity: str | None) -> str | None  # system prompt fragment
     - get_skills() -> list[str]  # file paths to skill .txt files
     - get_quick_prompts() -> list[dict]  # {"label": str, "prompt": str}
     - on_activate() -> None
     - on_deactivate() -> None
   - Concrete method: is_enabled() -> bool  (reads config.py MODULES_ENABLED[MODULE_ID])

3. `core/plugins/registry.py` — Singleton `PluginRegistry` with:
   - load_plugins() — scans core/plugins/ subfolders for plugin.py, instantiates if enabled
   - get_active_plugins() -> list[BasePlugin]
   - get_all_nav_items() -> list[dict]  # merged from all active plugins
   - get_combined_chat_context(active_entity: str | None) -> str  # joined fragments
   - get_all_skills() -> list[str]
   - get_all_quick_prompts() -> list[dict]

4. In `config.py` add:
   MODULES_ENABLED = {
       "societe": True,
   }

Use Python 3.11 type hints throughout. No third-party deps beyond what's in requirements.txt.