---
name: Connect abstraction  Dol
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert Python engineer working on ada_local.

Context:
- CompanyModel stores connector config as JSON in company_connectors.config_json
- Target: plug live ERP/CRM data into ADA's chat responses
- Priority connector: Dolibarr (REST API, self-hosted)
- Future connectors: other ERPs, CRMs (same interface)

Task: Create the connector layer.

1. `core/plugins/societe/connectors/__init__.py` — empty

2. `core/plugins/societe/connectors/base_connector.py`:
   Abstract class `BaseConnector`:
   - CONNECTOR_TYPE: str (class var)
   - __init__(self, config: dict)  # config from DB config_json
   - Abstract: test_connection() -> bool
   - Abstract: get_display_name() -> str
   - Abstract: fetch_documents(entity_ref: str | None) -> list[dict]
     # Returns list of {name, meta, status, amount, source, url}
   - Abstract: fetch_events(entity_ref: str | None) -> list[dict]
     # Returns list of {title, description, tag, event_type, timestamp}
   - Abstract: fetch_metrics() -> dict[str, str]
     # Returns {key: value} for dashboard KPIs
   - Concrete: safe_fetch(method, *args) -> any
     # Wraps call in try/except, returns None on error, logs warning

3. `core/plugins/societe/connectors/dolibarr.py`:
   Class `DolibarrConnector(BaseConnector)`:
   CONNECTOR_TYPE = "dolibarr"

   Config keys expected: {"url": str, "api_key": str, "entity_id": str | None}

   Implement using httpx (already in requirements or add it):
   - test_connection(): GET {url}/api/index.php/version with DOLAPIKEY header
   - fetch_documents(): GET /proposals (devis) filtered by socid if entity_id set
     Map Dolibarr proposal fields → standard dict
     status mapping: 0=draft, 1=pending, 2=accepted, 3=refused
   - fetch_events(): GET /agenda filtered by company, return last 10
   - fetch_metrics(): return {"devis_ouverts": count, "montant_en_cours": sum, "factures_impayees": count}

   All HTTP calls: timeout=5s, verify=False (self-hosted), handle ConnectionError gracefully.

4. `core/plugins/societe/connectors/factory.py`:
   Function `get_connector(connector_type: str, config: dict) -> BaseConnector | None`
   Registry: {"dolibarr": DolibarrConnector}
   Returns None if type unknown or config invalid.

Add httpx to requirements.txt if not present.