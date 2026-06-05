"""core/intent/entity_resolver.py

Re-contextualizes action parameters extracted from the intent corpus onto the
current request.  Supports four entity categories (v1):
  - room / domotique zone
  - Proxmox VM / CT id
  - timer label
  - RMM client name

The resolver returns a (possibly-mutated) copy of the params dict and a
boolean indicating whether all variable entities were successfully resolved.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_str).strip().lower()


# ---------------------------------------------------------------------------
# Entity patterns in French / mixed
# ---------------------------------------------------------------------------

# Domotique room/zone : "du salon", "de la cuisine", "du bureau", …
_ROOM_RE = re.compile(
    r"\b(?:d(?:u|e la?|es?|'|')\s*)?(salon|cuisine|bureau|chambre|salle\s+(?:de\s+bain|à\s+manger|de\s+jeux)|"
    r"garage|entrée|entree|couloir|toilette[s]?|wc|cave|grenier|jardin|terrasse|véranda|veranda"
    r"|séjour|sejour|living|hall|bibliothèque|bibliotheque|dressing|buanderie|cellier)\b",
    re.IGNORECASE,
)

# Proxmox VM/CT identifier (2-4 digits)
_VMID_RE = re.compile(r"\b(\d{2,4})\b")

# Timer label : "pour <label>", "nommé <label>", "appelé <label>"
_TIMER_LABEL_RE = re.compile(
    r"\b(?:pour|nommé|nomme|appelé|appele|intitulé|intitule)\s+(.+?)(?:\s*$|\s+(?:de|dans|à)\b)",
    re.IGNORECASE,
)

# RMM client name (single or double word, often capitalized)
_RMM_CLIENT_RE = re.compile(
    r"\b(?:client|société|societe|company|pour)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-]+(?:\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\-]+)?)\b",
    re.IGNORECASE,
)


class EntityResolver:
    """
    Resolves and re-contextualizes variable entities in action parameters.

    Parameters
    ----------
    unified_entity_service : optional
        The unified_entity_service singleton for domotique entity validation.
    """

    def __init__(self, unified_entity_service=None) -> None:
        self._entity_service = unified_entity_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        current_text: str,
        source_text: str,
        params: dict[str, Any],
        action: str,
    ) -> tuple[dict[str, Any], bool]:
        """
        Re-contextualize *params* by extracting entities from *current_text*.

        Returns
        -------
        (updated_params, all_resolved)
            all_resolved is False when a required entity could not be resolved.
        """
        updated = dict(params)
        all_resolved = True

        # Room / zone (domotique)
        if "room" in updated or action in ("control_light", "set_scene", "device_status"):
            room, ok = self._resolve_room(current_text, source_text, updated.get("room"))
            if room:
                updated["room"] = room
            if not ok:
                all_resolved = False

        # VM / CT identifier (Proxmox)
        if "vmid" in updated or action in ("vm_power", "vm_backup", "vm_status", "node_stats"):
            vmid, ok = self._resolve_vmid(current_text, source_text, updated.get("vmid"))
            if vmid is not None:
                updated["vmid"] = vmid
            if not ok:
                all_resolved = False

        # Timer label
        if "label" in updated or action == "set_timer":
            label = self._resolve_timer_label(current_text)
            if label:
                updated["label"] = label
            # label is optional — not failing if absent

        # RMM client name
        if "client_name" in updated or "client" in updated:
            client = self._resolve_rmm_client(current_text)
            key = "client_name" if "client_name" in updated else "client"
            if client:
                updated[key] = client

        return updated, all_resolved

    # ------------------------------------------------------------------
    # Private resolvers
    # ------------------------------------------------------------------

    def _resolve_room(
        self, current_text: str, source_text: str, fallback_room: str | None
    ) -> tuple[str | None, bool]:
        """Extract room from current_text; validate against entity service."""
        m = _ROOM_RE.search(current_text)
        room = m.group(1).strip() if m else None

        if room is None:
            # No room mentioned in current request — keep corpus value
            room = fallback_room

        if room and self._entity_service is not None:
            # Validate entity exists in the domotique service
            try:
                entities = self._entity_service.get_unified_entities(force_refresh=False)
                room_lower = _normalize(room)
                known = any(
                    room_lower in _normalize(e.name) or room_lower in _normalize(e.zone or "")
                    for e in entities
                )
                if not known:
                    return room, False  # entity unknown → is_certain=False
            except Exception:
                pass  # service unavailable → optimistic, don't downgrade

        return room, True

    def _resolve_vmid(
        self, current_text: str, source_text: str, fallback_vmid: Any
    ) -> tuple[int | None, bool]:
        """Extract VM/CT id from current_text."""
        matches = _VMID_RE.findall(current_text)
        # Prefer ids that differ from source text ids (i.e. a new target)
        source_ids = set(_VMID_RE.findall(source_text))
        new_ids = [x for x in matches if x not in source_ids]
        if new_ids:
            return int(new_ids[0]), True
        if matches:
            return int(matches[0]), True
        if fallback_vmid is not None:
            try:
                return int(fallback_vmid), True
            except (ValueError, TypeError):
                pass
        return None, False

    @staticmethod
    def _resolve_timer_label(current_text: str) -> str | None:
        m = _TIMER_LABEL_RE.search(current_text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _resolve_rmm_client(current_text: str) -> str | None:
        m = _RMM_CLIENT_RE.search(current_text)
        return m.group(1).strip() if m else None


# Lazy singleton — created on first import of intent_detector
_resolver_instance: EntityResolver | None = None


def get_resolver() -> EntityResolver:
    global _resolver_instance
    if _resolver_instance is None:
        try:
            from core.unified_entities import unified_entity_service
            _resolver_instance = EntityResolver(unified_entity_service)
        except Exception:
            _resolver_instance = EntityResolver()
    return _resolver_instance
