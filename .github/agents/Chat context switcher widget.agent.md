---
name: Chat context switcher widget
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert PySide6 engineer working on ada_local.

Context:
- HTML reference: `ada-dashboard-societe.html` — chat panel has:
  a context selector bar (Tout / OpenTechno / USCSS / Marge Pro / Maison buttons)
  + an active context indicator row (colored dot, "Company · Skills chargés", connector status)
- Current chat panel is in gui/tabs/chat.py or gui/handlers.py
- SocietePlugin.get_chat_context(active_entity) builds the system prompt fragment
- LLM calls go through core/llm.py

Task: Create `gui/components/chat_context_bar.py`

Class `ChatContextBar(QWidget)`:

__init__(self, plugin_registry):
    Builds the selector from plugin_registry.get_active_plugins() companies.
    Always includes "Tout" button first.

Layout: QVBoxLayout
- Row 1: "Contexte actif" label + pills row
  Pills: ContextPill(QFrame) — colored dot + label, toggle on click
  "Tout" pill: always visible, selects all/none
  Company pills: one per active company from SocietePlugin

- Row 2: ActiveContextIndicator (QFrame, hidden by default)
  Shows when a specific company is selected:
  - Colored dot (company color)
  - Text: f"{company_name} · Skills chargés"
  - Right side: connector status button
    If connector connected: "Dolibarr 🟢" (green text, subtle border)
    If not: "+ Connecteur" → emit connector_setup_requested

State:
- active_company_id: str | None  (None = "Tout")
- Changing selection: emits context_changed(company_id | None)

Signals:
- context_changed = Signal(object)  # str company_id or None
- connector_setup_requested = Signal(str)  # company_id

Method: get_system_prompt_fragment() -> str | None
    Calls plugin_registry get_combined_chat_context(active_company_id)
    Returns None if "Tout" selected.

Integration point (in gui/handlers.py or core/llm.py):
    Before each Ollama call, prepend get_system_prompt_fragment() to the system prompt.
    If None, use the default ADA system prompt only.
    Comment: # MODULE_SOCIETE: context injection