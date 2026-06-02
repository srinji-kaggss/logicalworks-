"""
lgwks_math — algebraic signatures of every CLI verb.

The "quick math for AI": each verb is a typed function with pre-conditions,
post-conditions, state-delta, and cost model. An AI reading this JSON does not
need prose — it knows exactly what each command consumes, produces, and risks.

Design: formal but lightweight — not a full theorem prover, but enough to
prevent an agent from calling `project deploy` when it meant `project plan`.
"""

from __future__ import annotations

import json
from typing import Any

# ── algebraic signatures ───────────────────────────────────────────────────────
# Each entry is a mini-spec: domain (input types), codomain (output types),
# pre (what must hold), post (what will hold), side_effects (external mutations),
# cost (time/tokens/RAM), risk_class (read/mutate/destructive/network/token-spend),
# inverse (reversible operation, or None).

_VERB_ALGEBRA: dict[str, dict[str, Any]] = {
    "manifest": {
        "signature": "manifest : (render: Bool) → MachineContract",
        "domain": {"render": "Bool — human view instead of JSON"},
        "codomain": {"verbs": "List[VerbMeta]", "capabilities": "List[CapMeta]",
                     "steering": "DialSchema", "thought_schema": "Schema"},
        "pre": [],
        "post": ["contract reflects every verb registered in build_parser()",
                 "capabilities pulled live from resolver"],
        "side_effects": [],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "math": {
        "signature": "math : (verb: Maybe[str], render: Bool) → AlgebraContract",
        "domain": {"verb": "Maybe[str] — optional single-verb filter", "render": "Bool"},
        "codomain": {"signatures": "List[AlgebraEntry]"},
        "pre": [],
        "post": ["every verb in build_parser() has a signature entry",
                 "missing verbs emit loud '(no algebra)' placeholder"],
        "side_effects": [],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "solve": {
        "signature": "solve : (target: GitTarget, repo: Path, thought: String, frontier: 0..1, lens: -1..1, depth: 0..1) → ForensicsReport × CSLJSON",
        "domain": {"target": "GitTarget (currently only 'git')", "repo": "Path",
                   "thought": "String — worry/claim to prove",
                   "frontier": "0..1 settled→frontier", "lens": "-1..1 philosophy→science",
                   "depth": "0..1 shallow→deep"},
        "codomain": {"findings": "List[Finding]", "provenance": "CSL-JSON", "thought_packet": "Packet"},
        "pre": ["repo is a git repository", "target == 'git' (currently)"],
        "post": ["all claims carry source handle or 'unsupported' label",
                 "no narrative presented as source of truth"],
        "side_effects": ["filesystem: reads .git/ (read-only)"],
        "cost": {"time": "O(commit_count)", "tokens": "0 (deterministic); optional Tongue narration", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "extract": {
        "signature": "extract : (target: URL|Path, max_chars: Nat) → TextArtifact",
        "domain": {"target": "URL or local file path", "max_chars": "Nat — bound on returned text"},
        "codomain": {"source": "String", "kind": "String", "ok": "Bool", "text": "String"},
        "pre": ["target is http(s) URL or existing local path",
                 "blocked-host list rejects private/metadata endpoints"],
        "post": ["text is extracted, not executed", "ok=False when target missing or scheme unsupported"],
        "side_effects": ["network: HTTP GET if URL", "filesystem: read if local path"],
        "cost": {"time": "O(file_size)", "tokens": "0", "ram": "O(max_chars)"},
        "risk_class": "read",
        "inverse": None,
    },
    "convert": {
        "signature": "convert : (source: URL|Path, to: Format, out: Maybe[Path], max_chars: Nat) → Artifact",
        "domain": {"source": "URL or file", "to": "Format ∈ {text, md, json}", "out": "Maybe[Path]", "max_chars": "Nat"},
        "codomain": {"artifact": "String (stdout) or File (when --out)"},
        "pre": ["source readable (URL or local path)"],
        "post": ["format matches 'to' choice", "never executes source content"],
        "side_effects": ["network if URL", "filesystem write if --out"],
        "cost": {"time": "O(file_size)", "tokens": "0", "ram": "O(max_chars)"},
        "risk_class": "read",
        "inverse": None,
    },
    "x": {
        "signature": "x : (expr: GeoExpr, yes: Bool, force: Bool, allow_unknown: Bool, dry_run: Bool, keep_going: Bool) → Transcript",
        "domain": {"expr": "GeoExpr — product with {a,b,c} cartesian axes",
                   "yes": "Bool — non-interactive approve read-only chains",
                   "force": "Bool — allow destructive commands non-interactively",
                   "allow_unknown": "Bool — allow unknown commands after --yes",
                   "dry_run": "Bool — show plan, run nothing",
                   "keep_going": "Bool — continue after failure"},
        "codomain": {"commands": "List[CommandResult]", "plan_id": "SHA"},
        "pre": ["expr expands to a finite command set", "destructive commands require --force"],
        "post": ["each command executed via argv list (no shell)", "unknown commands blocked unless --allow-unknown",
                 "transcript persisted with embeddings"],
        "side_effects": ["filesystem: may mutate files when force=True", "network: none"],
        "cost": {"time": "O(command_count * command_time)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "mutate",
        "inverse": None,
    },
    "refine": {
        "signature": "refine : (intent: String, agent: Bool, depth: 0..1) → RefinedIntent",
        "domain": {"intent": "String — raw intent", "agent": "Bool — auto-inject quality keywords",
                   "depth": "0..1 — higher demands more specificity"},
        "codomain": {"intent_class": "String", "specificity": "0..1", "abstain": "Bool",
                     "gaps": "List[String]", "questions": "List[String]"},
        "pre": ["intent is non-empty"],
        "post": ["specificity computed", "abstain=True when intent too thin for depth threshold",
                 "intent_commit logged to cognition-log"],
        "side_effects": ["filesystem: append to store/cognition/ (intent_commit)"],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "store": {
        "signature": "store : () → StoreStatus",
        "domain": {},
        "codomain": {"stores": "List[StoreMeta] — cache, cognition, vault"},
        "pre": [],
        "post": ["status reflects actual on-disk state"],
        "side_effects": [],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "jarvis crawl": {
        "signature": "crawl : (source: Maybe[URL], keywords: List[String], max_pages: Nat, max_depth: Nat, workers: Nat) → RunManifest",
        "domain": {"source": "Maybe[URL]", "keywords": "List[String]",
                   "max_pages": "Nat", "max_depth": "Nat", "workers": "Nat",
                   "search_expansion": "Bool", "chunk_words": "Nat", "chunk_overlap": "Nat"},
        "codomain": {"run_id": "RunID", "db": "SQLite", "report": "Markdown", "graph": "Mermaid", "gnn": "CSV+JSONL"},
        "pre": ["source is valid URL or keywords non-empty", "max_pages >= 1", "workers >= 1"],
        "post": ["db contains sources, documents, chunks, nodes, edges, embeddings",
                 "run manifest written to disk", "deterministic embeddings computed"],
        "side_effects": ["network: HTTP GET to seeds and discovered links",
                         "filesystem: writes to RUN_ROOT/<run_id>/"],
        "cost": {"time": "O(max_pages * 8s / workers)", "tokens": "0", "ram": "O(max_pages * 100KB)"},
        "risk_class": "network",
        "inverse": None,
    },
    "jarvis remap-db": {
        "signature": "remap-db : (run_dir: Path) → RemappedDB",
        "domain": {"run_dir": "Path — existing run directory with legacy db"},
        "codomain": {"db": "SQLite — current schema version"},
        "pre": ["run_dir/db/research.sqlite exists"],
        "post": ["legacy tables migrated or renamed", "embeddings remapped to id-primary schema"],
        "side_effects": ["filesystem: modifies SQLite schema in place"],
        "cost": {"time": "O(chunks)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "mutate",
        "inverse": None,
    },
    "geo compile": {
        "signature": "compile : (expr: GeoExpr) → CommandPlan",
        "domain": {"expr": "GeoExpr JSON — product over typed axes"},
        "codomain": {"plan_id": "SHA", "commands": "List[TypedArgv]", "compile_policy": "Policy"},
        "pre": ["expr.schema == 'lgwks-geoexpr/1'", "expr.op == 'product'"],
        "post": ["plan_id is deterministic (sha of canonical JSON)", "argv is a list (never shell string)"],
        "side_effects": [],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "geo preview": {
        "signature": "preview : (plan: CommandPlan, risk_max: RiskClass) → HumanPreview",
        "domain": {"plan": "CommandPlan", "risk_max": "RiskClass ∈ {read, mutate, destructive}"},
        "codomain": {"approval": "auto_allowed | ask | blocked", "risk": "RiskClass", "steps": "List[Step]"},
        "pre": ["plan is a valid CommandPlan"],
        "post": ["approval is ask when any command risk > risk_max",
                 "unknown verbs are never approved automatically"],
        "side_effects": [],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "geo run": {
        "signature": "run : (expr: GeoExpr, yes: Bool, force: Bool) → HumanPreview × Transcript",
        "domain": {"expr": "GeoExpr", "yes": "Bool", "force": "Bool"},
        "codomain": {"preview": "HumanPreview", "results": "List[CommandResult]", "run_dir": "Path"},
        "pre": ["compile(plan) succeeds", "preview approval != blocked"],
        "post": ["destructive commands blocked unless force=True",
                 "unknown commands blocked unless allow_unknown",
                 "transcript + embeddings persisted"],
        "side_effects": ["filesystem: writes to store/geo-runs/", "network: none (argv only)"],
        "cost": {"time": "O(command_count)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "mutate",
        "inverse": None,
    },
    "memory init": {
        "signature": "init : (project: Name, site: Host, goal: String) → ChainHead",
        "domain": {"project": "Name", "site": "Host", "goal": "String"},
        "codomain": {"chain_head": "SHA", "scope": "Scope", "site": "Host", "goal": "String"},
        "pre": ["project is non-empty"],
        "post": ["chain head written to store/projects/<project>/memory.jsonl",
                 "HMAC chain starts with genesis event"],
        "side_effects": ["filesystem: creates store/projects/<project>/"],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "mutate",
        "inverse": None,
    },
    "memory remember": {
        "signature": "remember : (project: Name, text: String) → ChainHead",
        "domain": {"project": "Name", "text": "String"},
        "codomain": {"chain_head": "SHA", "themes": "List[Theme]"},
        "pre": ["project exists (init first)"],
        "post": ["text appended to memory.jsonl", "themes derived and embedded", "HMAC chain valid"],
        "side_effects": ["filesystem: appends to memory.jsonl"],
        "cost": {"time": "O(text_length)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "mutate",
        "inverse": None,
    },
    "memory context": {
        "signature": "context : (project: Name, query: String) → ContextBlock",
        "domain": {"project": "Name", "query": "String"},
        "codomain": {"scopes": "List[Scope]", "focus_themes": "List[Theme]", "chain_ok": "Bool"},
        "pre": ["project exists"],
        "post": ["focus themes ranked by cosine to query embedding",
                 "chain_ok indicates HMAC integrity"],
        "side_effects": [],
        "cost": {"time": "O(events)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "login": {
        "signature": "login : (target: URL) → SessionMeta",
        "domain": {"target": "URL — host login page"},
        "codomain": {"ok": "Bool", "path": "Path", "reason": "String"},
        "pre": ["target is https URL (bare domains auto-prefixed)"],
        "post": ["session saved host-scoped", "no credentials printed to stdout"],
        "side_effects": ["filesystem: writes to store/sessions/<host>.json", "network: browser navigation"],
        "cost": {"time": "O(human_login_time)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "network",
        "inverse": None,
    },
    "public": {
        "signature": "public : (query: String, source: Source, limit: Nat) → SourceRecords",
        "domain": {"query": "String", "source": "Source ∈ {all, openalex, crossref, openverse}", "limit": "Nat"},
        "codomain": {"records": "List[SourceRecord]", "policy": "String"},
        "pre": [],
        "post": ["every record carries license + license_url + basis",
                 "policy is 'open-license-only; verify per-item before redistribution'"],
        "side_effects": ["network: HTTP GET to chosen source APIs"],
        "cost": {"time": "O(limit * API_latency)", "tokens": "0", "ram": "O(limit * record_size)"},
        "risk_class": "network",
        "inverse": None,
    },
    "embed": {
        "signature": "embed : (path: Path, project: Name, keywords: List[String], cycles: Nat, max_cycles: Nat) → VaultMeta",
        "domain": {"path": "Path — local folder", "project": "Name", "keywords": "List[String]",
                   "cycles": "Nat (0 = until stable)", "max_cycles": "Nat"},
        "codomain": {"vault": "Path", "manifest": "Path", "records": "Nat", "subvaults": "Nat"},
        "pre": ["path exists and is a directory"],
        "post": ["root vault + per-folder subvaults created",
                 "deterministic embeddings for every file under max_files"],
        "side_effects": ["filesystem: writes to store/embeddings/<project>/"],
        "cost": {"time": "O(files * cycle_count)", "tokens": "0", "ram": "O(files * avg_file_size)"},
        "risk_class": "read",
        "inverse": None,
    },
    "project plan": {
        "signature": "plan : (project: Name, prompt: String, reasoning_cycles: Nat, embedding_rounds: Nat, max_workers: Nat) → Plan",
        "domain": {"project": "Name", "prompt": "String",
                   "reasoning_cycles": "Nat (default 5)", "embedding_rounds": "Nat (default 400)",
                   "max_workers": "Nat (hard-capped at role_count)"},
        "codomain": {"plan_id": "Slug", "budgets": "Budgets", "branch_workers": "List[Worker]",
                     "next_commands": "List[Command]"},
        "pre": ["project is non-empty", "max_workers <= computed_cap"],
        "post": ["plan.json written to store/project-plans/<plan_id>/",
                 "budgets include token + worker + cycle limits"],
        "side_effects": ["filesystem: writes plan.json"],
        "cost": {"time": "O(1)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
    "project deploy": {
        "signature": "deploy : (project: Name, prompt: String, dry_run: Bool, execute: Bool, effort: Effort) → DeployDAG",
        "domain": {"project": "Name", "prompt": "String", "dry_run": "Bool (default True)",
                   "execute": "Bool", "effort": "Effort ∈ {low, medium, high}"},
        "codomain": {"deploy_dag": "DeployDAG", "cycles": "List[Cycle]", "leases": "List[Lease]",
                     "machine_packets": "List[Packet]", "learning_records": "List[Record]",
                     "graph_edges": "List[Edge]", "model_state": "ModelState"},
        "pre": ["project is non-empty", "if execute=True then dry_run=False"],
        "post": ["all artifacts written to store/project-deploy/<project>/",
                 "cycle chain is hash-linked", "token ledger records estimated spend"],
        "side_effects": ["filesystem: writes 15+ artifact files",
                         "network: public_search + embed when execute=True",
                         "tokens: bounded by tokens_per_cycle * reasoning_cycles"],
        "cost": {"time": "O(reasoning_cycles * token_time)", "tokens": "bounded by --tokens-per-cycle", "ram": "O(1)"},
        "risk_class": "token-spend",
        "inverse": None,
    },
    "project review": {
        "signature": "review : (project: Name) → ReviewReport",
        "domain": {"project": "Name"},
        "codomain": {"chain_ok": "Bool", "token_spend": "Nat", "bias_counts": "Map[String,Nat]",
                     "unsupported_claims": "List[String]", "execution_status_counts": "Map[String,Nat]"},
        "pre": ["project deploy artifacts exist"],
        "post": ["chain integrity verified (hash-linked)", "unsupported claims listed",
                 "operator stance surfaced"],
        "side_effects": [],
        "cost": {"time": "O(artifacts)", "tokens": "0", "ram": "O(1)"},
        "risk_class": "read",
        "inverse": None,
    },
}


# ── public API ─────────────────────────────────────────────────────────────────

def _collect_verbs() -> list[str]:
    """Derive verb names from the live argparse tree (same approach as lgwks_manifest)."""
    import importlib.machinery
    import importlib.util
    import os
    import sys
    import argparse

    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(here, "lgwks")
    loader = importlib.machinery.SourceFileLoader("_lgwks_main_for_math", script_path)
    spec = importlib.util.spec_from_loader("_lgwks_main_for_math", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    loader.exec_module(mod)
    parser = mod.build_parser()

    def _find_subparsers_action(p):
        for a in p._actions:
            if isinstance(getattr(a, "choices", None), dict) and a.choices:
                return a
        return None

    def _walk(prefix, p):
        sub = _find_subparsers_action(p)
        if sub is None:
            return [(prefix, p)] if prefix else []
        out = []
        for name, child in sorted(sub.choices.items()):
            full = f"{prefix} {name}" if prefix else name
            out.extend(_walk(full, child))
        return out

    return [name for name, _ in _walk("", parser)]


def build_algebra(verb_filter: str | None = None) -> dict:
    """Assemble the algebraic contract. Every registered verb gets an entry."""
    live = _collect_verbs()
    entries = []
    for name in live:
        alg = _VERB_ALGEBRA.get(name)
        if alg is None:
            entries.append({"verb": name, "algebra": "(no algebra)", "signature": "(no algebra)",
                           "domain": {}, "codomain": {}, "pre": [], "post": [],
                           "side_effects": [], "cost": {}, "risk_class": "unknown", "inverse": None})
        else:
            entry = {"verb": name, **alg}
            entries.append(entry)
    if verb_filter:
        entries = [e for e in entries if e["verb"] == verb_filter]
    return {
        "schema": "lgwks.algebra.v0",
        "purpose": "algebraic signatures of every CLI verb — pre/post-conditions, state-delta, cost model",
        "machine_first": True,
        "count": len(entries),
        "entries": entries,
    }


def math_command(args) -> int:
    verb = getattr(args, "verb", None)
    alg = build_algebra(verb_filter=verb)
    if getattr(args, "render", False):
        return _render(alg)
    print(json.dumps(alg, indent=2, ensure_ascii=False))
    return 0


def _render(alg: dict) -> int:
    try:
        import lgwks_ui as ui
        on = ui.color_on()
    except Exception:
        on = False
        ui = None
    if not ui:
        print(json.dumps(alg, indent=2)); return 0
    for ln in ui.band("math", f"{alg['count']} verb signatures — pre·post·cost·risk", on=on):
        print(ln)
    for e in alg["entries"]:
        sig = e["signature"]
        risk = e["risk_class"]
        risk_color = ui.EMERALD if risk == "read" else ui.AMBER if risk in ("mutate", "network") else ui.RUST
        print(ui.spine(ui.fg(f"  {e['verb']:<14}", ui.EMERALD, on=on)
                       + ui.fg(sig, ui.CREAM_DIM, on=on)
                       + ui.fg(f"   [{risk}]", risk_color, on=on), on=on))
        for pre in e.get("pre", [])[:2]:
            print(ui.spine(ui.fg(f"      ∵ {pre}", ui.MUTED, on=on), on=on))
    return 0
