---
name: GUI Dashboard company cards widget
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert PySide6 / QFluentWidgets engineer working on ada_local.

Context:
- QFluentWidgets (qfluentwidgets) is installed and used for the main UI
- The HTML file `ada-dashboard-societe.html` shows the exact target:
  company cards grid (2 cols), each with: logo initials, name, type, status badge,
  3 metrics, connector pills at bottom. Clicking a card opens company detail view.
- CompanyModel and SocietePlugin are implemented
- Existing tab pattern: gui/tabs/*.py, each is a QWidget added to the main NavigationPanel

Task: Create `gui/tabs/companies_dashboard.py`

Class `CompaniesDashboardTab(QWidget)`:

Layout: QVBoxLayout
- Section header: "Sociétés actives" label + right-aligned "Vue globale" button
- Companies grid: QGridLayout 2 columns, populated from CompanyModel.get_all_companies()
- Alerts section: "Alertes croisées" label + list of cross-company alert cards

CompanyCard(QFrame) inner widget:
- Left color accent bar (3px, company color, custom paintEvent or stylesheet)
- Header row: logo QLabel (32x32, initials, colored), name + type, status badge
- Metrics row: 3 CompanyMetricWidget (label, value, sub — from CompanyModel.get_metrics)
- Connectors row: ConnectorPill widgets (label + colored dot, from CompanyModel.get_connectors)
- Clicked signal: company_selected = Signal(str)  # emits company_id

Signals on CompaniesDashboardTab:
- company_selected = Signal(str)  # bubble up from cards

Style: match ada-dashboard-societe.html dark theme.
Use QFluentWidgets CardWidget as base for CompanyCard if available, else QFrame.
Use setStyleSheet for colors — CSS variables not available in Qt, use hex from company.color.

Refresh method: refresh_data() — reloads all cards from DB.
Auto-refresh: QTimer every 30 seconds.