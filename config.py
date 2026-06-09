"""
Centralized configuration for Pocket AI.
"""

import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        return float(value) if value not in (None, "") else default
    except ValueError:
        return default


# --- Docker / externalized paths ---
# Ces dossiers existent dans l'image pour un fonctionnement autonome.
# En production, ils doivent de préférence être bind-mountés depuis l'hôte.
ADA_DATA_DIR = Path(os.getenv("ADA_DATA_DIR", "data"))
ADA_SKILLS_DIR = Path(os.getenv("ADA_SKILLS_DIR", "skills"))
ADA_DOCUMENTS_DIR = Path(os.getenv("ADA_DOCUMENTS_DIR", "documents"))
ADA_RAG_DIR = Path(os.getenv("ADA_RAG_DIR", "rag"))
ADA_MODELS_DIR = Path(os.getenv("ADA_MODELS_DIR", "models"))
ADA_CACHE_DIR = Path(os.getenv("ADA_CACHE_DIR", ".cache"))
ADA_CERTS_DIR = Path(os.getenv("ADA_CERTS_DIR", "web/certs"))

# --- Intent Mining (extraction corpus depuis Radar) ---
INTENT_MINING_ENABLED: bool = _env_bool("INTENT_MINING_ENABLED", True)
INTENT_MINING_AUTO_RUN_ON_STARTUP: bool = _env_bool("INTENT_MINING_AUTO_RUN_ON_STARTUP", True)
INTENT_MINING_PERIODIC_INTERVAL_MINUTES: int = _env_int("INTENT_MINING_PERIODIC_INTERVAL_MINUTES", 60)
INTENT_MINING_DB_PATH: str = os.getenv("INTENT_MINING_DB_PATH", str(ADA_DATA_DIR / "intent_corpus.sqlite"))

# --- Intent Detection ---
INTENT_DETECTION_ENABLED: bool = _env_bool("INTENT_DETECTION_ENABLED", True)
INTENT_DETECTION_THRESHOLD_CERTAIN: float = _env_float("INTENT_DETECTION_THRESHOLD_CERTAIN", 0.92)
INTENT_DETECTION_THRESHOLD_CANDIDATE: float = _env_float("INTENT_DETECTION_THRESHOLD_CANDIDATE", 0.75)
INTENT_DETECTION_MAX_CORPUS_SIZE: int = _env_int("INTENT_DETECTION_MAX_CORPUS_SIZE", 5000)
INTENT_DETECTION_UNIVERSE_FILTER: bool = _env_bool("INTENT_DETECTION_UNIVERSE_FILTER", True)
INTENT_DETECTION_INDEX_REBUILD_ON_FEEDBACK: bool = _env_bool("INTENT_DETECTION_INDEX_REBUILD_ON_FEEDBACK", True)

# --- Radar Local Event Console ---
RADAR_ENABLED: bool = _env_bool("RADAR_ENABLED", True)
RADAR_DB_PATH: str = os.getenv("RADAR_DB_PATH", str(ADA_DATA_DIR / "radar" / "events.sqlite"))
RADAR_MAX_EVENTS: int = _env_int("RADAR_MAX_EVENTS", 100_000)
RADAR_RETENTION_DAYS: int = _env_int("RADAR_RETENTION_DAYS", 30)
RADAR_TEXT_PREVIEW_MAX: int = _env_int("RADAR_TEXT_PREVIEW_MAX", 300)
RADAR_SENSITIVE_FIELDS: list = [
    "api_key", "token", "access_token", "refresh_token",
    "authorization", "password", "secret", "cookie",
    "session_cookie", "private_key",
]

# --- Model Configuration ---
RESPONDER_MODEL = os.getenv("RESPONDER_MODEL", "mistral:latest")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api")

# --- Marketing / MargePro ---
# Modèle utilisé pour la génération marketing (peut être différent du modèle principal)
# Ex : "deepseek-r1:7b", "mistral:7b", "llama3.1:8b" pour de meilleures copies
MARKETING_MODEL = os.getenv("MARKETING_MODEL", RESPONDER_MODEL)  # Même modèle par défaut, remplace si besoin

# Contexte produit MargePro — chargé dynamiquement depuis skills/margepro/SKILL.md
# Édite ce fichier depuis l'onglet Compétences de l'UI pour mettre à jour le contexte.
def _load_margepro_context() -> str:
    import re as _re
    from pathlib import Path as _Path
    skill_path = _Path(os.getenv("ADA_SKILLS_DIR", str(_Path(__file__).parent / "skills"))) / "margepro" / "SKILL.md"
    try:
        raw = skill_path.read_text(encoding="utf-8")
        # Retire le frontmatter YAML (entre les deux ---)
        m = _re.match(r"^---[ \t]*\r?\n.*?\r?\n---[ \t]*\r?\n(.*)", raw, _re.DOTALL)
        return m.group(1).strip() if m else raw.strip()
    except Exception:
        return ""

MARGEPRO_CONTEXT = _load_margepro_context()
LOCAL_ROUTER_PATH = os.getenv("LOCAL_ROUTER_PATH", str(ADA_MODELS_DIR / "merged_model"))
HF_ROUTER_REPO = os.getenv("HF_ROUTER_REPO", "nlouis/pocket-ai-router")  # Hugging Face repo for auto-download
MAX_HISTORY = _env_int("MAX_HISTORY", 20)

# --- TTS Configuration ---
TTS_VOICE_MODEL = "en_GB-northern_english_male-medium"
TTS_MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx"
TTS_CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json"

# --- STT Configuration ---
# Using RealTimeSTT for real-time speech-to-text
STT_MODEL_PATH = None  # Not used with RealTimeSTT (kept for compatibility)
STT_USE_WHISPER = False  # Not used with RealTimeSTT (kept for compatibility)
WHISPER_MODEL_SIZE = "base"  # Not used with RealTimeSTT (kept for compatibility)
WAKE_WORD_DETECTION_METHOD = "transcription"  # RealTimeSTT uses transcription-based detection
REALTIMESTT_MODEL = "base"  # RealTimeSTT model: "tiny", "base", "small", "medium", "large"
USE_PORCUPINE_WAKE_WORD = False  # Use Porcupine for wake word detection (more accurate, requires API key)
PORCUPINE_ACCESS_KEY = None  # Get from https://console.picovoice.ai/ (optional, for better wake word detection)
WAKE_WORD = "jarvis"
WAKE_WORD_SENSITIVITY = 0.4  # For audio pattern matching (0.0-1.0, higher = more sensitive) - Lowered to reduce false positives
WAKE_WORD_CONFIRMATION_COUNT = 1  # Require multiple detections before triggering (reduces false positives)
STT_SAMPLE_RATE = 16000
STT_CHUNK_SIZE = 4096
STT_RECORD_TIMEOUT = 5.0  # Maximum seconds to record after wake word

# --- Voice Assistant Configuration ---
VOICE_ASSISTANT_ENABLED = _env_bool("VOICE_ASSISTANT_ENABLED", True)
QWEN_TIMEOUT_SECONDS = _env_int("QWEN_TIMEOUT_SECONDS", 300)  # 5 minutes of inactivity before sleep
QWEN_KEEP_ALIVE = os.getenv("QWEN_KEEP_ALIVE", "5m")  # Keep in memory for 5 minutes after last use

# --- Router Keywords ---
# REMOVED: ROUTER_KEYWORDS - All queries now go through Function Gemma router
# The router handles all routing decisions, so keyword-based bypass is no longer needed

# --- Function Definitions (Official JSON Schema) ---
FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "control_light",
            "description": "Controls smart lights - turn on, off, or dim lights in a room",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "description": "The action to perform: on, off, or dim"},
                    "room": {"type": "string", "description": "The room name where the light is located"}
                },
                "required": ["action", "room"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web for information using Google",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query string"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Sets a countdown timer for a specified duration",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "string", "description": "Time duration like 5 minutes or 1 hour"},
                    "label": {"type": "string", "description": "Optional timer name or label"}
                },
                "required": ["duration"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Creates a new calendar event or appointment",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The event title"},
                    "date": {"type": "string", "description": "The date of the event"},
                    "time": {"type": "string", "description": "The time of the event"},
                    "description": {"type": "string", "description": "Optional event details"}
                },
                "required": ["title", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_calendar",
            "description": "Reads and retrieves calendar events for a date or time range",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "The date or date range to check"},
                    "filter": {"type": "string", "description": "Optional filter like meetings or appointments"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "Execute a PowerShell or shell command on the local system. Use for: listing files, checking system info, running scripts, managing processes, checking network, installing packages, or any system operation the user requests explicitly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The PowerShell/shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 120)"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "passthrough",
            "description": "DEFAULT FUNCTION - Use this whenever no other function is clearly needed. This is the fallback for: greetings (hello, hi, good morning), chitchat (how are you, what's your name), general knowledge questions, explanations, conversations, and ANY query that does NOT explicitly require controlling lights, setting timers, searching the web, or managing calendar events. When in doubt, use passthrough.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thinking": {"type": "boolean", "description": "Set to true for complex reasoning/math/logic, false for simple greetings and chitchat."}
                },
                "required": ["thinking"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "play_music",
            "description": "Play music by genre or artist on the default media player. Use when the user wants to listen to music.",
            "parameters": {
                "type": "object",
                "properties": {
                    "genre": {
                        "type": "string",
                        "description": "Music genre, e.g. jazz, rock, classical, blues, electro",
                    },
                    "artist": {
                        "type": "string",
                        "description": "Artist name, e.g. Ween, Miles Davis, Pink Floyd",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_media",
            "description": "Control media playback: pause, stop, or skip to next track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["pause", "stop", "next"],
                        "description": "Playback action to perform",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Control the volume of the default media player.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "set"],
                        "description": "up/down for relative change, set for absolute level",
                    },
                    "level": {
                        "type": "number",
                        "description": "Volume level 0-100, required when action is set",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_book",
            "description": "Search for a book in the personal library by title, author, or genre/tag. Use when the user asks for a book, novel, or wants to find something to read.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search terms: title, author name, or genre/tag (e.g. 'Dune', 'Frank Herbert', 'science fiction')",
                    },
                    "search_type": {
                        "type": "string",
                        "enum": ["title", "author", "tags", "all"],
                        "description": "Which field to search. Defaults to 'all'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# MODULE_SOCIETE: feature flag — mettre à False pour désactiver entièrement le module
MODULES_ENABLED: dict = {
    "societe":      True,
    "domotique":    True,    # → DomotiquePlugin (univers: home)
    "proxmox":      True,    # → ProxmoxPlugin (univers: opent)
    "rmm":          True,    # → RmmPlugin (univers: opent)
    "telephony":    False,   # → TelephonyPlugin (off par défaut)
    "margepro":     True,    # → MargeProPlugin (univers: margep)
    "music":        False,   # → module Musique (off par défaut)
    "n8n_bridge":   True,    # → Connecteur n8n sortant (events + fallback)
    "n8n_fallback": True,    # → Pipeline fallback automatique vers n8n
}

# --- Intent Pipeline (SPEC_INTENT_PIPELINE2) ---
INTENT_DETECTION_ENABLED  = False   # Détecteur legacy (intent_detector.py)
INTENT_PIPELINE_ENABLED   = True    # Nouveau pipeline C1/C2/C3 agnostique à la langue

INTENT_MODEL = RESPONDER_MODEL      # Modèle utilisé pour l'extraction d'intention

INTENT_CONFIDENCE_THRESHOLD = 0.85  # Seuil C1 : en dessous → fallback pipeline legacy
ENTITY_CONFIDENCE_THRESHOLD = 0.85  # Seuil C2 : en dessous mais > AMBIGUITY → question ciblée
ENTITY_AMBIGUITY_THRESHOLD  = 0.60  # Seuil C2 : en dessous → "entité inconnue"

# Intervalles de polling d'index (secondes)
ENTITY_SYNC_INTERVAL_DOMOTICZ = 300   # 5 min
ENTITY_SYNC_INTERVAL_PROXMOX  = 600   # 10 min
ENTITY_SYNC_INTERVAL_DOLIBARR = 3600  # 1 heure
ENTITY_SYNC_INTERVAL_RMM      = 600   # 10 min

# --- N8N Bridge ---
N8N_BRIDGE_ENABLED           = True
N8N_BASE_URL                 = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_DEFAULT_WEBHOOK_URL      = os.getenv("N8N_DEFAULT_WEBHOOK_URL", f"{N8N_BASE_URL.rstrip('/')}/webhook/ada-event")
N8N_TIMEOUT_SECONDS          = _env_int("N8N_TIMEOUT_SECONDS", 10)
N8N_MAX_RETRIES              = _env_int("N8N_MAX_RETRIES", 2)
N8N_VERIFY_SSL               = _env_bool("N8N_VERIFY_SSL", True)
N8N_FALLBACK_ENABLED         = _env_bool("N8N_FALLBACK_ENABLED", True)
N8N_ALLOWED_EVENT_DOMAINS: list = [
    "domotic", "marketing", "social", "lead", "crm",
    "support", "content", "notification", "workflow", "system",
]

# --- Feedback Loop & Auto-tuning ---
FEEDBACK_ENABLED: bool = _env_bool("FEEDBACK_ENABLED", True)
FEEDBACK_AUTOSKILL_VALIDATE_THRESHOLD: int = _env_int("FEEDBACK_AUTOSKILL_VALIDATE_THRESHOLD", 3)   # validations pour promouvoir 'confirmed'
FEEDBACK_AUTOSKILL_REJECT_THRESHOLD: int = _env_int("FEEDBACK_AUTOSKILL_REJECT_THRESHOLD", 2)     # rejets pour 'under_review'
FEEDBACK_REBUILD_TRIGGER_POSITIVE: int = _env_int("FEEDBACK_REBUILD_TRIGGER_POSITIVE", 10)      # signaux positifs avant rebuild index
FEEDBACK_REBUILD_TRIGGER_NEGATIVE: int = _env_int("FEEDBACK_REBUILD_TRIGGER_NEGATIVE", 3)       # signaux négatifs avant rebuild index
FEEDBACK_ERROR_LOG_AUTO_RADAR: bool = _env_bool("FEEDBACK_ERROR_LOG_AUTO_RADAR", True)       # alimentation auto depuis Radar
FEEDBACK_ERROR_LOG_RETENTION_DAYS: int = _env_int("FEEDBACK_ERROR_LOG_RETENTION_DAYS", 90)

# --- Semantic Memory (SPEC_SEMANTIC_MEMORY_CONTEXT) ---
SEMANTIC_MEMORY_ENABLED: bool = _env_bool("SEMANTIC_MEMORY_ENABLED", True)
SEMANTIC_ONBOARDING_MAX_TURNS: int = _env_int("SEMANTIC_ONBOARDING_MAX_TURNS", 10)

# --- Console Colors ---
GRAY = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
