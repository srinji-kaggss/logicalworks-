#!/usr/bin/env python3
"""check_runtime_bounded — the `runtime.bounded` Keel lane (R2 of the Pristine Program).

A no-model CI is CORRECT but BLIND to whether a model / network / subprocess call is
*bounded*: a call that hangs in real use ships green (exactly how the `review` hang
reached production while the suite stayed green — #319/#320). This lane makes
boundedness a GATED INVARIANT instead of a per-hang whack-a-mole habit.

THE INVARIANT. Every hang-class external call in the load-bearing runtime
(`lgwks_*.py`) is either:
  • BOUNDED — the call carries an explicit `timeout=` (or routes through the
    canonical `_run_bounded` wrapper, recognised below), OR
  • OUT OF SCOPE — a fast LOCAL call that cannot hang on the network (local
    `git` / `node` / `cargo` / a local python subprocess), EXPLICITLY listed in
    the inventory with a one-line reason — no silent omissions.
Any unbounded sink that is NOT on the out-of-scope inventory FAILS the lane: a
newly introduced unbounded model/network sink cannot ship. This is the structural
fix for the #320 disease class.

CANONICAL SINK VOCABULARY. What counts as a sink is NOT re-defined here — it is
imported from `lgwks_bot_code_hacker` (the repo's one static-analysis surface
detector). One definition, no parallel copy to drift.

NO MODELS. NO INTERNET. Pure AST. Fail closed on a parse error (a file we cannot
parse is an unproven file → NO-GO, never a silent pass).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

# One canonical definition of "what is a sink" — reused, never re-stated (CLAUDE.md:
# one canonical implementation). bot_code_hacker is the repo's AST surface detector.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lgwks_bot_code_hacker as bch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "spec" / "second-harness" / "runtime-bounded-inventory.json"

_SUBPROCESS_ATTRS = bch._SUBPROCESS_ATTRS          # run / Popen / call / check_*
# Network VERB attrs (get/post/...) are matched ONLY when the receiver root is a real
# network module — never on a bare `.get` (that is dict.get, not a sink). The verb
# vocabulary is the canonical one; the receiver gate is what kills the false positives.
_NET_VERB_ATTRS = bch._NET_VERB_ATTRS
# Roots that mean "this is a network client", so `<root>.get(...)` is a real sink.
# urllib is handled via urlopen / opener.open below, not as a verb root.
_NET_ROOTS = frozenset({"requests", "httpx", "aiohttp", "urllib3", "curl_cffi", "pycurl"})


def _has_timeout(call: ast.Call) -> bool:
    """The call carries its own bound — an explicit `timeout=` keyword."""
    return any(kw.arg == "timeout" for kw in call.keywords)


def _callee_name(func: ast.AST) -> str:
    """Dotted name of a call target, best-effort: subprocess.run, requests.get, x.urlopen."""
    parts: list[str] = []
    node: ast.AST = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _root_name(node: ast.AST) -> str:
    """Leftmost identifier of a dotted/call chain (the receiver root)."""
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return node.id if isinstance(node, ast.Name) else ""


def _is_opener_receiver(node: ast.AST) -> bool:
    """True when `<node>.open(...)` is a urllib opener read, not a file/Path .open().

    Matches the three real shapes: `opener.open`, `build_opener(...).open`,
    `_opener().open`. Anything else (Path.open, file.open) is NOT a network sink.
    """
    if isinstance(node, ast.Name):
        return "opener" in node.id.lower()
    if isinstance(node, ast.Call):
        name = _callee_name(node.func).lower()
        return "opener" in name
    return False


def _argv0(call: ast.Call) -> str:
    """Best-effort literal of the first positional arg (argv[0] / url), else 'dynamic'."""
    if not call.args:
        return "dynamic"
    a = call.args[0]
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return a.value
    if isinstance(a, (ast.List, ast.Tuple)) and a.elts:
        e = a.elts[0]
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            return e.value
    return "dynamic"


class _SinkVisitor(ast.NodeVisitor):
    def __init__(self, speaks_urllib: bool) -> None:
        self.speaks_urllib = speaks_urllib
        self.sinks: list[dict] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        kind = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
            if attr in _SUBPROCESS_ATTRS:
                # subprocess.run / subprocess.Popen / proc.communicate-style receivers.
                recv = _callee_name(func.value)
                if recv == "subprocess" or recv.endswith(".subprocess"):
                    kind = "subprocess"
            elif attr == "system" and _callee_name(func).endswith("os.system"):
                kind = "subprocess"
            elif attr == "urlopen":
                kind = "network"
            elif attr == "open" and self.speaks_urllib and _is_opener_receiver(func.value):
                # `opener.open(req, ...)` — a urllib opener read, never Path/file.open.
                kind = "network"
            elif attr in _NET_VERB_ATTRS and _root_name(func.value) in _NET_ROOTS:
                # requests.get / httpx.post / curl_cffi... — receiver-rooted only, so a
                # bare dict.get / obj.get is never mistaken for a network call.
                kind = "network"
        if kind is not None:
            self.sinks.append({
                "callee": _callee_name(func),
                "kind": kind,
                "line": node.lineno,
                "target": _argv0(node),
                "bounded": _has_timeout(node),
            })
        self.generic_visit(node)


def scan_file(path: Path) -> list[dict]:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src, filename=str(path))  # SyntaxError → propagates → NO-GO
    speaks_urllib = "urllib" in src
    v = _SinkVisitor(speaks_urllib)
    v.visit(tree)
    for s in v.sinks:
        s["file"] = path.name
    return v.sinks


def runtime_files() -> list[Path]:
    """The load-bearing root runtime modules (CLAUDE.md structural invariant)."""
    return sorted(ROOT.glob("lgwks_*.py"))


def load_inventory() -> dict:
    if not INVENTORY_PATH.exists():
        return {"out_of_scope": []}
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _allow_key(s: dict) -> tuple:
    return (s["file"], s["callee"], s["target"])


def evaluate() -> tuple[list[dict], list[dict]]:
    """Return (all_sinks, violations). A violation is an unbounded sink that is
    not on the out-of-scope inventory."""
    all_sinks, violations, _stale = evaluate_full()
    return all_sinks, violations


def evaluate_full() -> tuple[list[dict], list[dict], list[dict]]:
    """Return (all_sinks, violations, stale_entries).

    violation     — an unbounded sink that is neither timed-out nor inventoried.
    stale_entry   — an inventory out_of_scope entry that matches zero current
                    unbounded sinks (the inventory rotted; force a re-review).
    """
    inv = load_inventory()
    entries = inv.get("out_of_scope", [])
    allow = {(e["file"], e["callee"], e["target"]) for e in entries}
    matched: set[tuple] = set()
    all_sinks: list[dict] = []
    violations: list[dict] = []
    for f in runtime_files():
        for s in scan_file(f):
            all_sinks.append(s)
            if s["bounded"]:
                continue  # carries its own bound — fine
            key = _allow_key(s)
            if key in allow:
                matched.add(key)
                continue  # listed out-of-scope (local, cannot hang on the network)
            violations.append(s)
    stale = [e for e in entries
             if (e["file"], e["callee"], e["target"]) not in matched]
    return all_sinks, violations, stale


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--verify"
    if mode == "--list":
        all_sinks, _ = evaluate()
        print(json.dumps({"sinks": all_sinks, "count": len(all_sinks)}, indent=2))
        return 0
    # --verify (the gate)
    try:
        all_sinks, violations, stale = evaluate_full()
    except SyntaxError as exc:  # unparseable file → fail closed
        print(f"runtime.bounded: NO-GO — parse error: {exc}")
        return 1
    bounded = sum(1 for s in all_sinks if s["bounded"])
    if violations:
        print(f"runtime.bounded: NO-GO — {len(violations)} unbounded hang-class "
              f"sink(s) neither timed-out nor inventoried out-of-scope:")
        for v in violations:
            print(f"  {v['file']}:{v['line']}  {v['callee']}({v['target']})  [{v['kind']}]")
        print("Fix: add timeout=/route through _run_bounded, OR add an out_of_scope "
              "entry with a reason in spec/second-harness/runtime-bounded-inventory.json")
        return 1
    if stale:
        print(f"runtime.bounded: NO-GO — {len(stale)} stale inventory entr(y/ies) "
              f"matching no current unbounded sink (the inventory rotted — remove or fix):")
        for e in stale:
            print(f"  {e['file']}  {e['callee']}({e['target']})")
        return 1
    oos = len(all_sinks) - bounded
    print(f"runtime.bounded: GO — {len(all_sinks)} hang-class sinks "
          f"({bounded} bounded, {oos} inventoried out-of-scope); no unbounded sink escapes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
