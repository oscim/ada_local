# ADA — Spécification : Intent Pipeline (Version Mimifiée)

**Projet :** ADA local
**Branche cible :** `univers`
**Périmètre :** `web/pipeline.py`, `config.py`, couche web uniquement
**Hors périmètre :** `main.py`, `/gui`, entraînement de modèle
**Remplace :** `SPEC_INTENT_DETECTION.md`, `SPEC_STRUCTURED_OUTPUT.md`
**Document :** spécification fonctionnelle
**Version :** 1.0 (Mimifiée)
**Date :** 2026-06-05
**Dépendances :** `SPEC_RADAR_INTEGRATION.md`, `ADA_SPEC_N8N_BRIDGE.md`

---

## 1. Vision & Architecture

Remplacement des routages déterministes codés en dur et des mots-clés (monolingues et interprétatifs) par un **pipeline agnostique à la langue en 3 couches**. La langue s'arrête à la Couche 1, la suite ne traite que des identifiants (IDs).

Requête utilisateur (toute langue)↓[ Couche 1 — Extraction LLM ] ──> JSON sémantique (intent + action + params)↓ (si valide et confidence ≥ 0.85)[ Couche 2 — Entity Resolver ] ──> Matching fuzzy local (Nom/Alias ──> ID réel)↓ (entités résolues)[ Couche 3 — Pipeline existant ] ──> Dispatchers (Domoticz, Proxmox, n8n...)
> ⚠️ **Règle d'or :** Si la Couche 1 ou 2 échoue ou est sous le seuil de confiance, le système bascule sur un **fallback direct et transparent vers le pipeline existant**. Aucune régression possible.

---

## 2. Spécifications des Couches

### Couche 1 : Extraction LLM (`core/intent/intent_extractor.py`)
* **Rôle :** Extrait l'intention au format JSON via un appel Ollama sans connaissance de la liste des entités réelles.
* **Payload Ollama :** `model=config.INTENT_MODEL`, `format="json"`, `stream=False` (stream désactivé pour attendre le bloc complet).
* **Schéma JSON de sortie :**
```json
{
  "intent": "string",
  "domain": "home|infra|crm|media|system|unknown",
  "action": "control|query|create|delete|backup|...",
  "params": { "entity": "string", "state?": "string", "value?": "string" },
  "response": "string",
  "confidence": 0.0
}
Aiguillage & Seuils :confidence $\ge$ 0.85 et domain != unknown ──> Transmet à la Couche 2.action == "passthrough" (conversationnel) ──> Réponse directe (response affichée dans la langue de l'user, Couches 2/3 bypassées).confidence < 0.85 OU JSON invalide ──> Fallback Pipeline Existant.Couche 2 : Entity Resolver (core/intent/entity_resolver.py & entity_index.py)Rôle : Mappe params.entity (texte brut) vers les identifiants réels des systèmes via un matching fuzzy local (sans LLM) sur des index synchronisés.Stratégie d'Indexation & Sync :Domoticz / HA : Entités, scènes, groupes ──> Polling périodique (ou webhook sortant).Proxmox : Nœuds (event-driven via config ADA), VMs/CTs ──> Polling API.Dolibarr & RMM : Sociétés, contacts, devices ──> Polling périodique.Rebuild Index : En arrière-plan (ancien index actif). Déclencheurs : 1. Polling périodique | 2. Event (ajout connecteur ADA) | 3. Manuel ("ADA, recharge la domotique").Gestion des Seuils C2 :Score $\ge$ 0.85 ──> Dispatch direct (Couche 3).Score 0.60 - 0.84 ──> Ambiguïté (Question ciblée : "Tu veux dire le bureau du RDC ou du premier ?").Score < 0.60 ──> Non trouvé (Message "entité inconnue", évite toute hallucination).Couche 3 : Pipeline Legacy (web/pipeline.py)Rôle : Reçoit le contrat enrichi et l'exécute via les dispatchers existants (comportement inchangé).Contrat JSON reçu de C2 :JSON{
  "intent": "string", "domain": "string", "action": "string",
  "params": {
    "entity_raw": "string",
    "entity_id": "string",
    "entity_source": "domoticz|proxmox|dolibarr|rmm",
    "state?": "string", "value?": "string"
  },
  "confidence_intent": "float", "confidence_entity": "float"
}
3. Configuration (config.py)Python# --- Intent Pipeline ---
INTENT_PIPELINE_ENABLED = True
INTENT_MODEL = RESPONDER_MODEL

INTENT_CONFIDENCE_THRESHOLD = 0.85
ENTITY_CONFIDENCE_THRESHOLD = 0.85
ENTITY_AMBIGUITY_THRESHOLD = 0.60

# Intervalles Polling (secondes)
ENTITY_SYNC_INTERVAL_DOMOTICZ = 300   # 5 min
ENTITY_SYNC_INTERVAL_PROXMOX = 600    # 10 min
ENTITY_SYNC_INTERVAL_DOLIBARR = 3600  # 1 heure
ENTITY_SYNC_INTERVAL_RMM = 600        # 10 min
4. Traçabilité (Radar) & Fichiers impactésÉvénements Radar à implémenter :intent.extracted (C1 OK) | intent.passthrough (Mode conv) | intent.low_confidence / intent.invalid_json (Bascule fallback)entity.resolved (C2 OK) | entity.ambiguous (Choix requis) | entity.not_found (Inconnu) | entity.index_rebuilt (Sync OK)intent.pipeline.fallback (Bascule globale sur pipeline legacy)Cartographie des fichiers :Nouveaux : core/intent/intent_extractor.py, core/intent/entity_resolver.py, core/intent/entity_index.py, web/prompts/intent_system.txtModifiés : web/pipeline.py (injection C1/C2), web/server.py (lifespan polling), config.py (variables dédiées)5. Priorités d'implémentationGeler le prompt intent_system.txt avec des exemples few-shot stables.Développer l'IntentExtractor (Appel Ollama format:json + validation du schéma).Insérer la Couche 1 dans web/pipeline.py avec gestion stricte du fallback.Créer l'EntityIndex avec la structure locale et le polling par source.Implémenter la logique fuzzy de l'EntityResolver.Insérer la Couche 2 dans le pipeline.Instrumenter avec les événements Radar et intégrer les commandes de rebuild manuel.
