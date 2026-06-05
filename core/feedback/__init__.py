"""core/feedback — Boucle de feedback, validation et auto-tuning ADA."""
from .error_store import init_db, log_error, get_error, list_errors, resolve_error, stats, export_errors
from .feedback_processor import FeedbackProcessor

__all__ = [
    "init_db", "log_error", "get_error", "list_errors", "resolve_error", "stats", "export_errors",
    "FeedbackProcessor",
]
