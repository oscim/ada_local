---
name: Wire everything into main app
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert PySide6 / QFluentWidgets engineer working on ada_local.

Context:
- All plugin/company components are implemented (Prompts 1–7)
- Main window is in gui/app.py, uses QFluentWidgets NavigationInterface or similar
- main.py creates QApplication, splash screen, then MainWindow

Task: Wire the Société module into the existing app.

Modify `gui/app.py`:

1. On __init__, after existing setup:
   from core.plugins.registry import PluginRegistry
   self.plugin_registry = PluginRegistry()
   self.plugin_registry.load_plugins()

2. For each active plugin, call plugin.on_activate()

3. Add navigation items from plugin_registry.get_all_nav_items():
   For each item with header=True: add a NavigationGroup or separator with company name + color dot
   For each sub-item: add NavigationItem linking to the relevant tab

4. Instantiate and add tabs:
   - CompaniesDashboardTab → add to main stacked widget, show when nav "Tableau de bord" clicked
   - For each company: CompanyDetailTab(company_id) → add to stacked widget

5. Connect signals:
   - CompaniesDashboardTab.company_selected → open corresponding CompanyDetailTab
   - CompanyDetailTab.back_requested → return to CompaniesDashboardTab
   - CompanyDetailTab.chat_prompt_requested → inject into chat input
   - CompanyDetailTab.connector_setup_requested → open ConnectorSetupDialog (stub OK)

6. Add ChatContextBar to the chat panel sidebar:
   - Insert above chat input area
   - Connect context_changed → store in self.active_chat_context
   - In the Ollama call handler, prepend plugin_registry.get_combined_chat_context(self.active_chat_context)

7. Reload quick prompts from plugin_registry.get_all_quick_prompts() and display in chat panel.

8. In config.py: if MODULES_ENABLED.get("societe") is False, skip all above silently.
   The app must work identically with the module disabled — zero UI difference.

Keep all existing functionality intact. Add # MODULE_SOCIETE: comments on every new block for easy grep.