"""core/intent/entity_index.py — Index d'entités multi-sources (SPEC_INTENT_PIPELINE2)

Construit et maintient en mémoire un index local des entités de chaque source
(Domoticz/HA, Proxmox, RMM, Dolibarr) pour le matching fuzzy de la Couche 2.

Cycle de vie :
  entity_index.start_polling()  → appelé depuis web/server.py au startup
  entity_index.rebuild_all()    → rebuild manuel ou déclenché par webhook
  entity_index.rebuild_source("domoticz")  → rebuild partiel
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structure d'une entrée d'index
# ---------------------------------------------------------------------------

@dataclass
class IndexEntry:
    name: str           # Nom affiché (ex: "Salon - Plafond")
    entity_id: str      # ID réel dans le système source
    source: str         # "domoticz" | "proxmox" | "rmm" | "dolibarr"
    aliases: list[str] = field(default_factory=list)  # Variantes normalisées


# ---------------------------------------------------------------------------
# Normalisation (partagée avec entity_resolver)
# ---------------------------------------------------------------------------

def normalize_entry(text: str) -> str:
    """Lowercase, supprime accents, réduit les espaces."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_str).strip().lower()


# ---------------------------------------------------------------------------
# EntityIndex
# ---------------------------------------------------------------------------

class EntityIndex:
    """Index local multi-source. Thread-safe via asyncio.Lock."""

    def __init__(self) -> None:
        self._entries: list[IndexEntry] = []
        self._lock = asyncio.Lock()
        self._polling_tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Lecture

    def get_all(self) -> list[IndexEntry]:
        """Retourne une copie de l'index courant."""
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Rebuild

    async def rebuild_source(self, source: str) -> int:
        """Reconstruit les entrées d'une source. Retourne le nombre d'entrées."""
        try:
            new_entries = await self._fetch_source(source)
        except Exception as exc:
            logger.warning("EntityIndex: échec rebuild '%s' — %s", source, exc)
            return 0

        async with self._lock:
            self._entries = [e for e in self._entries if e.source != source]
            self._entries.extend(new_entries)

        count = len(new_entries)
        logger.info("EntityIndex: source '%s' reconstruite — %d entrées", source, count)

        try:
            from web.radar.events import emit_event
            emit_event(
                type="entity.index_rebuilt",
                level="info",
                module="core.intent.entity_index",
                metadata={"source": source, "count": count},
            )
        except Exception:
            pass

        return count

    async def rebuild_all(self) -> None:
        """Reconstruit toutes les sources en parallèle."""
        sources = ["domoticz", "proxmox", "rmm", "dolibarr"]
        await asyncio.gather(
            *[self.rebuild_source(s) for s in sources],
            return_exceptions=True,
        )
        logger.info(
            "EntityIndex: rebuild complet — %d entrées totales", self.count()
        )

    # ------------------------------------------------------------------
    # Polling périodique

    def start_polling(self) -> None:
        """Lance les tâches de polling arrière-plan (appeler depuis startup)."""
        try:
            from config import (
                ENTITY_SYNC_INTERVAL_DOMOTICZ as _DOM,
                ENTITY_SYNC_INTERVAL_PROXMOX  as _PX,
                ENTITY_SYNC_INTERVAL_RMM       as _RMM,
                ENTITY_SYNC_INTERVAL_DOLIBARR  as _DOL,
            )
        except ImportError:
            _DOM, _PX, _RMM, _DOL = 300, 600, 600, 3600

        intervals = {
            "domoticz": _DOM,
            "proxmox":  _PX,
            "rmm":      _RMM,
            "dolibarr": _DOL,
        }
        for source, interval in intervals.items():
            task = asyncio.create_task(self._poll_loop(source, interval))
            self._polling_tasks.append(task)
        logger.info("EntityIndex: polling démarré pour %d sources", len(intervals))

    async def _poll_loop(self, source: str, interval: int) -> None:
        """Boucle infinie de polling pour une source."""
        await self.rebuild_source(source)  # Premier rebuild immédiat
        while True:
            await asyncio.sleep(interval)
            await self.rebuild_source(source)

    # ------------------------------------------------------------------
    # Fetch par source

    async def _fetch_source(self, source: str) -> list[IndexEntry]:
        if source == "domoticz":
            return await self._fetch_domoticz()
        if source == "proxmox":
            return await self._fetch_proxmox()
        if source == "rmm":
            return await self._fetch_rmm()
        if source == "dolibarr":
            return await self._fetch_dolibarr()
        return []

    async def _fetch_domoticz(self) -> list[IndexEntry]:
        """Charge les entités Domoticz/HA depuis unified_entity_service."""
        entries: list[IndexEntry] = []
        try:
            from core.unified_entities import unified_entity_service
            entities = unified_entity_service.get_unified_entities(force_refresh=True)
            for e in entities:
                nname = normalize_entry(e.name)
                aliases = [nname]
                if e.zone and e.zone not in ("Other", ""):
                    aliases.append(normalize_entry(e.zone))
                entries.append(IndexEntry(
                    name=e.name,
                    entity_id=e.id,
                    source="domoticz",
                    aliases=list(dict.fromkeys(aliases)),  # dédoublonner
                ))
        except Exception as exc:
            logger.debug("EntityIndex._fetch_domoticz: %s", exc)
        return entries

    async def _fetch_proxmox(self) -> list[IndexEntry]:
        """Charge les nœuds Proxmox et VM/CTs depuis config + plugin."""
        entries: list[IndexEntry] = []

        # 1. Depuis la config statique proxmox_instances.json
        try:
            conf_path = (
                Path(__file__).parent.parent.parent / "config" / "proxmox_instances.json"
            )
            if conf_path.exists():
                instances = json.loads(conf_path.read_text(encoding="utf-8"))
                for inst in instances if isinstance(instances, list) else []:
                    name = inst.get("name") or inst.get("host", "")
                    eid  = str(inst.get("id") or name)
                    if name:
                        entries.append(IndexEntry(
                            name=name,
                            entity_id=eid,
                            source="proxmox",
                            aliases=[normalize_entry(name), eid],
                        ))
        except Exception as exc:
            logger.debug("EntityIndex._fetch_proxmox (config): %s", exc)

        # 2. VM/CTs live via plugin (si disponible)
        try:
            from core.plugin_registry import plugin_registry
            result = plugin_registry.dispatch_action("vm_list", {"instance_id": None, "node": None})
            if result and result.get("success"):
                raw = result.get("message", "")
                # Extraire les lignes "VM 101 (nom)" ou "CT 201 (nom)"
                for m in re.finditer(
                    r"\b(?:VM|CT)\s+(\d{2,4})\s+\(([^)]+)\)", raw or "", re.IGNORECASE
                ):
                    vmid, name = m.group(1), m.group(2).strip()
                    # Éviter les doublons
                    if not any(e.entity_id == vmid for e in entries):
                        entries.append(IndexEntry(
                            name=name,
                            entity_id=vmid,
                            source="proxmox",
                            aliases=[normalize_entry(name), vmid],
                        ))
        except Exception as exc:
            logger.debug("EntityIndex._fetch_proxmox (plugin): %s", exc)

        return entries

    async def _fetch_rmm(self) -> list[IndexEntry]:
        """Charge les clients/devices RMM."""
        entries: list[IndexEntry] = []
        try:
            from core.plugin_registry import plugin_registry
            result = plugin_registry.dispatch_action("rmm_clients_list", {})
            if result and result.get("success") and isinstance(result.get("data"), list):
                for item in result["data"]:
                    name = item.get("name") or item.get("client_name", "")
                    eid  = str(item.get("id") or name)
                    if name:
                        entries.append(IndexEntry(
                            name=name,
                            entity_id=eid,
                            source="rmm",
                            aliases=[normalize_entry(name)],
                        ))
        except Exception as exc:
            logger.debug("EntityIndex._fetch_rmm: %s", exc)
        return entries

    async def _fetch_dolibarr(self) -> list[IndexEntry]:
        """Charge les sociétés depuis le module CRM."""
        entries: list[IndexEntry] = []
        try:
            from core.societe.societe_service import get_companies  # type: ignore
            companies = get_companies()
            for c in companies or []:
                name = c.get("name") or c.get("nom", "")
                eid  = str(c.get("id") or name)
                if name:
                    entries.append(IndexEntry(
                        name=name,
                        entity_id=eid,
                        source="dolibarr",
                        aliases=[normalize_entry(name)],
                    ))
        except Exception as exc:
            logger.debug("EntityIndex._fetch_dolibarr: %s", exc)
        return entries


# ---------------------------------------------------------------------------
# Singleton

entity_index = EntityIndex()
