"""
lgwks_cycle — project deploy cycle ledger.

The deploy loop's source of truth is not stdout. It is a typed, HMAC-chained
ledger that AI workers can replay and humans can audit.
"""

from __future__ import annotations

import lgwks_chain
import lgwks_hashing
import json
import time
from pathlib import Path

import lgwks_sign

GENESIS = lgwks_chain.GENESIS
from lgwks_substrate_config import SLUG_SCRUB_RE as SAFE  # one source of truth


def project_id(project: str) -> str:
    safe = SAFE.sub("-", project.strip().lower()).strip(".-") or "project"
    return f"{safe}-{lgwks_hashing.content_id(project, 12)}"


def canon(record: dict) -> str:
    return json.dumps({k: v for k, v in record.items() if k != "hash"},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cycle_hash(record: dict, key: bytes | None = None) -> str:
    key = key if key is not None else lgwks_sign.signing_key()[0]
    return lgwks_sign.mac(canon(record), key)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """Public JSONL writer. Delegates to the one source of truth."""
    from lgwks_substrate_io import _emit_jsonl
    _emit_jsonl(path, rows)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


# Map the canonical primitive's structured errors back to this store's taxonomy.
# (bad-link == prev mismatch, bad-record == seq mismatch — both were "bad-sequence".)
_ERR = {"": "", "bad-link": "bad-sequence", "bad-record": "bad-sequence",
        "bad-hash": "bad-hash", "read-error": "read-error"}


def _cycle_log(path: Path, key: bytes) -> "lgwks_chain.HashChainLog":
    """This ledger as the canonical hash-chain primitive — VERIFY ONLY.

    The cycle chain is batch-built by make_cycles and written by a full overwrite
    (write_jsonl), not incrementally appended, so this log injects no build_core/
    serialize. It shares only the link-walk invariant + this store's hash
    construction (mac(canon(row), key)) and its 1-based seq.
    """
    return lgwks_chain.HashChainLog(
        path,
        key=key,
        hash_core=lambda core, prev, k: cycle_hash(core, k),  # mac(canon(core), k)
        verify_record=lambda rec, index, prev: rec.get("seq") == index + 1,  # 1-based seq
    )


def verify_cycles(path: Path, key: bytes | None = None) -> dict:
    key = key if key is not None else lgwks_sign.signing_key()[0]
    s = _cycle_log(path, key).scan()
    return {"chain_ok": s["ok"], "cycles": s["count"], "chain_head": s["head"],
            "error": _ERR.get(s["error"], s["error"])}


def prompt_ref(prompt: str) -> str:
    return "prompt-sha256:" + lgwks_hashing.digest(prompt)


def deploy_dir(root: Path, project: str) -> Path:
    return root / project_id(project)


def seed_weight(seq: int) -> dict:
    return {
        "retrieval": round(0.34 + seq * 0.01, 3),
        "evidence_quality": 0.25,
        "contradiction": 0.16 if seq >= 2 else 0.12,
        "intent_mapping": 0.18,
        "slop_chain_recall": 0.10,
    }


def make_cycles(project: str, prompt: str, *, cycles: int, tokens_per_cycle: int,
                keywords: list[str], rollback_ref: str, key: bytes | None = None) -> list[dict]:
    key = key if key is not None else lgwks_sign.signing_key()[0]
    forms = [
        ("neutral_academic", "map mechanism and vocabulary"),
        ("disproof", "seek falsifiers and limits"),
        ("evidence_gap", "fill missing source handles"),
        ("graph_frontier", "connect intent evidence claim correction edges"),
        ("synthesis_packet", "emit compact AI-to-AI continuation packet"),
    ]
    rows: list[dict] = []
    prev = GENESIS
    for seq in range(1, max(1, cycles) + 1):
        form, purpose = forms[(seq - 1) % len(forms)]
        focus = " ".join(keywords[:8]) or prompt
        query = f"{focus} {purpose}"
        status = "planned"
        if form == "synthesis_packet":
            status = "unsupported"
        estimated = min(tokens_per_cycle, 900 + 180 * seq + len(query.split()) * 18)
        row = {
            "schema": "lgwks-cycle/1",
            "project": project,
            "seq": seq,
            "prev": prev,
            "intent": prompt_ref(prompt),
            "intent_view": {
                "mode": "hash_ref",
                "note": "raw prompt remains local/user-owned; cycle carries only derived intent features",
            },
            "query_form": form,
            "query": query,
            "token_budget": tokens_per_cycle,
            "estimated_tokens": estimated,
            "token_status": "ok" if estimated <= tokens_per_cycle else "over",
            "evidence_attention": [
                {"source": "openalex", "id": "planned:openalex", "why": purpose, "score": round(0.55 + seq * 0.03, 3)}
            ],
            "bias_flags": [
                {"plane": "prompt_bias", "kind": "thesis_lock", "severity": "m" if form == "disproof" else "l"},
                {"plane": "ai_bias", "kind": "confident_completion_pressure", "severity": "m"},
            ],
            "next_commands": [
                {"argv": ["lgwks", "public", query, "--source", "all", "--limit", "10"],
                 "reason": purpose, "budget": 10}
            ],
            "eval_result": {"status": status, "score": 0.0 if status == "unsupported" else round(0.35 + seq * 0.05, 3)},
            "weight": seed_weight(seq),
            "rollback_ref": rollback_ref,
            "created_at": time.time(),
        }
        row["hash"] = cycle_hash(row, key)
        rows.append(row)
        prev = row["hash"]
    return rows
