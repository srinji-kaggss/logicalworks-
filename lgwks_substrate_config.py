"""lgwks_substrate_config — constants, paths, regexes, and shared types for substrate runs.

This module is the foundation layer. It defines all configuration values,
compiled regexes, and path constants used across the substrate system.
Defense-in-Depth: all regexes are pre-compiled at import time; all paths
are resolved eagerly to catch filesystem issues early.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT / "store" / "substrate"
GLOBAL_ROOT = ROOT / "store" / "substrate-global"
GLOBAL_FACT_DB = GLOBAL_ROOT / "fact_vectors.db"

# ── Exceptions ───────────────────────────────────────────────────────────────


class EmbeddingProviderUnavailable(RuntimeError):
    """Raised when an explicitly requested semantic embedding provider cannot produce vectors."""


# ── Types ────────────────────────────────────────────────────────────────────


class FrontierList(list):
    """Frontier list with optional click telemetry metadata."""

    def __init__(self, *args, click_telemetry=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.click_telemetry = click_telemetry or {}


# ── File-type constants ──────────────────────────────────────────────────────

TEXT_EXT = {
    ".txt", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".csv",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt", ".swift", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".sh", ".bash", ".zsh", ".sql", ".lua", ".r",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "target", ".next", "dist", "build", "store"}
IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"})

# ── Regex constants ──────────────────────────────────────────────────────────

TAG_RE = re.compile(r"<[^>]+>")  # strip HTML/XML tags
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")  # owner/repo slug
NUMERIC_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b|\$\s*\d[\d,]*(?:\.\d+)?")
CODE_RE = re.compile(r"\b(?:[A-Z]{2,}\d{0,4}|T\d{4}|TR\d{2}|[A-Z]{2,5})\b")
REF_RE = re.compile(r"\b(?:s\.?\s*\d+(?:\.\d+)?|\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
PREVIOUS_VERSION_RE = re.compile(r"\bV(?:3[0-5]|[12]\d)\b", re.I)
AUTH_GATE_RE = re.compile(
    r"\b("
    r"sign in|log in|login|password|multi-factor|two-factor|passkey|touch id|face id|verify identity|"
    r"one-time code|magic link|otp|captcha|cloudflare|checking your browser|verify you are human|"
    r"access denied|enable javascript|challenge|bot detection|unusual traffic"
    r")\b",
    re.I,
)
STRONG_AUTH_GATE_RE = re.compile(
    r"\b("
    r"sign in|log in|password|multi-factor|two-factor|passkey|touch id|face id|verify identity|"
    r"one-time code|magic link|otp|captcha|cloudflare|checking your browser|verify you are human|"
    r"access denied|enable javascript|challenge|bot detection|unusual traffic"
    r")\b",
    re.I,
)

# ── Domain-specific term sets ────────────────────────────────────────────────

PROCEDURE_TERMS = {
    "must", "requires", "required", "only", "cannot", "blocked", "allowed", "if",
    "when", "then", "before", "after", "submit", "transfer", "route", "settlement",
    "minimum", "maximum", "threshold", "code", "form", "designation", "version",
}
NARRATIVE_TERMS = {
    "think", "feel", "believe", "love", "maybe", "probably", "helpful", "great",
    "excellent", "frustrated", "opinion", "story", "journey", "marketing", "vision",
}

# ── Versioning constants ─────────────────────────────────────────────────────

UPCOMING_EFFECTIVE_DATE = date(2026, 6, 15)
VERSION_BUCKETS = ("Current", "Upcoming", "Previous")

# ── Network module sets ────────────────────────────────────────────────────────

_NET_MODULES = {"requests", "urllib3", "httpx", "aiohttp", "pycurl", "tornado.httpclient"}
_NET_TOPS = {"requests", "urllib", "http", "httpx", "aiohttp", "urllib3", "tornado"}
_LOG_ATTRS = {"debug", "info", "warning", "error", "critical", "exception", "log"}
_LOG_OBJ_RE = re.compile(r"log(?:ger)?[_.]?\d*", re.I)
_SECRET_RE = re.compile(
    r"\b(?:password|passwd|pwd|secret|token|api[-_]?key|auth[-_]?key|"
    r"access[-_]?key|private[-_]?key|client[-_]?secret|"
    r"credential|bearer|jwt|oauth[-_]?token|session[-_]?id|"
    r"ssh[-_]?key|pem|rsa[-_]?key|encryption[-_]?key|decrypt[-_]?key)\b",
    re.I,
)
