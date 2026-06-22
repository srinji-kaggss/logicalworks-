"""lgwks_cortex — the Transcript Cortex (PRD-06 U5).

Tails agent JSONL transcripts and converts them into per-turn records for the
Subconscious Engine. This is the sensory organ that allows the daemon to
detect "lies," intent drift, and unresolved commitments.

Contract: emits `lgwks.cortex.v1`
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lgwks_hashing
import lgwks_transcript
from lgwks_clock import now_iso as _now

@dataclass
class CortexTurn:
    turn_id: str
    session_id: str
    role: str
    intent_class: str = "unknown"
    phase: str = "observation"
    entities: list[str] = field(default_factory=list)
    attention: list[str] = field(default_factory=list)
    content: str = ""
    ts: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "role": self.role,
            "intent_class": self.intent_class,
            "phase": self.phase,
            "entities": self.entities,
            "attention": self.attention,
            "ts": self.ts,
        }

class TranscriptCortex:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.cortex_dir = repo_root / "store" / "cortex"
        self.cortex_dir.mkdir(parents=True, exist_ok=True)
        # Observability counters (defect: a pipeline whose PRODUCT is the data
        # must never drop a trajectory silently). Reset per process_transcript
        # call so a caller/daemon tick can read the loss for the work it did.
        self.emit_ok = 0
        self.emit_failures = 0
        self.tokenize_failures = 0

    def _drop_log(self, event: str, ct: "CortexTurn", err: Exception) -> None:
        """Emit a structured loss record to stderr. Capture stays best-effort
        (never raises into the daemon loop), but a drop is now COUNTED + VISIBLE
        instead of swallowed — silent training-data loss was the defect."""
        try:
            print(
                json.dumps({
                    "schema": "lgwks.cortex.drop.v1",
                    "event": event,
                    "session_id": ct.session_id,
                    "turn_id": ct.turn_id,
                    "error": f"{type(err).__name__}: {err}",
                }),
                file=sys.stderr,
            )
        except Exception:
            pass  # logging the drop must itself never break capture

    def process_transcript(
        self,
        transcript_path: Path,
        session_id: str,
        n: int = 0,
        gate: Any = None,
        limit: int = 0,
    ) -> list[CortexTurn]:
        """Convert a raw JSONL transcript into a sequence of CortexTurns.

        Each turn is ANT-tokenized and emitted as a tokenized artifact onto the
        State Fabric (Causal Tape + TokenIndex) — the durable, replayable training
        trajectory. n=0 processes the whole file. A caller may pass its own `gate`
        (it owns the lifecycle); otherwise a per-session gate is opened/closed here.

        `limit > 0` bounds the number of NEW (not-yet-persisted) turns processed
        in one call so the daemon loop stays responsive on a long backlog (#247);
        idempotency (#239) makes the remainder drain safely across later calls.
        `len(returned) == limit` signals the backlog may not be fully drained.
        """
        # Layer 1: Entry Point Validation
        self.emit_ok = self.emit_failures = self.tokenize_failures = 0
        if not transcript_path.exists():
            return []

        # PRD-06: "deterministic extraction first, BERT salience when 05 lands"
        import lgwks_intent_classifier as ic
        import lgwks_tokenizer as atok

        clf = ic.IntentClassifier.load()
        tokenizer = atok.AetheriusTokenizer(self.repo_root)

        own_gate = gate is None
        if own_gate:
            import lgwks_storage
            gate = lgwks_storage.get_gate("cortex", tenant_id=session_id)

        processed: list[CortexTurn] = []
        # Idempotency: a turn already persisted for this session is never
        # re-emitted. This is what makes repeated/autonomous polling of a
        # growing transcript safe — without it the daemon loop would duplicate
        # trajectory turns and corrupt the training corpus.
        seen = self._persisted_turn_ids(session_id)
        try:
            raw_turns = lgwks_transcript.tail(transcript_path, n=n, include_content=True)

            for turn in raw_turns:
                if turn["turn_id"] in seen:
                    continue
                content = turn.get("content", "")

                # Layer 2: Business Logic (ModernBERT Salience)
                entities = self._extract_entities(content)
                res = clf.classify(content)

                ct = CortexTurn(
                    turn_id=turn["turn_id"],
                    session_id=session_id,
                    role=turn["role"],
                    intent_class=res.label,
                    entities=entities,
                    attention=entities[:3],  # Simple attention baseline
                    content=content,
                )

                # Layer 3: Neural Tokenization (Aetherius Neural Tokenizer).
                # Tokenize the full turn (content + entities + modality anchors) —
                # not the metadata-only to_dict() that previously dropped content.
                tokens: tuple[int, ...] = ()
                try:
                    traj = tokenizer.tokenize_trajectory({
                        "content": content,
                        "entities": entities,
                        "image_hash": turn.get("image_hash", ""),
                        "tty_hash": turn.get("tty_hash", ""),
                    })
                    tokens = tuple(traj.tokens)
                    ct.attention.extend([f"atok:{t}" for t in tokens[:5]])
                except Exception as err:
                    # Empty token stream = a degraded trajectory; the artifact is
                    # still emitted (its metadata/text survive) but the token
                    # payload is lost. Count + log it rather than degrade silently.
                    tokens = ()
                    self.tokenize_failures += 1
                    self._drop_log("tokenize_failed", ct, err)

                # Layer 4: persist. The durable, replayable training trajectory
                # goes on the Causal Tape (+ TokenIndex); the JSONL is a mirror.
                self._emit_trajectory(gate, ct, content, tokens)
                self._persist_turn(ct)
                seen.add(ct.turn_id)
                processed.append(ct)

                # #247: bound NEW turns per call so a long backlog drains across
                # several daemon ticks instead of blocking the loop (and SIGTERM)
                # in one synchronous pass. Idempotency carries the remainder.
                if limit > 0 and len(processed) >= limit:
                    break
        finally:
            if own_gate:
                gate.close()

        return processed

    def _emit_trajectory(self, gate: Any, ct: CortexTurn, content: str, tokens: tuple[int, ...]) -> None:
        """Append one turn to the State Fabric as a tokenized reasoning artifact.

        Best-effort: trajectory capture must never break transcript processing
        (the gate isolates projection failures; we only guard the tape append).
        A failure is COUNTED + logged (self.emit_failures / stderr), never
        swallowed — silent drop = invisible training-data loss.
        """
        import time

        import lgwks_artifact_tokenized as artifact_mod

        try:
            payload_cid = lgwks_hashing.content_id(content or ct.turn_id)
            artifact = artifact_mod.build_artifact(
                tenant_id=ct.session_id,
                source="daemon_event",
                modality="reasoning",
                tokenization_id=gate.tokenizers.default_aetherius_id(),
                token_stream=tokens,
                payload_cid=payload_cid,
                payload_meta={
                    "turn_id": ct.turn_id,
                    "role": ct.role,
                    "intent_class": ct.intent_class,
                    "phase": ct.phase,
                    "entities": ct.entities,
                    "ts": ct.ts,
                    "text": content[:2000],
                },
                capability_id="cap:cortex",
                timestamp=time.time(),
            )
            gate.ingest_artifact(artifact)
            self.emit_ok += 1
        except Exception as err:
            self.emit_failures += 1
            self._drop_log("trajectory_emit_failed", ct, err)

    def _persisted_turn_ids(self, session_id: str) -> set[str]:
        """turn_ids already written to this session's cortex trajectory file.

        Read once per process_transcript call; the cortex .cortex.jsonl is a flat
        append log with no native dedup, so this set is the idempotency key for
        re-runs (CLI re-invocation, daemon polling a growing transcript)."""
        path = self.cortex_dir / f"{session_id}.cortex.jsonl"
        if not path.exists():
            return set()
        seen: set[str] = set()
        try:
            with path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        seen.add(json.loads(line)["turn_id"])
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError:
            return seen
        return seen

    def _extract_entities(self, text: str) -> list[str]:
        """Find repo entities (files, modules) mentioned in text."""
        # Simple regex-based extraction for now
        import re
        # Match potential file paths or module names
        matches = re.findall(r'\b[a-zA-Z0-9_\-/]+\.(?:py|rs|js|ts|md|json)\b', text)
        return sorted(list(set(matches)))

    def _classify_intent(self, text: str) -> str:
        """Heuristic intent classification."""
        text_lower = text.lower()
        if "research" in text_lower or "find" in text_lower:
            return "research_orchestration"
        if "test" in text_lower or "pytest" in text_lower:
            return "quality_assurance"
        if "fix" in text_lower or "refactor" in text_lower:
            return "code_mutation"
        return "unknown"

    def _persist_turn(self, turn: CortexTurn):
        """Save the turn to the local cortex store (JSONL)."""
        path = self.cortex_dir / f"{turn.session_id}.cortex.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(turn.to_dict()) + "\n")

def index_command(args) -> int:
    """CLI entrypoint for indexing."""
    from pathlib import Path
    cortex = TranscriptCortex(Path(args.repo))
    turns = cortex.process_transcript(Path(args.path), args.session_id, n=getattr(args, "n", 0))
    count = len(turns) if turns is not None else 0
    if getattr(args, "json", False):
        import json as _json
        print(_json.dumps({"schema": "lgwks.cortex.index.v1", "ok": True,
                           "session_id": args.session_id, "turns": count,
                           "emit_ok": cortex.emit_ok,
                           "emit_failures": cortex.emit_failures,
                           "tokenize_failures": cortex.tokenize_failures,
                           "transcript": str(args.path)}))
    else:
        drops = cortex.emit_failures + cortex.tokenize_failures
        note = f" ({drops} dropped — see stderr)" if drops else ""
        print(f"cortex: indexed {count} turn(s) from {args.path} -> {args.session_id}.cortex.jsonl{note}")
    return 0


def add_parser(sub) -> None:
    """Register `state cortex index` — tail a transcript into per-turn cortex
    trajectory records (PRD-06 U5). Previously orphaned: index_command existed
    with no CLI parser, so the transcript->trajectory step was unreachable."""
    p = sub.add_parser("cortex", help="transcript cortex — index a JSONL transcript into trajectory records (PRD-06)")
    cp = p.add_subparsers(dest="cortex_cmd", required=True)
    idx = cp.add_parser("index", help="tail a transcript into {session}.cortex.jsonl trajectory records")
    idx.add_argument("path", help="path to the JSONL transcript to index")
    idx.add_argument("--session-id", required=True, help="session id (names the .cortex.jsonl output)")
    idx.add_argument("--repo", default=".", help="repo root (cortex store lives under <repo>/store/cortex)")
    idx.add_argument("-n", type=int, default=0, help="last N turns (0 = whole transcript)")
    idx.add_argument("--json", action="store_true", help="machine-readable result")
    idx.set_defaults(func=index_command)
