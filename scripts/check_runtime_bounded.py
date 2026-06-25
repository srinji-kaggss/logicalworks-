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
# network module/client — never on a bare `.get` (that is dict.get, not a sink). The
# verb vocabulary is canonical; the receiver gate is what kills the false positives.
_NET_VERB_ATTRS = bch._NET_VERB_ATTRS
# The seed network-module tops. A file's ACTUAL net roots are computed per-file from its
# imports (incl. aliases like `import requests as rq` / `from curl_cffi import requests as
# _curl`) so an aliased net import is not invisible (H4). os.popen/os.system are shell
# sinks too. The detector is binding-aware so an aliased `import subprocess as sp` cannot
# hide a child-process call (H1).
_NET_MODULE_TOPS = frozenset({"requests", "httpx", "aiohttp", "urllib3", "curl_cffi", "pycurl"})
_OS_SHELL_ATTRS = frozenset({"system", "popen"})


def _has_timeout(call: ast.Call) -> bool:
    """The call carries a REAL bound — a `timeout=` keyword whose value is not the
    explicit no-bound sentinel `None`. `timeout=None` blocks forever in both
    subprocess and requests, so counting it as bounded would be a one-keyword bypass
    of the whole gate (H3). A positive literal or any non-None expression counts."""
    for kw in call.keywords:
        if kw.arg == "timeout":
            v = kw.value
            if isinstance(v, ast.Constant) and v.value is None:
                return False  # timeout=None → explicitly unbounded
            return True
    return False


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


class _Bindings(ast.NodeVisitor):
    """Per-file binding pre-pass: resolves what names actually refer to the
    subprocess/os modules and to network modules/clients, so an ALIASED import
    (`import subprocess as sp`, `from subprocess import run`, `from curl_cffi import
    requests as _curl`, `s = requests.Session()`) cannot hide a hang-class call (H1/H4)."""

    def __init__(self) -> None:
        self.subprocess_mods: set[str] = {"subprocess"}   # names == the subprocess module
        self.os_mods: set[str] = {"os"}                   # names == the os module
        self.subprocess_funcs: set[str] = set()           # bare-name subprocess/os-shell calls
        self.net_roots: set[str] = set(_NET_MODULE_TOPS)  # names == a net module
        self.net_funcs: set[str] = set()                  # bare-name net calls (urlopen, get…)
        self.net_clients: set[str] = set()                # vars bound to a Session()/Client()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for a in node.names:
            top = a.name.split(".")[0]
            bound = a.asname or top
            if top == "subprocess":
                self.subprocess_mods.add(bound)
            elif top == "os":
                self.os_mods.add(bound)
            elif top in _NET_MODULE_TOPS:
                self.net_roots.add(bound)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        mod = node.module or ""
        top = mod.split(".")[0]
        for a in node.names:
            bound = a.asname or a.name
            if top == "subprocess" and a.name in _SUBPROCESS_ATTRS:
                self.subprocess_funcs.add(bound)
            elif top == "os" and a.name in _OS_SHELL_ATTRS:
                self.subprocess_funcs.add(bound)
            elif mod == "urllib.request" and a.name == "urlopen":
                self.net_funcs.add(bound)
            elif top in _NET_MODULE_TOPS:
                # `from curl_cffi import requests as _curl` → _curl is a net root;
                # `from requests import get` → get is a bare net call.
                if a.name in _NET_VERB_ATTRS:
                    self.net_funcs.add(bound)
                else:
                    self.net_roots.add(bound)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        v = node.value
        if isinstance(v, ast.Call):
            callee = _callee_name(v.func).lower()
            root = _root_name(v.func)
            if root in self.net_roots and (
                callee.endswith(".session") or callee.endswith(".client") or callee == root
            ):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self.net_clients.add(t.id)
        self.generic_visit(node)


class _SinkVisitor(ast.NodeVisitor):
    def __init__(self, b: _Bindings, speaks_urllib: bool) -> None:
        self.b = b
        self.speaks_urllib = speaks_urllib
        self.sinks: list[dict] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        kind = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
            root = _root_name(func.value)
            if attr in _SUBPROCESS_ATTRS and root in self.b.subprocess_mods:
                kind = "subprocess"          # subprocess.run / sp.Popen / … (alias-aware)
            elif attr in _OS_SHELL_ATTRS and root in self.b.os_mods:
                kind = "subprocess"          # os.system / os.popen — shell, no timeout API
            elif attr == "urlopen":
                kind = "network"
            elif attr == "open" and self.speaks_urllib and _is_opener_receiver(func.value):
                kind = "network"             # urllib opener.open, never Path/file.open
            elif attr in _NET_VERB_ATTRS and (root in self.b.net_roots or root in self.b.net_clients):
                kind = "network"             # requests.get / _curl.get / session.get
        elif isinstance(func, ast.Name):
            if func.id in self.b.subprocess_funcs:
                kind = "subprocess"          # bare run()/Popen()/popen() from a `from … import`
            elif func.id in self.b.net_funcs:
                kind = "network"             # bare urlopen()/get() from a `from … import`
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
    bindings = _Bindings()
    bindings.visit(tree)            # resolve aliases FIRST, then detect sinks
    v = _SinkVisitor(bindings, "urllib" in src)
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
    """Return (all_sinks, violations) — back-compat shape used by tests."""
    all_sinks, violations, _stale, _mism = evaluate_full()
    return all_sinks, violations


def evaluate_full() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Return (all_sinks, violations, stale_entries, count_mismatches).

    violation       — an unbounded sink whose (file,callee,target) is not inventoried.
    stale_entry     — an inventory entry matching zero current unbounded sinks.
    count_mismatch  — an inventory entry whose declared `lines` count != the number of
                      current unbounded sinks under its key. This is what stops the
                      coarse (file,callee,target) key from auto-pardoning a NEW sink
                      that happens to share the key (H2): one reviewed call site can no
                      longer launder every future sink with the same key.
    """
    inv = load_inventory()
    entries = inv.get("out_of_scope", [])
    by_key: dict[tuple, dict] = {(e["file"], e["callee"], e["target"]): e for e in entries}
    groups: dict[tuple, list[dict]] = {}
    all_sinks: list[dict] = []
    for f in runtime_files():
        for s in scan_file(f):
            all_sinks.append(s)
            if s["bounded"]:
                continue  # carries its own bound — fine
            groups.setdefault(_allow_key(s), []).append(s)

    violations: list[dict] = []
    count_mismatches: list[dict] = []
    for key, sinks in groups.items():
        entry = by_key.get(key)
        if entry is None:
            violations.extend(sinks)  # unbounded AND uninventoried
            continue
        expected = len(entry.get("lines", []))
        if len(sinks) != expected:
            count_mismatches.append({
                "file": key[0], "callee": key[1], "target": key[2],
                "expected": expected, "found": len(sinks),
                "lines": sorted(s["line"] for s in sinks),
            })
    stale = [e for e in entries
             if (e["file"], e["callee"], e["target"]) not in groups]
    return all_sinks, violations, stale, count_mismatches


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--verify"
    if mode == "--list":
        all_sinks, _ = evaluate()
        print(json.dumps({"sinks": all_sinks, "count": len(all_sinks)}, indent=2))
        return 0
    # --verify (the gate)
    try:
        all_sinks, violations, stale, mism = evaluate_full()
    except SyntaxError as exc:  # unparseable file → fail closed
        print(f"runtime.bounded: NO-GO — parse error: {exc}")
        return 1
    bounded = sum(1 for s in all_sinks if s["bounded"])
    if violations:
        print(f"runtime.bounded: NO-GO — {len(violations)} unbounded hang-class "
              f"sink(s) neither timed-out nor inventoried out-of-scope:")
        for v in violations:
            print(f"  {v['file']}:{v['line']}  {v['callee']}({v['target']})  [{v['kind']}]")
        print("Fix: add a real timeout=/route through _run_bounded, OR add an out_of_scope "
              "entry (with lines + reason) in spec/second-harness/runtime-bounded-inventory.json")
        return 1
    if mism:
        print(f"runtime.bounded: NO-GO — {len(mism)} inventory entr(y/ies) whose unbounded-sink "
              f"count drifted (a new sink shares an inventoried key, or one was removed — re-review):")
        for m in mism:
            print(f"  {m['file']}  {m['callee']}({m['target']})  expected {m['expected']}, "
                  f"found {m['found']} at lines {m['lines']}")
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
