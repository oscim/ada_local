---
name: Company data model (SQLite)
description: Describe what this custom agent does and when to use it.
argument-hint: The inputs this agent expects, e.g., "a task to implement" or "a question to answer".
# tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo'] # specify the tools this agent can use. If not set, all enabled tools are allowed.
---

<!-- Tip: Use /create-agent in chat to generate content with agent assistance -->

You are an expert Python engineer working on ada_local (PySide6, SQLite via built-in sqlite3).

Context:
- Plugin registry is in place (core/plugins/registry.py)
- HTML reference: `ada-dashboard-societe.html` — see company card structure:
  name, logo initials, color, type/subtitle, connectors list, metrics, timeline events, documents
- Existing DB: chat_history.db (SQLite) with chat history table

Task: Create `core/plugins/societe/data.py`

Implement:

class CompanyModel:
    """SQLite-backed model for the Société module."""

    Tables to create on init (CREATE TABLE IF NOT EXISTS):
    - companies(id TEXT PK, name TEXT, logo TEXT, color TEXT, type TEXT, subtitle TEXT, active INTEGER DEFAULT 1)
    - company_connectors(id TEXT PK, company_id TEXT FK, label TEXT, connector_type TEXT, config_json TEXT, connected INTEGER DEFAULT 0)
    - company_events(id TEXT PK, company_id TEXT FK, title TEXT, description TEXT, tag TEXT, event_type TEXT, timestamp TEXT)
    - company_documents(id TEXT PK, company_id TEXT FK, name TEXT, meta TEXT, status TEXT, source TEXT, amount REAL, created_at TEXT)
    - company_metrics(company_id TEXT FK, key TEXT, value TEXT, sub TEXT, updated_at TEXT, PRIMARY KEY(company_id, key))

    Methods:
    - get_all_companies() -> list[dict]
    - get_company(company_id: str) -> dict | None
    - get_connectors(company_id: str) -> list[dict]
    - get_events(company_id: str, limit: int = 20) -> list[dict]
    - get_documents(company_id: str) -> list[dict]
    - get_metrics(company_id: str) -> list[dict]
    - upsert_company(data: dict) -> None
    - upsert_connector(data: dict) -> None
    - add_event(company_id: str, title: str, description: str, tag: str, event_type: str) -> None
    - upsert_document(data: dict) -> None
    - upsert_metric(company_id: str, key: str, value: str, sub: str) -> None

    Seed default companies on first run (if table empty):
    - OpenTechno (id="opent", color="#00d4ff", type="MSP · Infra & Téléphonie")
    - USCSS (id="uscss", color="#00ff9d", type="Client · Supervision & Projets")
    - Marge Pro (id="margep", color="#ff9500", type="Client · Commercial & Suivi")

Use only stdlib sqlite3. Thread-safe with threading.Lock.
DB path: same folder as chat_history.db (resolve from config.py or __file__).