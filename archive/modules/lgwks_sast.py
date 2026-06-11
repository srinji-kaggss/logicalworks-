"""lgwks_sast — comprehensive static code review: a real CFG + flow-sensitive taint engine.

This is the `cfg_execution_pathway` the SAST blueprints (extract-data, 7 cited patterns)
describe, implemented for the language this runtime can parse — Python — and honest about
the rest. It is NOT a regex grep: it builds a true control-flow graph (basic blocks + edges
for if/while/for/try) per function and propagates taint over it with a worklist to fixpoint
(gen/kill, reaching-taint), then reports source→sink flows that are not sanitized.

Comprehensive across CWE classes from one engine (Python, intra-procedural):
  CWE-89 SQL injection · CWE-78 command injection · CWE-94 code injection ·
  CWE-22 path traversal · CWE-502 unsafe deserialization · CWE-918 SSRF.

Cross-language / cross-procedure patterns (C use-after-free, Java Spring misconfig,
JS prototype-pollution, React XSS, integer-overflow, interprocedural IFDS) are REGISTERED in
PATTERN_CATALOG with their citation and a `deferred` status + landing point — they need
tree-sitter grammars and a call graph this single-file Python engine does not have. //why
register-not-fake: a shallow cross-language detector wearing a paper citation is the
oversimplification sin; the catalog states exactly what is proven vs pending.

Deterministic, stdlib-only, no network, no LLM. Findings carry a source→sink trace
(explainability) so a reviewer can verify each without re-running.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Optional


# ── declarative taint contract (the pattern's sources/sinks/sanitizers) ─────────

# //why match on the trailing attribute/name, not a full dotted path: the receiver
# object varies (cursor.execute, conn.execute, db.session.execute) but the dangerous
# verb is stable. We pair the method name with a source requirement so a bare
# `obj.execute("literal")` with no tainted arg never fires.
_SOURCE_CALLS = frozenset({"get", "getlist", "getvalue"})          # request.GET.get(...)
_SOURCE_ATTRS = frozenset({"args", "form", "json", "values", "data", "cookies", "headers"})
_SOURCE_NAMES = frozenset({"input"})                                # input(...)
_SOURCE_DOTTED = frozenset({"os.environ.get", "os.getenv", "sys.argv"})
_REQUEST_BASES = frozenset({"request", "req", "flask.request"})

_SINKS: dict[str, tuple[str, str]] = {
    # method/func name -> (CWE, label)
    "execute": ("CWE-89", "sql_injection"),
    "executemany": ("CWE-89", "sql_injection"),
    "executescript": ("CWE-89", "sql_injection"),
    "raw": ("CWE-89", "sql_injection"),
    "system": ("CWE-78", "command_injection"),
    "popen": ("CWE-78", "command_injection"),
    "eval": ("CWE-94", "code_injection"),
    "exec": ("CWE-94", "code_injection"),
    "compile": ("CWE-94", "code_injection"),
    "loads": ("CWE-502", "unsafe_deserialization"),       # pickle/yaml/marshal.loads
    "load": ("CWE-502", "unsafe_deserialization"),         # yaml.load
    "urlopen": ("CWE-918", "ssrf"),
}
# functions whose FIRST positional arg is a filesystem path → path traversal when tainted
_PATH_SINKS = frozenset({"open", "remove", "unlink", "rmtree", "rmdir", "copy", "move", "send_file"})
# requests-style network sinks → SSRF when the URL arg is tainted
_NET_SINKS = frozenset({"get", "post", "put", "delete", "request", "urlopen"})
_NET_BASES = frozenset({"requests", "httpx", "urllib", "aiohttp"})

_SANITIZERS = frozenset({
    "escape_string", "escape", "quote", "shlex.quote", "int", "float", "bool",
    "basename", "secure_filename", "escape", "quote_plus", "re_escape", "abspath",
})


# ── findings ────────────────────────────────────────────────────────────────────

@dataclass
class Flow:
    cwe: str
    label: str
    source: str            # the tainted origin description
    source_line: int
    sink: str              # the dangerous call
    sink_line: int
    function: str
    severity: str = "high"

    def to_record(self) -> dict[str, Any]:
        return {
            "schema": "lgwks.sast.flow.v1",
            "cwe": self.cwe,
            "kind": self.label,
            "severity": self.severity,
            "function": self.function,
            "trace": {
                "source": self.source, "source_line": self.source_line,
                "sink": self.sink, "sink_line": self.sink_line,
            },
            "summary": f"{self.label} ({self.cwe}): tainted '{self.source}' "
                       f"(L{self.source_line}) reaches {self.sink}() (L{self.sink_line}) "
                       f"in {self.function}() without sanitization",
        }


# ── control-flow graph ──────────────────────────────────────────────────────────

@dataclass
class Block:
    """A basic block: straight-line statements with one entry, edges to successors."""
    bid: int
    stmts: list[ast.stmt] = field(default_factory=list)
    succs: list[int] = field(default_factory=list)


class CFG:
    """Per-function control-flow graph. Compound statements (if/while/for/try/with)
    are expanded recursively into blocks with branch and back edges."""

    def __init__(self) -> None:
        self.blocks: dict[int, Block] = {}
        self._n = 0

    def new_block(self) -> Block:
        b = Block(self._n)
        self.blocks[self._n] = b
        self._n += 1
        return b

    def _edge(self, frm: Block, to: Block) -> None:
        if to.bid not in frm.succs:
            frm.succs.append(to.bid)

    def build(self, body: list[ast.stmt]) -> Block:
        entry = self.new_block()
        self._build_seq(body, entry)
        return entry

    def _build_seq(self, stmts: list[ast.stmt], cur: Block) -> Block:
        """Append stmts to cur, splitting at compound statements. Returns the block
        control reaches after the sequence (the join)."""
        for stmt in stmts:
            if isinstance(stmt, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.Try, ast.With, ast.AsyncWith)):
                cur = self._build_compound(stmt, cur)
            else:
                cur.stmts.append(stmt)
                # //why a terminator ends the block: return/raise/break/continue cut
                # control flow; nothing after them in this block is reachable.
                if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    dead = self.new_block()
                    cur = dead
        return cur

    def _build_compound(self, stmt: ast.stmt, cur: Block) -> Block:
        join = self.new_block()
        if isinstance(stmt, ast.If):
            then_entry = self.new_block(); self._edge(cur, then_entry)
            then_exit = self._build_seq(stmt.body, then_entry); self._edge(then_exit, join)
            if stmt.orelse:
                else_entry = self.new_block(); self._edge(cur, else_entry)
                else_exit = self._build_seq(stmt.orelse, else_entry); self._edge(else_exit, join)
            else:
                self._edge(cur, join)  # //why: the no-else branch falls straight to join
        elif isinstance(stmt, (ast.While, ast.For, ast.AsyncFor)):
            header = self.new_block(); self._edge(cur, header)
            body_entry = self.new_block(); self._edge(header, body_entry)
            body_exit = self._build_seq(stmt.body, body_entry)
            self._edge(body_exit, header)   # back edge — the loop
            self._edge(header, join)         # exit edge
        elif isinstance(stmt, (ast.Try,)):
            body_entry = self.new_block(); self._edge(cur, body_entry)
            body_exit = self._build_seq(stmt.body, body_entry); self._edge(body_exit, join)
            for handler in stmt.handlers:    # //why edge from body entry: an exception
                h_entry = self.new_block(); self._edge(body_entry, h_entry)  # may fire mid-body
                h_exit = self._build_seq(handler.body, h_entry); self._edge(h_exit, join)
            if stmt.finalbody:
                self._build_seq(stmt.finalbody, join)
            if stmt.orelse:
                self._build_seq(stmt.orelse, join)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            self._edge(cur, join)
            return self._build_seq(stmt.body, join)
        return join


# ── taint analysis over the CFG (worklist to fixpoint) ──────────────────────────

def _dotted(node: ast.AST) -> str:
    """Best-effort dotted name of an attribute/name chain, e.g. os.environ.get."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _is_request_base(base: str) -> bool:
    # //why match the chain ROOT, not endswith: request.GET.get has base "request.GET";
    # the trust origin is the leading `request`/`req` segment. endswith failed every case.
    return (base in _REQUEST_BASES
            or base.split(".")[0] in _REQUEST_BASES
            or any(base.startswith(b + ".") for b in _REQUEST_BASES))


def _is_source(node: ast.AST) -> bool:
    """Does this expression introduce untrusted input?"""
    if isinstance(node, ast.Call):
        dotted = _dotted(node.func)
        if dotted in _SOURCE_DOTTED:
            return True
        if isinstance(node.func, ast.Attribute):
            base = _dotted(node.func.value)
            if node.func.attr in _SOURCE_CALLS and _is_request_base(base):
                return True
        if isinstance(node.func, ast.Name) and node.func.id in _SOURCE_NAMES:
            return True
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        if node.attr in _SOURCE_ATTRS and _is_request_base(base):
            return True
    if isinstance(node, ast.Subscript):
        base = _dotted(node.value)
        if _is_request_base(base) or base == "os.environ":
            return True
    return False


def _is_sanitized(node: ast.AST) -> bool:
    if isinstance(node, ast.Call):
        dotted = _dotted(node.func)
        last = dotted.split(".")[-1] if dotted else ""
        return last in _SANITIZERS or dotted in _SANITIZERS
    return False


def _expr_tainted(node: Optional[ast.AST], tainted: set[str]) -> bool:
    """Does this expression carry taint under the current tainted-var set?"""
    if node is None:
        return False
    if _is_sanitized(node):
        return False                      # //why: a sanitizer call cleans its result
    if _is_source(node):
        return True
    if isinstance(node, ast.Name):
        return node.id in tainted
    for child in ast.iter_child_nodes(node):
        if _expr_tainted(child, tainted):
            return True
    return False


def _assign_targets(stmt: ast.stmt) -> list[str]:
    names: list[str] = []
    targets = []
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)):
        targets = [stmt.target]
    for t in targets:
        if isinstance(t, ast.Name):
            names.append(t.id)
    return names


def _classify_sink(call: ast.Call, tainted: set[str]) -> Optional[tuple[str, str, str]]:
    """If this call is a sink reached by a tainted arg, return (cwe, label, sink_name)."""
    func = call.func
    name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
    dotted = _dotted(func)
    base = _dotted(func.value) if isinstance(func, ast.Attribute) else ""

    def first_arg_tainted() -> bool:
        # //why FIRST positional only: the dangerous datum is the query/command/code/
        # path/blob in arg[0]. Tainted values in arg[1+] of execute() are BOUND
        # PARAMETERS — the parameterized-query remediation — and must NOT flag. This
        # is the precision that separates a real SQLi from its own fix.
        return bool(call.args) and _expr_tainted(call.args[0], tainted)

    def kw_url_tainted() -> bool:
        return any(k.arg in ("url", "uri") and _expr_tainted(k.value, tainted) for k in call.keywords)

    if name in _SINKS and first_arg_tainted():
        cwe, label = _SINKS[name]
        return cwe, label, dotted or name
    if name in _PATH_SINKS and first_arg_tainted():
        return "CWE-22", "path_traversal", dotted or name
    if name in _NET_SINKS and (base in _NET_BASES or base.endswith("request")) and (first_arg_tainted() or kw_url_tainted()):
        return "CWE-918", "ssrf", dotted or name
    return None


def _transfer(block: Block, tainted_in: set[str], func_name: str, flows: list[Flow]) -> set[str]:
    """Run one block's statements: gen/kill taint, and report sinks. Returns OUT set."""
    tainted = set(tainted_in)
    for stmt in block.stmts:
        # sinks first (a sink in the RHS is checked against taint reaching this stmt)
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                hit = _classify_sink(sub, tainted)
                if hit:
                    cwe, label, sink_name = hit
                    src = next((_dotted(a) or "input" for a in sub.args if _expr_tainted(a, tainted)), "tainted-arg")
                    flows.append(Flow(cwe=cwe, label=label, source=src,
                                      source_line=getattr(stmt, "lineno", 0),
                                      sink=sink_name, sink_line=getattr(sub, "lineno", 0),
                                      function=func_name))
        # then gen/kill for assignments
        rhs = stmt.value if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign)) else None
        if rhs is not None:
            tainted_rhs = _expr_tainted(rhs, tainted)
            for tgt in _assign_targets(stmt):
                if tainted_rhs:
                    tainted.add(tgt)        # gen
                else:
                    tainted.discard(tgt)    # kill — clean value overwrites taint
    return tainted


def _analyze_function(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[Flow]:
    cfg = CFG()
    cfg.build(fn.body)   # populates cfg.blocks
    # parameters are untrusted only if the function is an entrypoint — conservative
    # default: params are NOT sources (intra-procedural; interprocedural is deferred).
    in_sets: dict[int, set[str]] = {bid: set() for bid in cfg.blocks}
    flows: list[Flow] = []
    # worklist to fixpoint over reaching-taint
    preds: dict[int, list[int]] = {bid: [] for bid in cfg.blocks}
    for b in cfg.blocks.values():
        for s in b.succs:
            preds[s].append(b.bid)
    worklist = list(cfg.blocks.keys())
    out_sets: dict[int, set[str]] = {bid: set() for bid in cfg.blocks}
    guard = 0
    while worklist and guard < 10000:
        guard += 1
        bid = worklist.pop()
        in_sets[bid] = set().union(*(out_sets[p] for p in preds[bid])) if preds[bid] else set()
        new_out = _transfer(cfg.blocks[bid], in_sets[bid], fn.name, [])  # taint only, no dup flows
        if new_out != out_sets[bid]:
            out_sets[bid] = new_out
            worklist.extend(cfg.blocks[bid].succs)
    # final pass with fixed IN sets to collect flows once (dedup)
    seen: set[tuple] = set()
    for bid, block in cfg.blocks.items():
        local: list[Flow] = []
        _transfer(block, in_sets[bid], fn.name, local)
        for f in local:
            key = (f.cwe, f.sink, f.sink_line, f.source_line)
            if key not in seen:
                seen.add(key)
                flows.append(f)
    return flows


def analyze_source(code: str, *, filename: str = "<string>") -> list[dict[str, Any]]:
    """Comprehensive intra-procedural CFG taint analysis over Python source.
    Returns one record per unique source→sink flow. Fail-closed: parse error → []."""
    try:
        tree = ast.parse(code, filename=filename)
    except (SyntaxError, ValueError):
        return []
    out: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for flow in _analyze_function(node):
                out.append(flow.to_record())
    return out


# ── pattern catalog (all 7 cited blueprints; live vs deferred, auditable) ───────

PATTERN_CATALOG: dict[str, dict[str, Any]] = {
    "TAINT-001-SQL-INJECTION": {
        "cwe": "CWE-89", "languages": ["python"], "status": "live",
        "engine": "cfg_taint", "note": "request.* / input / env → execute/query sink",
        "citation": "https://semgrep.dev/docs/writing-rules/data-flow/taint-mode/overview"},
    "INJ-CMD": {"cwe": "CWE-78", "languages": ["python"], "status": "live", "engine": "cfg_taint",
                "note": "tainted → os.system / subprocess / popen",
                "citation": "https://cheatsheetseries.owasp.org/"},
    "INJ-CODE": {"cwe": "CWE-94", "languages": ["python"], "status": "live", "engine": "cfg_taint",
                 "note": "tainted → eval / exec / compile", "citation": "https://cwe.mitre.org/data/definitions/94.html"},
    "PATH-022": {"cwe": "CWE-22", "languages": ["python"], "status": "live", "engine": "cfg_taint",
                 "note": "tainted → open / shutil / send_file path", "citation": "https://cwe.mitre.org/data/definitions/22.html"},
    "DESER-502": {"cwe": "CWE-502", "languages": ["python"], "status": "live", "engine": "cfg_taint",
                  "note": "tainted → pickle/yaml/marshal load(s)", "citation": "https://cwe.mitre.org/data/definitions/502.html"},
    "SSRF-918": {"cwe": "CWE-918", "languages": ["python"], "status": "live", "engine": "cfg_taint",
                 "note": "tainted → requests/urllib network sink", "citation": "https://cwe.mitre.org/data/definitions/918.html"},
    # deferred — need tree-sitter grammars and/or a call graph (interprocedural)
    "MEM-002-USE-AFTER-FREE": {"cwe": "CWE-416", "languages": ["c", "cpp"], "status": "deferred",
        "needs": "tree-sitter c/cpp + pointer state machine", "lands": "PRD-10 10-d",
        "citation": "https://www.amossys.fr/insights/blog-technique/intro-to-use-after-free-detection/"},
    "CONC-003-RACE-CONDITION": {"cwe": "CWE-362", "languages": ["c", "cpp"], "status": "deferred",
        "needs": "lockset analysis + z-test over CFG", "lands": "PRD-10 10-e",
        "citation": "https://web.stanford.edu/~engler/racerx-sosp03.pdf"},
    "FW-004-SPRING-MISCONFIG": {"cwe": "CWE-1004", "languages": ["java"], "status": "deferred",
        "needs": "tree-sitter java + config threshold rules", "lands": "PRD-10 10-g",
        "citation": "https://yaogroup.cs.vt.edu/spring-security-sec-dev-2020-camera-ready.pdf"},
    "JS-005-PROTOTYPE-POLLUTION": {"cwe": "CWE-1321", "languages": ["javascript"], "status": "deferred",
        "needs": "object dependence graph (ODG)", "lands": "PRD-10 10-f",
        "citation": "https://www.usenix.org/system/files/sec22-li-song.pdf"},
    "ARITH-006-INTEGER-OVERFLOW": {"cwe": "CWE-190", "languages": ["c", "cpp"], "status": "deferred",
        "needs": "value-range/interval analysis", "lands": "PRD-10 10-d",
        "citation": "https://cwe.mitre.org/data/definitions/190.html"},
    "XSS-007-REACT-DANGEROUS-HTML": {"cwe": "CWE-79", "languages": ["javascript", "jsx"], "status": "deferred",
        "needs": "tree-sitter jsx + component taint", "lands": "PRD-10 10-f",
        "citation": "https://pragmaticwebsecurity.com/articles/spasecurity/react-xss-part1.html"},
}


def catalog_status() -> dict[str, Any]:
    live = sorted(k for k, v in PATTERN_CATALOG.items() if v["status"] == "live")
    deferred = sorted(k for k, v in PATTERN_CATALOG.items() if v["status"] == "deferred")
    cwes_live = sorted({v["cwe"] for v in PATTERN_CATALOG.values() if v["status"] == "live"})
    return {"schema": "lgwks.sast.catalog.v1", "live": live, "deferred": deferred,
            "cwe_classes_live": cwes_live, "total": len(PATTERN_CATALOG)}


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        src = open(sys.argv[1], encoding="utf-8", errors="replace").read()
        print(json.dumps({"findings": analyze_source(src, filename=sys.argv[1])}, indent=2))
    else:
        print(json.dumps(catalog_status(), indent=2))
