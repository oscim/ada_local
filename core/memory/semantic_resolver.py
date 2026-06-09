"""
Semantic memory resolver — position 1 in the pipeline (SPEC_SEMANTIC_MEMORY_CONTEXT).

Resolves pronominal / relational entity references ("ma chambre", "la chambre
d'Amaury") by looking up atomic fact triplets stored in consolidated_memories.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Pronominal / possessive patterns
# ---------------------------------------------------------------------------
# "ma chambre", "mon bureau", "mes enfants"
_RE_POSSESSIVE = re.compile(
    r"\b(ma|mon|mes|notre)\s+(\w+)\b",
    re.IGNORECASE,
)

# "la chambre d'Amaury" / "le bureau de Thomas"
_RE_NAMED_ROOM = re.compile(
    r"\b(?:la|le|les)\s+(\w+)\s+d[e']\s*([A-ZÀ-ÿ][a-zà-ÿ]+)\b",
)

# "mon collègue Thomas" / "mon ami Luc"
_RE_PERSON_REL = re.compile(
    r"\b(mon|ma|mes)\s+(collègue|ami(?:e)?|frère|sœur|fils|fille|père|mère|parent|patron|chef|époux|épouse|mari|femme)\s+([A-ZÀ-ÿ][a-zà-ÿ]+)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Nouns that are plausibly domotique-relevant (filter spurious "mon café")
# ---------------------------------------------------------------------------
_DOMOTIQUE_NOUNS: frozenset[str] = frozenset([
    "chambre", "salon", "cuisine", "salle", "bureau", "garage",
    "jardin", "terrasse", "cave", "grenier", "couloir", "toilettes",
    "wc", "entrée", "hall", "palier", "dressing", "véranda", "piscine",
    "lumière", "lampe", "lumières", "lampes", "volet", "volets",
    "thermostat", "radiateur", "clim", "climatisation",
    "télé", "tv", "télévision", "enceinte", "son",
])

# ---------------------------------------------------------------------------
# Verb → entity type filter
# ---------------------------------------------------------------------------
_VERB_TYPE: dict[str, str] = {
    "allume": "light",
    "allumer": "light",
    "éteins": "light",
    "éteindre": "light",
    "baisse": "light",
    "augmente": "light",
    "tamise": "light",
    "règle la température": "thermostat",
    "chauffe": "thermostat",
    "réchauffe": "thermostat",
    "refroidis": "thermostat",
    "joue": "media_player",
    "mets de la musique": "media_player",
    "arrête la musique": "media_player",
    "ouvre": "switch",
    "ferme": "switch",
    "active": "switch",
    "désactive": "switch",
    "verrouille": "lock",
    "déverrouille": "lock",
}

_DOMOTIQUE_VERBS: frozenset[str] = frozenset(_VERB_TYPE.keys())


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
class ResolvedEntity(NamedTuple):
    original: str          # "ma chambre"
    resolved: str          # "chambre_parents"
    match_type: str        # "possessive" | "named_room" | "person_rel"
    type_filter: str | None


class ResolutionResult(NamedTuple):
    resolved_text: str
    entities: list[ResolvedEntity]
    type_filter: str | None
    unresolved_refs: list[str]  # pronominal refs that could NOT be resolved


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_index(consolidated: list[dict]) -> dict[tuple[str, str], str]:
    """(subject_lower, relation_lower) → object from all consolidated facts."""
    index: dict[tuple[str, str], str] = {}
    for record in consolidated:
        facts = record.get("facts", [])
        if not isinstance(facts, list):
            continue
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            s = str(fact.get("subject", "")).lower().strip()
            r = str(fact.get("relation", "")).lower().strip()
            o = str(fact.get("object", "")).strip()
            if s and r and o:
                index[(s, r)] = o
    return index


def _type_filter(text_lower: str) -> str | None:
    for verb, typ in _VERB_TYPE.items():
        if verb in text_lower:
            return typ
    return None


def _resolve_possessive(
    noun_lower: str,
    index: dict[tuple[str, str], str],
    user_name_lower: str,
) -> str | None:
    if user_name_lower:
        obj = index.get((user_name_lower, noun_lower))
        if obj:
            return obj
    # Fallback: any subject → noun_lower → object
    for (s, r), o in index.items():
        if r == noun_lower:
            return o
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def resolve(
    user_text: str,
    user_name: str = "",
    consolidated: list[dict] | None = None,
) -> ResolutionResult:
    """
    Resolve pronominal entity references in *user_text* using triplet memory.

    :param user_text: Raw user input
    :param user_name: User's first name (for "ma chambre" → user→chambre→X lookup)
    :param consolidated: Pre-loaded consolidated records; if None loads from memory_store
    :returns: ResolutionResult
    """
    if consolidated is None:
        try:
            from core.memory_store import memory_store
            consolidated = memory_store.get_consolidated(days=365)
        except Exception:
            consolidated = []

    index = _build_index(consolidated)
    user_name_lower = user_name.lower().strip() if user_name else ""

    resolved_text = user_text
    text_lower = user_text.lower()
    entities: list[ResolvedEntity] = []
    unresolved_refs: list[str] = []
    tfilter = _type_filter(text_lower)

    # 1. Named-room: "la chambre d'Amaury" → (amaury, chambre) → object
    for m in _RE_NAMED_ROOM.finditer(user_text):
        noun_l = m.group(1).lower()
        person_l = m.group(2).lower()
        target = index.get((person_l, noun_l))
        if target:
            entities.append(ResolvedEntity(m.group(0), target, "named_room", tfilter))
            resolved_text = resolved_text.replace(m.group(0), target, 1)
        else:
            unresolved_refs.append(m.group(0))

    # 2. Person relation: "mon collègue Thomas" — annotate if known
    for m in _RE_PERSON_REL.finditer(resolved_text):
        rel_l = m.group(2).lower()
        person_l = m.group(3).lower()
        stored_rel = index.get((person_l, "relation"))
        if stored_rel and stored_rel.lower() == rel_l:
            entities.append(ResolvedEntity(m.group(0), m.group(3), "person_rel", None))
        # Person relations are annotated but not substituted in text

    # 3. Possessive: "ma chambre", "mon bureau"
    for m in _RE_POSSESSIVE.finditer(resolved_text):
        noun = m.group(2)
        noun_l = noun.lower()
        # Only resolve domotique-relevant nouns
        if noun_l not in _DOMOTIQUE_NOUNS:
            continue
        target = _resolve_possessive(noun_l, index, user_name_lower)
        if target:
            entities.append(ResolvedEntity(m.group(0), target, "possessive", tfilter))
            resolved_text = resolved_text.replace(m.group(0), target, 1)
        else:
            unresolved_refs.append(m.group(0))

    return ResolutionResult(
        resolved_text=resolved_text,
        entities=entities,
        type_filter=tfilter,
        unresolved_refs=unresolved_refs,
    )


def has_domotique_context(text_lower: str) -> bool:
    """True if text contains a domotique action verb."""
    return any(v in text_lower for v in _DOMOTIQUE_VERBS)
