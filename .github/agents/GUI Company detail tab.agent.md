---
name: GUI Company detail tab
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert PySide6 / QFluentWidgets engineer working on ada_local.

Context:
- HTML reference: `ada-dashboard-societe.html` — company detail view shows:
  header (back button, logo, name, subtitle, connector pills),
  4 KPI cards, timeline + documents side by side
- CompanyModel, BaseConnector, DolibarrConnector are implemented

Task: Create `gui/tabs/company_detail.py`

Class `CompanyDetailTab(QWidget)`:

__init__(self, company_id: str, model: CompanyModel, plugin_registry)
    Loads company data, sets up layout.

Layout: QVBoxLayout with:
1. DetailHeader (QFrame):
   - Back button → emit back_requested signal
   - Logo label (40x40, initials, company color)
   - Name (large, bold) + subtitle
   - Connector pills row: one ConnectorPill per connector
     - Green dot + label if connected
     - Gray "+ Label" if not connected → clicking emits connector_setup_requested(connector_type)

2. KPI grid: 2 rows × 2 cols of KpiCard widgets
   - Each: label, large value (colored), sub-label
   - Colored top accent bar using company color
   - Data from CompanyModel.get_metrics(company_id)
   - If connector live: try to refresh from connector.fetch_metrics() on load

3. Split pane (QSplitter horizontal):
   Left — TimelineWidget:
   - QScrollArea containing TimelineItemWidget list
   - Each item: colored dot, vertical line, title, desc, tag pill, time label
   - Data: CompanyModel.get_events(company_id, limit=15)
   - If connector live: merge connector.fetch_events() with local events, deduplicate by title+timestamp

   Right — DocumentsWidget:
   - Header with "+ Nouveau" button → emit new_document_requested(company_id)
   - List of DocItemWidget: icon, name, meta, status badge, source pill
   - Status colors: accepted=green, sent=blue, pending=orange
   - Double-click → emit document_selected(doc_id)
   - Data: CompanyModel.get_documents(company_id)
   - If connector live: merge with connector.fetch_documents()

Signals:
- back_requested = Signal()
- connector_setup_requested = Signal(str, str)  # company_id, connector_type
- new_document_requested = Signal(str)  # company_id
- document_selected = Signal(str)  # doc_id
- chat_prompt_requested = Signal(str)  # inject prompt into chat

refresh_data(): reload all sections from DB + connectors.