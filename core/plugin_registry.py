"""
Plugin Registry — système de plugins pour ADA.

# MODULE_SOCIETE: ce fichier est le cœur du système de plugins.
# Chaque plugin hérite de BasePlugin et s'enregistre dans PluginRegistry.
# Guard : si MODULES_ENABLED["societe"] = False, le plugin SocietePlugin
# n'est pas enregistré et toute l'UI/logic societe est inactive.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


# ── Base ──────────────────────────────────────────────────────────────────────

class BasePlugin(ABC):
    """Interface commune à tous les plugins ADA."""

    # Identifiant unique (snake_case), ex : "societe"
    plugin_id: str = ""

    # Libellé affiché dans la nav
    display_name: str = ""

    # Icône (emoji ou chemin ressource)
    icon: str = "🔌"

    @abstractmethod
    def get_nav_items(self) -> list[dict]:
        """
        Retourne la liste des items à ajouter à la navigation.
        Chaque item : {"label": str, "icon": str, "route": str}
        """
        ...

    @abstractmethod
    def get_chat_context(self, company_id: str | None = None) -> str:
        """
        Retourne le bloc de contexte à injecter dans le system prompt du chat.
        """
        ...

    @abstractmethod
    def get_skills(self) -> list[str]:
        """
        Retourne les noms des fichiers skill à activer (dans skills/<plugin_id>/).
        """
        ...

    @abstractmethod
    def get_quick_prompts(self, company_id: str | None = None) -> list[str]:
        """
        Retourne les quick-prompts à afficher dans la barre de chat.
        """
        ...

    def on_enable(self) -> None:
        """Appelé quand le plugin est activé (optionnel)."""

    def on_disable(self) -> None:
        """Appelé quand le plugin est désactivé (optionnel)."""


# ── Registry ──────────────────────────────────────────────────────────────────

class PluginRegistry:
    """Registre singleton de tous les plugins actifs."""

    _instance: "PluginRegistry | None" = None

    def __new__(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins: dict[str, BasePlugin] = {}
        return cls._instance

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, plugin: BasePlugin) -> None:
        """Enregistre un plugin. Idempotent."""
        if plugin.plugin_id in self._plugins:
            return
        self._plugins[plugin.plugin_id] = plugin
        plugin.on_enable()
        print(f"[PluginRegistry] ✓ Plugin '{plugin.plugin_id}' enregistré")

    def unregister(self, plugin_id: str) -> None:
        """Désenregistre un plugin proprement."""
        plugin = self._plugins.pop(plugin_id, None)
        if plugin:
            plugin.on_disable()
            print(f"[PluginRegistry] Plugin '{plugin_id}' désactivé")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get(self, plugin_id: str) -> BasePlugin | None:
        return self._plugins.get(plugin_id)

    def all(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def is_active(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    # ── Aggregated helpers ────────────────────────────────────────────────────

    def all_nav_items(self) -> list[dict]:
        items = []
        for p in self._plugins.values():
            items.extend(p.get_nav_items())
        return items

    def combined_chat_context(self, company_id: str | None = None) -> str:
        parts = [p.get_chat_context(company_id) for p in self._plugins.values()]
        return "\n\n".join(p for p in parts if p.strip())


# Singleton global
plugin_registry = PluginRegistry()


# ── Auto-registration ─────────────────────────────────────────────────────────

def register_enabled_plugins() -> None:
    """
    # MODULE_SOCIETE: appelé au démarrage de l'app.
    Enregistre uniquement les plugins dont le flag est True dans MODULES_ENABLED.
    settings_store.modules.societe prend la priorité sur config.MODULES_ENABLED.
    """
    from config import MODULES_ENABLED  # import tardif pour éviter la circularité
    from core.settings_store import settings as _settings

    # MODULE_SOCIETE: settings_store prime sur config.py
    store_val = _settings.get("modules.societe")
    societe_enabled = store_val if store_val is not None else MODULES_ENABLED.get("societe", False)

    if societe_enabled:
        from core.societe.plugin import SocietePlugin
        plugin_registry.register(SocietePlugin())
    else:
        print("[PluginRegistry] Module 'societe' désactivé — aucun plugin societe chargé")
