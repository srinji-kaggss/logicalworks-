"""lgwks_tokenizer_registry — tokenizer/analyzer identity registry.

Schema id: lgwks.tokenizer.registry.v1

Every stored tokenized artifact carries a `tokenization_id` referencing a row
in this registry. The registry makes the DB tokenizer-aware: FTS, vector
embeddings, graph edges, and chunk tables all reference a specific
tokenizer/analyzer version rather than a pipeline-local default.

Default entries:
  - word_regex:v1 — the existing WORD_RE regex used by substrate text chunking.
  - aetherius:v0  — the Aetherius Neural Tokenizer (ANT) when present.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lgwks_substrate_config as config

SCHEMA = "lgwks.tokenizer.registry.v1"
DEFAULT_WORD_REGEX_ID = "word_regex:v1"
DEFAULT_AETHERIUS_ID = "aetherius:v0"


class RegistryError(ValueError):
    """Contract violation in the tokenizer registry."""


@dataclass(frozen=True)
class TokenizerRecord:
    """Immutable tokenizer/analyzer registration record."""

    tokenizer_id: str
    kind: str
    version: str
    config_json: str
    vocab_cid: str
    modality_anchors: tuple[str, ...]
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tokenizer_id": self.tokenizer_id,
            "kind": self.kind,
            "version": self.version,
            "config_json": self.config_json,
            "vocab_cid": self.vocab_cid,
            "modality_anchors": list(self.modality_anchors),
            "created_at": self.created_at,
        }


def _default_word_regex_config() -> str:
    return json.dumps({
        "pattern": config.WORD_RE.pattern,
        "description": "lowercase alphanumeric word tokenizer used by substrate text chunking",
    }, sort_keys=True)


def _default_aetherius_config() -> str:
    # Import lazily so the registry does not require the ANT vocab to exist.
    return json.dumps({
        "byte_range": "0-255",
        "core_range": "256-511",
        "modal_range": "512-1023",
        "merge_range": "1024+",
        "description": "Aetherius Neural Tokenizer: byte-level BPE with modality anchors",
    }, sort_keys=True)


class TokenizerRegistry:
    """Local-first registry of tokenizers/analyzers.

    The registry is persisted as a JSONL file at `store/tokenizer_registry.jsonl`
    under the repo root. Writes are append-only and idempotent: registering the
    same tokenizer_id twice is a no-op (the first definition wins).
    """

    def __init__(self, root: Path):
        self.root = root
        self.path = root / "store" / "tokenizer_registry.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, TokenizerRecord] = {}
        self._load()
        self._ensure_defaults()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if data.get("schema") != SCHEMA or "tokenizer_id" not in data:
                continue
            record = TokenizerRecord(
                tokenizer_id=data["tokenizer_id"],
                kind=data["kind"],
                version=data["version"],
                config_json=data["config_json"],
                vocab_cid=data["vocab_cid"],
                modality_anchors=tuple(data.get("modality_anchors", [])),
                created_at=float(data["created_at"]),
            )
            if record.tokenizer_id not in self._records:
                self._records[record.tokenizer_id] = record

    def _ensure_defaults(self) -> None:
        """Seed the registry with the two canonical default analyzers."""
        if DEFAULT_WORD_REGEX_ID not in self._records:
            self.register(
                tokenizer_id=DEFAULT_WORD_REGEX_ID,
                kind="word_regex",
                version="v1",
                config=_default_word_regex_config(),
                vocab_cid="",
                modality_anchors=(),
            )
        if DEFAULT_AETHERIUS_ID not in self._records:
            self.register(
                tokenizer_id=DEFAULT_AETHERIUS_ID,
                kind="aetherius",
                version="v0",
                config=_default_aetherius_config(),
                vocab_cid="",
                modality_anchors=("[IMG]", "[TTY]", "[VOICE]", "[SENS]", "[ANE]", "[MEM]"),
            )

    def register(
        self,
        *,
        tokenizer_id: str,
        kind: str,
        version: str,
        config: str,
        vocab_cid: str,
        modality_anchors: tuple[str, ...] | list[str] = (),
    ) -> TokenizerRecord:
        """Register a tokenizer. Idempotent: existing id returns existing record."""
        if not tokenizer_id or ":" not in tokenizer_id:
            raise RegistryError("tokenizer_id must be non-empty and contain a colon delimiter")
        if tokenizer_id in self._records:
            return self._records[tokenizer_id]

        record = TokenizerRecord(
            tokenizer_id=tokenizer_id,
            kind=kind,
            version=version,
            config_json=config,
            vocab_cid=vocab_cid,
            modality_anchors=tuple(modality_anchors),
            created_at=time.time(),
        )
        self._records[tokenizer_id] = record
        self._append(record)
        return record

    def _append(self, record: TokenizerRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")

    def get(self, tokenizer_id: str) -> TokenizerRecord:
        """Fetch a tokenizer record by id."""
        if tokenizer_id not in self._records:
            raise RegistryError(f"tokenizer {tokenizer_id!r} not registered")
        return self._records[tokenizer_id]

    def has(self, tokenizer_id: str) -> bool:
        return tokenizer_id in self._records

    def list_tokenizers(self) -> list[TokenizerRecord]:
        """Return all registered tokenizers, sorted by id."""
        return [self._records[k] for k in sorted(self._records)]

    def default_word_regex_id(self) -> str:
        return DEFAULT_WORD_REGEX_ID

    def default_aetherius_id(self) -> str:
        return DEFAULT_AETHERIUS_ID
