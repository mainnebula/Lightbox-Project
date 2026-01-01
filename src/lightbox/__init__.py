"""Lightbox: Flight recorder for AI agents.

Lightbox records tool execution events as append-only, tamper-evident records.
It captures what external actions an agent took, not internal reasoning.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lightbox")
except PackageNotFoundError:
    __version__ = "0.1.0"  # Fallback for development

from lightbox.core import (
    Session,
    emit,
    get_current_session,
    start_session,
)
from lightbox.integrity import VerificationResult, VerifyStatus, verify_session
from lightbox.models import Event
from lightbox.storage import RedactionConfig

__all__ = [
    "Session",
    "Event",
    "emit",
    "start_session",
    "get_current_session",
    "verify_session",
    "VerificationResult",
    "VerifyStatus",
    "RedactionConfig",
]
