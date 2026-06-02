"""
N8NExecutor — HTTP client for n8n webhooks with FunctionExecutor fallback.

Call n8n_executor.call(action, params) → {success, message, data}.
Never raises. Falls back to FunctionExecutor if n8n is unavailable.

Découverte dynamique : interroge l'API n8n au démarrage pour lister les workflows
actifs tagués 'ada' ou dont le nom commence par 'ADA'. TTL = 5 min.
"""

import logging
import re
import threading
import time
from typing import Any

import requests

from core.settings_store import settings as app_settings


def _slugify(text: str) -> str:
    """'ADA - Speed Test' → 'ada-speed-test'"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

logger = logging.getLogger(__name__)

# Mapping: webhook action name (hyphens) → FunctionExecutor func_name (underscores)
_WEBHOOK_TO_FUNC: dict[str, str] = {
    "control-light":   "control_light",
    "set-timer":       "set_timer",
    "set-alarm":       "set_alarm",
    "web-search":      "web_search",
    "shell-exec":      "shell_exec",
    "get-info":        "get_system_info",
    "calendar-event":  "create_calendar_event",
    "weather":         "weather",
}


class N8NExecutor:
    """
    HTTP client for n8n webhooks with transparent FunctionExecutor fallback.

    - POST /webhook/<action> with {"params": params}
    - Expects response: {"success": bool, "message": str, "data": Any}
    - On ConnectionError or Timeout: activates cooldown_s-second cooldown,
      falls back to FunctionExecutor for that call and the cooldown window.
    - Never raises.
    """

    def __init__(self) -> None:
        self._down_since: float = 0.0  # monotonic timestamp of last failure; 0 = healthy
        self._lock = threading.Lock()
        self._plugin_webhooks: dict[str, str] = {}  # action → URL, enregistrés par les plugins

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    # Patterns d'actions connues comme lentes (speed test, benchmark, GC, verify...)
    _LONG_RUNNING_PATTERNS = (
        "speedtest", "speed_test", "speed-test",
        "benchmark", "verify", "gc", "garbage",
        "backup", "scan", "index",
    )

    def _load_settings(self) -> tuple[str, float, bool, float]:
        """Return (webhook_base_url, timeout_s, fallback_enabled, cooldown_s)."""
        cfg = app_settings.get("n8n") or {}
        base_url   = cfg.get("url", "http://localhost:5678").rstrip("/") + "/webhook"
        timeout_s  = float(cfg.get("timeout_s", 30.0))
        fallback   = bool(cfg.get("fallback_enabled", True))
        cooldown_s = float(cfg.get("cooldown_s", 30.0))
        return base_url, timeout_s, fallback, cooldown_s

    def _effective_timeout(self, action: str, base_timeout: float) -> float:
        """Retourne un timeout plus long pour les workflows connus comme lents."""
        cfg = app_settings.get("n8n") or {}
        long_t = float(cfg.get("long_running_timeout_s", 120.0))
        action_low = action.lower()
        if any(p in action_low for p in self._LONG_RUNNING_PATTERNS):
            return long_t
        return base_timeout

    # ------------------------------------------------------------------
    # Cooldown helpers
    # ------------------------------------------------------------------

    def _is_in_cooldown(self, cooldown_s: float) -> bool:
        if self._down_since == 0.0:
            return False
        return (time.monotonic() - self._down_since) < cooldown_s

    def _mark_down(self) -> None:
        """Must be called under self._lock."""
        self._down_since = time.monotonic()

    def _mark_up(self) -> None:
        """Must be called under self._lock."""
        self._down_since = 0.0

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _fallback(self, action: str, params: dict) -> dict:
        """Delegate to FunctionExecutor using the equivalent underscore func_name."""
        func_name = _WEBHOOK_TO_FUNC.get(action, action.replace("-", "_"))
        try:
            from core.function_executor import executor as function_executor
            return function_executor.execute(func_name, params)
        except Exception as exc:
            logger.error("[N8N] FunctionExecutor fallback failed: %s", exc)
            return {"success": False, "message": str(exc), "data": None}

    # ------------------------------------------------------------------
    # Plugin webhook registration
    # ------------------------------------------------------------------

    def register_plugin_webhooks(self, webhooks: dict[str, str]) -> None:
        """
        Enregistre dynamiquement les webhooks des plugins actifs.
        Ces entrées sont consultées en priorité dans call() avant _WEBHOOK_TO_FUNC.
        Appelé au démarrage après register_enabled_plugins().
        """
        self._plugin_webhooks.update(webhooks)
        logger.info("[N8N] %d webhooks plugins enregistrés", len(webhooks))

    # ------------------------------------------------------------------
    # Découverte dynamique des workflows n8n via API REST
    # ------------------------------------------------------------------

    _discovery_cache: list[dict] = []   # cache partagé (module-level via instance)
    _discovery_ts: float = 0.0
    _DISCOVERY_TTL: float = 300.0       # 5 minutes

    def _discover_workflows(self) -> list[dict]:
        """
        Interroge l'API n8n pour lister les workflows actifs dont :
          - le nom commence par 'ADA' (insensible à la casse), OU
          - l'un des tags vaut 'ada'.
        Retourne une liste de dicts {func_name, webhook_path, description, workflow_name}.
        Cache TTL = 5 min. Silencieux en cas d'échec.
        """
        now = time.monotonic()
        if now - self._discovery_ts < self._DISCOVERY_TTL and self._discovery_cache:
            return self._discovery_cache

        cfg = app_settings.get("n8n") or {}
        api_key = cfg.get("api_key", "")
        base = cfg.get("url", "http://localhost:5678").rstrip("/")

        if not api_key:
            logger.debug("[N8N] Pas d'api_key configurée — découverte workflows désactivée")
            return []

        try:
            resp = requests.get(
                f"{base}/api/v1/workflows",
                headers={"X-N8N-API-KEY": api_key, "Accept": "application/json"},
                timeout=5.0,
                verify=False,
            )
            resp.raise_for_status()
            workflows = resp.json().get("data", [])
        except Exception as exc:
            logger.warning("[N8N] Découverte workflows API échouée: %s", exc)
            return self._discovery_cache  # garder le cache périmé si disponible

        results = []
        for wf in workflows:
            if not wf.get("active"):
                continue
            wf_name = wf.get("name", "")
            tags = [t.get("name", "").lower() for t in (wf.get("tags") or [])]

            # Filtre : nom commence par "ADA" ou tag "ada"
            if not (wf_name.upper().startswith("ADA") or "ada" in tags):
                continue

            # Chercher le nœud webhook pour extraire le path
            nodes = wf.get("nodes") or []
            webhook_node = next(
                (
                    n for n in nodes
                    if n.get("type") in (
                        "n8n-nodes-base.webhook",
                        "@n8n/n8n-nodes-langchain.toolWebhook",
                    )
                ),
                None,
            )
            if webhook_node:
                webhook_path = webhook_node.get("parameters", {}).get("path", "").strip("/")
            else:
                webhook_path = ""

            # Convention fallback : slug du nom ("ADA - Speed Test" → "ada-speed-test")
            if not webhook_path:
                webhook_path = _slugify(wf_name)

            # Nom de fonction LLM : slug sans tirets ("ada-speed-test" → "ada_speed_test")
            func_name = webhook_path.replace("-", "_")

            # Description : notes du workflow ou description utile
            raw_notes = (wf.get("meta") or {}).get("templateNotes", "").strip()
            if raw_notes:
                description = raw_notes
            else:
                # Retirer le préfixe "ADA" du nom pour la description
                short_name = re.sub(r"^ada[\s\-:—]+", "", wf_name, flags=re.IGNORECASE).strip()
                description = (
                    f"Lance le workflow n8n '{wf_name}'. "
                    f"Utilise cette fonction quand l'utilisateur demande : {short_name.lower()}. "
                    f"Appelle '{func_name}' sans paramètres."
                )

            results.append({
                "func_name":      func_name,
                "webhook_path":   webhook_path,
                "description":    description,
                "workflow_name":  wf_name,
            })
            logger.debug("[N8N] Workflow découvert: %s → func=%s webhook=%s",
                         wf_name, func_name, webhook_path)

        self._discovery_cache = results
        self._discovery_ts    = now
        if results:
            logger.info("[N8N] %d workflow(s) ADA découvert(s): %s",
                        len(results), [r["func_name"] for r in results])
        return results

    def get_function_definitions(self) -> list[dict]:
        """
        Retourne les définitions de fonctions LLM pour tous les workflows ADA
        découverts dynamiquement depuis l'API n8n.
        Enregistre aussi leurs webhooks dans _plugin_webhooks.
        """
        base_url, _, _, _ = self._load_settings()
        defs = []
        for wf in self._discover_workflows():
            func_name    = wf["func_name"]
            webhook_path = wf["webhook_path"]
            description  = wf["description"]

            # Enregistrer le webhook pour dispatch direct
            action_key = func_name.replace("_", "-")
            self._plugin_webhooks[action_key] = f"{base_url}/{webhook_path}"
            self._plugin_webhooks[func_name]  = f"{base_url}/{webhook_path}"

            defs.append({
                "type": "function",
                "function": {
                    "name":        func_name,
                    "description": description,
                    "parameters":  {"type": "object", "properties": {}},
                },
            })
        return defs

    def invalidate_discovery_cache(self) -> None:
        """Force la redécouverte des workflows au prochain appel."""
        self._discovery_ts = 0.0

    # ------------------------------------------------------------------
    # Response normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(data: Any) -> dict:
        """Ensure response has the canonical {success, message, data} shape."""
        if data is None:
            return {"success": False, "message": "Empty response from n8n", "data": None}
        if isinstance(data, dict) and "success" in data:
            return {
                "success": bool(data["success"]),
                "message": str(data.get("message", data.get("error", str(data)))),
                "data":    data.get("data"),
            }
        # Non-standard response — wrap it
        return {
            "success": True,
            "message": str(data),
            "data":    data,
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def call(self, action: str, params: dict) -> dict:
        """
        POST /webhook/<action> with {"params": params}.
        Priorité : _plugin_webhooks > URL n8n configurée > FunctionExecutor fallback.
        Returns {success, message, data}. Never raises.
        """
        base_url, timeout_s, fallback_enabled, cooldown_s = self._load_settings()

        # Résoudre l'URL effective : plugin webhook en priorité, sinon URL n8n base
        plugin_url = self._plugin_webhooks.get(action)
        if plugin_url:
            effective_url = plugin_url
        else:
            effective_url = f"{base_url}/{action}"

        # Check cooldown under lock
        with self._lock:
            in_cooldown = self._is_in_cooldown(cooldown_s)

        if in_cooldown:
            logger.debug("[N8N] Cooldown actif, skip HTTP (action=%s)", action)
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False,
                    "message": "n8n indisponible (cooldown actif)",
                    "data": None}

        # Attempt HTTP call (outside lock — slow operation)
        effective_timeout = self._effective_timeout(action, timeout_s)
        logger.info("[N8N] → POST %s params=%s (timeout=%.0fs)", effective_url, params, effective_timeout)
        _t0 = time.monotonic()
        try:
            resp = requests.post(
                effective_url,
                json={"params": params},
                timeout=effective_timeout,
            )
            resp.raise_for_status()
            with self._lock:
                self._mark_up()
            # Gérer les réponses sans corps (200 vide — n8n sans nœud Respond)
            raw_body = resp.text.strip()
            if not raw_body:
                result = {"success": True, "message": "Workflow exécuté avec succès.", "data": None}
            else:
                try:
                    result = self._normalize(resp.json())
                except Exception:
                    result = {"success": True, "message": raw_body[:500], "data": None}
            _dur = int((time.monotonic() - _t0) * 1000)
            logger.info("[N8N] ← %s success=%s message=%s", action, result.get("success"), result.get("message", "")[:80])
            try:
                from web.radar.events import emit_event as _re
                _re(type="n8n.call.success", level="info", module="n8n_executor",
                    message=f"n8n ← {action} success={result.get('success')}",
                    duration_ms=_dur,
                    metadata={"action": action, "url": effective_url, "success": result.get("success")})
            except Exception:
                pass
            return result

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            _dur = int((time.monotonic() - _t0) * 1000)
            is_timeout = isinstance(exc, requests.exceptions.Timeout)
            # Ne marquer n8n "down" que sur ConnectionError, pas sur Timeout
            # (un timeout = workflow lent, n8n EST joignable)
            if not is_timeout:
                with self._lock:
                    self._mark_down()
            _reason = "timeout workflow" if is_timeout else "connexion impossible"
            logger.warning("[N8N] %s (action=%s, %.0fms)", _reason, action, _dur)
            try:
                from web.radar.events import emit_event as _re
                _re(type="n8n.unreachable", level="warning", module="n8n_executor",
                    message=f"n8n injoignable — action={action} ({type(exc).__name__})",
                    duration_ms=_dur,
                    metadata={"action": action, "url": effective_url, "error": str(exc)[:200]})
            except Exception:
                pass
            if fallback_enabled:
                return self._fallback(action, params)
            return {"success": False, "message": "n8n indisponible", "data": None}

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            _dur = int((time.monotonic() - _t0) * 1000)
            logger.error("[N8N] HTTP %d pour action=%s", status, action)
            try:
                from web.radar.events import emit_event as _re
                _level = "error" if status >= 500 else "warning"
                _re(type="n8n.http_error", level=_level, module="n8n_executor",
                    message=f"n8n HTTP {status} — action={action}",
                    duration_ms=_dur,
                    metadata={"action": action, "url": effective_url, "status": status})
            except Exception:
                pass
            # Only 5xx server errors indicate n8n is down — 4xx are client-side errors
            if status >= 500:
                with self._lock:
                    self._mark_down()
                if fallback_enabled:
                    return self._fallback(action, params)
            return {"success": False, "message": f"n8n HTTP {status}", "data": None}

        except Exception as exc:
            logger.error("[N8N] Erreur inattendue (action=%s): %s", action, exc)
            try:
                from web.radar.events import emit_event as _re
                _re(type="n8n.unexpected_error", level="error", module="n8n_executor",
                    message=f"n8n erreur inattendue — action={action}: {exc}",
                    metadata={"action": action, "error": str(exc)[:300]},
                    exception=exc)
            except Exception:
                pass
            return {"success": False, "message": str(exc), "data": None}


# Module-level singleton
n8n_executor = N8NExecutor()
