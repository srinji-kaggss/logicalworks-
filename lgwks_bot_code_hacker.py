"""
lgwks_bot_code_hacker — U5 build #2: enterprise-grade static security analyzer.

Evolves from naive regex scanning to a multi-layer fraud-engine architecture:

  Layer 1 — AST surface detection (H1-H4, retained from build #1)
  Layer 2 — Intra-file taint analysis (secret variable flow → sink)
  Layer 3 — Composite risk scoring (signal strength + context + history)
  Layer 4 — Baseline diffing (only flag *new* findings vs. previous run)
  Layer 5 — SARIF 2.1.0 export (structured, CI-integrable output)

Fraud-engine principles applied:
- Multi-signal aggregation: weak individual signals combine into strong verdicts
- Context awareness: where a variable was defined matters as much as where it was used
- False-positive suppression: configurable allowlists + historical TP/FP baseline
- Explainability: every finding carries a reasoning chain (why, not just what)
- Feedback loop: previous run baselines shape future detection thresholds

No LLM calls. No internet. Fail closed on parse errors.
"""

from __future__ import annotations

import ast
import fcntl
import lgwks_hashing
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import lgwks_project_artifacts as artifacts

_BOT = "code_hacker"

# ── Surface detection rule sets (Layer 1) ──────────────────────────────────
_SUBPROCESS_ATTRS = {"Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
_EXEC_ATTRS = {"system", "popen", "spawnl", "spawnv", "spawnlp", "spawnvp"}
_BROAD_DELETE = {"rmtree", "remove", "unlink", "rmdir"}
_WRITE_ATTRS = {"write_text", "write_bytes", "save", "save_as"}
_NET_MODULES = frozenset({"requests", "urllib.request", "httpx", "aiohttp", "http.client", "urllib3"})
# //why split egress imports from net-client *attrs* (#313): the egress check (H3) flags
# importing a module that can open an outbound socket. `urllib.parse` (URL string parsing),
# `urllib.error` (exception classes), `http.server` (INBOUND) cannot egress — flagging them
# was pure noise. Match egress-capable submodules exactly; match true client packages by top.
_EGRESS_EXACT = frozenset({"urllib.request", "http.client", "ftplib", "smtplib", "telnetlib"})
_EGRESS_TOPS = frozenset({"requests", "httpx", "aiohttp", "urllib3", "socket"})
# Network-client method names. `urlopen` is unambiguous (urllib only); the verb methods
# (get/post/...) are network sinks ONLY when the receiver is a known network client — a
# bare `d.get("k")` dict access must never read as an outbound request (#313).
_NET_VERB_ATTRS = frozenset({"get", "post", "put", "delete", "patch", "head", "options", "request"})
# Network sink method names by symbol (verbs + urlopen). Exported for graph-level
# consumers (lgwks_audit_graph) that match callee names without receiver resolution.
_NET_SINK_ATTRS = _NET_VERB_ATTRS | frozenset({"urlopen"})
_NET_CLIENT_FACTORIES = frozenset({"Session", "session", "Client", "AsyncClient", "ClientSession", "HTTPConnection", "HTTPSConnection", "PoolManager"})
_PATH_SINK_ATTRS = frozenset({"read_text", "read_bytes", "write_text", "write_bytes", "open", "rglob", "glob"})
_SQL_ATTRS = frozenset({"execute", "executescript"})
_NET_SAFE_RE = re.compile(r"(portal|network|search|fetch|browser|public|cohere|provider|auth_runtime)", re.I)
# Declares a value/variable a credential — used both for secret-named keys
# (getenv("API_KEY")) and secret-named variables. //why strict (#313): bare "key", "keys",
# "cache_key", "auth", "TOKENS" are overwhelmingly non-credential (dict keys, loop vars,
# config sections, limits); a loose regex turned them into phantom secret sources that
# leaked into every print of the surrounding payload. Require a qualified credential term.
_SECRET_NAME_RE = re.compile(
    r"(password|passwd|secret|credential|bearer|api_?key|access_?key|private_?key|"
    r"client_?secret|auth_?token|(^|_)token(_|$)|(^|_)apikey(_|$))", re.I)
# Calls that return a value of the SAME taint class as their RECEIVER — a secret stays a
# secret through `.strip()`/`.encode()`. (A call that does real work, like verify(token),
# returns a fresh untainted value, so it is NOT here.)
_RECV_PRESERVING = frozenset({
    "strip", "lstrip", "rstrip", "lower", "upper", "title", "encode", "decode",
    "replace", "hex", "removeprefix", "removesuffix", "casefold",
})
# Calls that return a value carrying their ARGUMENTS' taint — wrappers/formatters/path
# builders. `Path(user_input)` is still attacker-controlled; `sep.join(parts)` and
# `os.path.join(base, user)` carry the parts' taint; `"t={}".format(secret)` carries the
# secret. //why (#313): without these, `p = Path(input()); p.read_text()` laundered the
# taint and the traversal went undetected — a recall hole.
_ARG_PRESERVING = frozenset({
    "join", "format", "Path", "PurePath", "PosixPath", "WindowsPath",
    "str", "bytes", "bytearray", "repr", "fspath",
    "abspath", "normpath", "realpath", "expanduser", "basename", "dirname", "relpath",
})
from lgwks_substrate_config import _LOG_ATTRS  # one source of truth
_LOG_OBJ_RE = re.compile(r"^(logging|logger|log)", re.I)

# ── Baseline / allowlist helpers ────────────────────────────────────────────


def _finding_fingerprint(rec: dict) -> str:
    """Stable hash of a finding for deduplication and baseline tracking.
    Sensitive to file, kind, line, and symbol — NOT run_id or timestamp."""
    payload = json.dumps({
        "file": rec["links"]["file"],
        "kind": rec["kind"],
        "symbol": rec["links"].get("symbol"),
        "lineno": next(
            (e["value"] for e in rec.get("evidence", [])
             if e.get("name") == "lineno"),
            None
        ),
    }, sort_keys=True, separators=(",", ":"))
    return lgwks_hashing.content_id(payload)


class Baseline:
    """Historical finding store for TP/FP tracking and suppression.

    //why: world-class fraud engines learn from labeled history. A finding
    dismissed as false-positive 3 times should be auto-suppressed on the
    4th run unless the code changed."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self._seen: dict[str, dict] = {}
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._seen = {item["fp"]: item for item in data.get("findings", [])}
            except Exception:
                pass

    def is_suppressed(self, fp: str) -> bool:
        """Return True if this fingerprint was previously dismissed >=2 times."""
        if fp not in self._seen:
            return False
        return self._seen[fp].get("dismiss_count", 0) >= 2

    def has(self, fp: str) -> bool:
        """Return True when a finding fingerprint already exists in the baseline."""
        return fp in self._seen

    def get_history_penalty(self, fp: str) -> float:
        """Calculate penalty based on dismissal history (0..0.2). (H5)"""
        if fp not in self._seen:
            return 0.0
        # If it was dismissed once, -0.1; twice, -0.2 (which hits suppression threshold if >=2)
        count = self._seen[fp].get("dismiss_count", 0)
        return min(0.2, count * 0.1)

    def record(self, findings: list[dict]) -> None:
        """Persist current findings as the new baseline."""
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ensure file exists for locking
        self.path.touch(exist_ok=True)
        
        with self.path.open("r+") as f:
            # Advisory lock across read-modify-write
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # Merge existing dismissal counts if any
                f.seek(0)
                try:
                    existing_data = json.loads(f.read())
                    existing_fps = {item["fp"]: item for item in existing_data.get("findings", [])}
                except Exception:
                    existing_fps = {}

                current_findings = []
                for f_item in findings:
                    fp = _finding_fingerprint(f_item)
                    # Preserve count if it was seen before
                    count = existing_fps.get(fp, {}).get("dismiss_count", 0)
                    current_findings.append({
                        "fp": fp,
                        "kind": f_item["kind"],
                        "file": f_item["links"]["file"],
                        "dismiss_count": count,
                    })

                data = {
                    "updated_at": _ts(),
                    "findings": current_findings,
                }
                
                # Atomic write via temp file + replace
                tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# ── Taint tracker (Layer 2) ───────────────────────────────────────────────

# //why two taint CLASSES, not one lattice (#313): the scanner historically used a
# single "is it tainted?" bool for two unrelated questions —
#   SECRET    : does this value CONTAIN a credential? (drives H4 secret-exposure)
#   INJECTION : is this value ATTACKER-CONTROLLED? (drives H1 shell / H5 SSRF /
#               H6 path / H7 SQL / H8 file-write)
# Collapsing them made a diagnostic like `print(f"run: {run_id}")` read as secret
# exposure and a dict access like `pkt.get("k")` read as a network call. Tagging each
# source with the class(es) it actually carries, and asking checks the class-specific
# question, is what makes the static analysis precise without losing recall.
SECRET = "secret"
INJECTION = "injection"

# Source-kind → the taint class(es) it carries.
_KIND_CLASSES: dict[str, frozenset] = {
    "secret_var": frozenset({SECRET}),          # name matches the credential regex
    "env_secret": frozenset({SECRET, INJECTION}),  # getenv("API_KEY") — secret AND external
    "env_value": frozenset({INJECTION}),        # getenv("OUTPUT_DIR") — external, not secret
    "user_input": frozenset({INJECTION}),       # input(), argv
    "net_response": frozenset({INJECTION}),
    "file_read": frozenset({INJECTION}),
    "inferred_taint": frozenset(),              # caller passes the propagated classes
}


@dataclass
class Source:
    """A taint source: where a sensitive value enters the system."""
    name: str
    lineno: int
    kind: str  # 'secret_var', 'env_secret', 'env_value', 'user_input', 'file_read'
    classes: frozenset = field(default_factory=frozenset)  # subset of {SECRET, INJECTION}


@dataclass
class Sink:
    """A taint sink: where a sensitive value is consumed dangerously."""
    name: str
    lineno: int
    kind: str  # 'log', 'print', 'shell', 'network', 'file_write'


class TaintTracker:
    """Intra-file data-flow analysis for secret variables.

    Tracks assignments of sensitive names and detects when they flow into
    sinks (print, logging, shell, network). This is "taint analysis lite" —
    we don't do full inter-procedural analysis, but we do track:
    - direct use: print(token)
    - f-string interpolation: f"auth={token}"
    - concatenation: "Bearer " + token
    - dict/list membership: headers = {"Authorization": token}

    //why: naive regex flags *any* variable named 'token' in a print().
    Taint tracking flags only variables that were *assigned a sensitive value*
    or whose name matches the secret regex. This dramatically reduces FPs
    when developers use innocuous variable names like 'token' for non-secret
    purposes (e.g., CSRF token display in a debug log during dev).
    """

    def __init__(self) -> None:
        self.sources: dict[str, Source] = {}
        self.flows: list[tuple[Source, Sink, float]] = []

    def register_source(self, name: str, lineno: int, kind: str = "secret_var",
                        classes: Optional[frozenset] = None) -> None:
        if name not in self.sources:
            cls = classes if classes is not None else _KIND_CLASSES.get(kind, frozenset())
            self.sources[name] = Source(name=name, lineno=lineno, kind=kind, classes=cls)

    @staticmethod
    def _arg_is_secret_named(call: ast.Call) -> bool:
        """A .get()/.getenv() whose key argument names an actual credential.

        //why _SECRET_NAME_RE not _SECRET_RE (#313): the loose regex matched a config
        section key like `manifest.get("auth")` — "auth" is not a secret — and tainted
        the whole payload SECRET, leaking into every print of it. The strict regex
        requires a qualified credential term (api_key/password/token/...)."""
        return any(
            isinstance(a, ast.Constant) and isinstance(a.value, str)
            and len(a.value) > 2 and _SECRET_NAME_RE.search(a.value)
            for a in call.args
        )

    def taint_classes(self, node: ast.AST) -> frozenset:
        """Return the union of taint classes a node carries.

        //why no blanket f-string/BinOp rule: a JoinedStr or BinOp is tainted only
        when it *interpolates* a tainted source — `f"https://api/v1"` (all-constant)
        is not. ast.walk recurses into the children of an f-string/concatenation, so a
        tainted Name or source call nested inside is caught here. Treating every
        f-string/BinOp as tainted flagged constant URLs/SQL as injections — historically
        the dominant false-positive source.
        """
        cls: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in self.sources:
                cls |= self.sources[child.id].classes
            elif isinstance(child, ast.Call):
                f = child.func
                if isinstance(f, ast.Name) and f.id == "input":
                    cls.add(INJECTION)                       # raw user input
                elif isinstance(f, ast.Attribute):
                    if f.attr == "getenv":
                        cls.add(INJECTION)                   # env is externally settable
                        if self._arg_is_secret_named(child):
                            cls.add(SECRET)                  # getenv("API_KEY")
                    elif f.attr in {"get", "pop", "setdefault"} and self._arg_is_secret_named(child):
                        cls.add(SECRET)                      # cfg.get("api_key") / os.environ.get("TOKEN")
            if SECRET in cls and INJECTION in cls:
                break
        return frozenset(cls)

    def is_tainted(self, node: ast.AST, cls: Optional[str] = None) -> bool:
        """Returns True if the node carries taint of class `cls` (or any class when
        cls is None). Checks ask the class-specific question (INJECTION for sink
        checks, SECRET for exposure) so the two notions never bleed into each other."""
        classes = self.taint_classes(node)
        return bool(classes) if cls is None else (cls in classes)

    def propagated_classes(self, value: ast.AST) -> frozenset:
        """Taint classes carried by the RESULT of evaluating `value` — used for
        assignment propagation.

        //why distinct from taint_classes (#313): `taint_classes` answers "does this
        subtree reference a tainted value anywhere" (right for a SINK consuming an arg).
        Propagation needs "is the produced value itself the tainted one". A secret passed
        as an ARGUMENT to a call does NOT make the call's return value secret —
        `verified = verify(token)` yields a verdict, not the token. Crossing call results
        blindly is what spread SECRET from one `token` to scopes/result/packet/run_id."""
        if isinstance(value, ast.Name):
            return self.sources[value.id].classes if value.id in self.sources else frozenset()
        if isinstance(value, ast.Constant):
            return frozenset()
        if isinstance(value, (ast.JoinedStr, ast.FormattedValue, ast.BinOp, ast.BoolOp,
                              ast.Tuple, ast.List, ast.Set, ast.Starred)):
            cls: set[str] = set()
            for child in ast.iter_child_nodes(value):
                cls |= self.propagated_classes(child)
            return frozenset(cls)
        if isinstance(value, ast.Dict):
            cls = set()
            for v in value.values:
                if v is not None:
                    cls |= self.propagated_classes(v)
            return frozenset(cls)
        if isinstance(value, ast.IfExp):
            return self.propagated_classes(value.body) | self.propagated_classes(value.orelse)
        if isinstance(value, ast.Await):
            return self.propagated_classes(value.value)
        if isinstance(value, ast.Subscript):
            return self.propagated_classes(value.value)   # a slice of a secret is still secret
        if isinstance(value, ast.Attribute):
            return frozenset()                              # a field of an object is a fresh value
        if isinstance(value, ast.Call):
            f = value.func
            fname = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if isinstance(f, ast.Attribute):
                if f.attr == "getenv":
                    return frozenset({SECRET, INJECTION}) if self._arg_is_secret_named(value) else frozenset({INJECTION})
                if f.attr in {"get", "pop", "setdefault"} and self._arg_is_secret_named(value):
                    return frozenset({SECRET})
                if f.attr in _RECV_PRESERVING:              # secret.strip() stays secret
                    return self.propagated_classes(f.value)
            if fname == "input":
                return frozenset({INJECTION})
            if fname in _ARG_PRESERVING:                    # Path(x)/join(...)/format(...) carry args' taint
                cls: set[str] = set()
                for a in value.args:
                    cls |= self.propagated_classes(a)
                return frozenset(cls)
            return frozenset()                              # generic call result = fresh value
        return frozenset()

    def check_flow(self, node: ast.AST, sink_name: str, sink_lineno: int, sink_kind: str) -> list[tuple[Source, Sink, float]]:
        """Scan an AST subtree for SECRET-class sources flowing into a sink.

        //why SECRET-only and no string-literal rule (#313): exposure means a runtime
        *credential* reaches a print/log. A string literal can never carry a runtime
        secret (a label like "token:" is not a token), and an INJECTION-only value
        (a path, a run_id, an arg list) is not a secret. Both were prolific FPs."""
        found: list[tuple[Source, Sink, float]] = []
        sink = Sink(name=sink_name, lineno=sink_lineno, kind=sink_kind)
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in self.sources:
                src = self.sources[child.id]
                if SECRET in src.classes:
                    conf = 0.95 if isinstance(node, ast.Call) else 0.75
                    found.append((src, sink, conf))
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                # Inline secret read with no intervening assignment: print(os.getenv("API_KEY"))
                f = child.func
                if (f.attr == "getenv" or f.attr in {"get", "pop", "setdefault"}) and self._arg_is_secret_named(child):
                    src = Source(name=f"{f.attr}({child.args[0].value!r})", lineno=child.lineno,  # type: ignore[attr-defined]
                                 kind="env_secret", classes=frozenset({SECRET, INJECTION}))
                    found.append((src, sink, 0.8))
        return found


# ── Composite risk scorer (Layer 3) ───────────────────────────────────────

@dataclass
class RiskScore:
    """Composite risk: combines signal strength, blast radius, and history.
    
    //why explicit signals (H5): removes inert 0.1 placeholders. 
    Predictive signals (reachability, privilege_delta) replace the 'vibe' sum.
    """
    base: float           # 0..1 from the detector
    reachability: float = 0.0    # 0..1 normalized (O(n) predecessors)
    privilege_delta: float = 0.0 # 0..0.3 (delta if touches high-priv sink)
    history_penalty: float = 0.0 # -0..0.2 if previously dismissed
    final: float = field(init=False)
    explanation: str = field(init=False)

    def __post_init__(self) -> None:
        # Context boost: high reachability increases blast radius; 
        # privilege delta adds a step-function jump for sensitive sinks.
        context_boost = (self.reachability * 0.2) + self.privilege_delta
        raw = self.base + context_boost - self.history_penalty
        self.final = max(0.0, min(1.0, raw))
        
        reasons = []
        if self.reachability > 0.5:
            reasons.append(f"high reachability ({self.reachability:.2f})")
        if self.privilege_delta > 0:
            reasons.append(f"privilege delta (+{self.privilege_delta:.2f})")
        if self.history_penalty > 0:
            reasons.append(f"history penalty (-{self.history_penalty:.2f})")
        
        self.explanation = " | ".join(reasons) if reasons else "base detector confidence"

    def severity(self) -> str:
        if self.final >= 0.9:
            return "critical"
        if self.final >= 0.7:
            return "high"
        if self.final >= 0.4:
            return "medium"
        return "low"


# ── SARIF 2.1.0 converter (Layer 4) ─────────────────────────────────────────

class SARIFConverter:
    """Convert bot findings to SARIF 2.1.0 for CI integration.

    SARIF is the industry-standard format for static analysis results.
    It enables: GitHub Advanced Security ingestion, VS Code problem matching,
    Azure DevOps / GitLab SAST dashboards, and cross-tool correlation.
    """

    def __init__(self, tool_name: str = "lgwks-code-hacker", version: str = "2.0"):
        self.tool_name = tool_name
        self.version = version

    def convert(self, findings: list[dict], repo_root: Path) -> dict:
        runs = []
        for rec in findings:
            if rec["kind"] == "analyzer_failure":
                continue
            file_path = repo_root / rec["links"]["file"]
            lineno = next(
                (e["value"] for e in rec.get("evidence", [])
                 if e.get("name") == "lineno"),
                1
            )
            runs.append({
                "ruleId": rec["kind"],
                "level": self._severity_to_level(rec["severity"]),
                "message": {"text": rec["summary"]},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": rec["links"]["file"]},
                        "region": {
                            "startLine": lineno,
                            "startColumn": 1,
                        },
                    }
                }],
                "properties": {
                    "confidence": rec["confidence"],
                    "tags": rec.get("tags", []),
                }
            })
        return {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": self.tool_name,
                        "version": self.version,
                        "informationUri": "https://github.com/srinji-kaggss/logicalworks-",
                    }
                },
                "results": runs,
            }]
        }

    @staticmethod
    def _severity_to_level(sev: str) -> str:
        mapping = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "none"}
        return mapping.get(sev, "warning")


# ── Record factory ─────────────────────────────────────────────────────────

from lgwks_clock import now_iso as _ts  # one source of truth for timestamps


def _run_seed(repo: str) -> str:
    return artifacts.run_seed(_BOT, repo)


def _make(
    *,
    run_id: str,
    repo: str,
    file: str,
    kind: str,
    summary: str,
    severity: str,
    confidence: float,
    evidence: list[dict],
    tags: list[str],
    symbol: Optional[str] = None,
    created_at: Optional[str] = None,
) -> dict:
    # //why created_at is injected, not stamped here: a per-finding datetime.now()
    # made two identical scans of identical code produce non-equal records, which
    # breaks replay/determinism (doctrine T4) and diffing. The finding fingerprint
    # already excludes the timestamp; now the timestamp itself is stamped ONCE per
    # run() and threaded down, so a run over unchanged code is byte-reproducible.
    return artifacts.make_record(
        bot=_BOT, run_id=run_id, kind=kind, summary=summary, severity=severity,
        confidence=confidence, evidence=evidence, tags=tags, target_id=file,
        links={"repo": repo, "file": file, "symbol": symbol},
        created_at=created_at,
    )


def _failure_record(run_id: str, repo: str, file: str, reason: str,
                    created_at: Optional[str] = None) -> dict:
    return _make(
        run_id=run_id, repo=repo, file=file,
        kind="analyzer_failure",
        summary=f"parse error in {file}: {reason[:120]}",
        severity="info",
        confidence=1.0,
        evidence=[{"type": "trace", "name": "error", "value": reason[:300]}],
        tags=["analyzer", "parse-error"],
        created_at=created_at,
    )


def _is_net_safe(path: str) -> bool:
    return bool(_NET_SAFE_RE.search(path))


# ── Enhanced AST visitor with taint tracking ────────────────────────────────

class _Visitor(ast.NodeVisitor):
    """Single-pass H1-H4 visitor with Layer 2 taint tracking.

    //why: the original visitor used a simple `_secret_vars` set.
    This version uses TaintTracker for structured source→sink flow
    reporting, which gives fraud-engine-quality explainability."""

    def __init__(self, rel: str, run_id: str, repo: str, baseline: Baseline | None = None,
                 created_at: Optional[str] = None, graph: Any = None) -> None:
        self.rel = rel
        self.run_id = run_id
        self.repo = repo
        self.baseline = baseline
        self.created_at = created_at  # //why: one run timestamp, threaded for replay determinism
        self.graph = graph            # //why: for blast-radius / reachability scoring (H5)
        self.findings: list[dict] = []
        self.taint = TaintTracker()
        self._net_safe = _is_net_safe(rel)
        # Names that resolve to a network module/client (import alias, or a var bound to
        # requests.Session()/httpx.Client()/...). Only `.get/.post/...` on one of these is
        # an outbound request — distinguishing it from a dict's `.get()`. (#313, H5)
        self.net_names: set[str] = set()
        # Bare function names imported from a net module: `from requests import get`.
        self.net_funcs: set[str] = set()

        # Cache reachability for this file once
        self._file_reachability = 0.0
        if graph and hasattr(graph, "predecessors"):
            try:
                preds = list(graph.predecessors(rel))
                # Normalize by total node count (max 1.0)
                n = len(graph.nodes)
                self._file_reachability = len(preds) / n if n > 0 else 0.0
            except Exception:
                pass

        # Guard tracking
        self.guards_found: set[str] = set()

    def _add(self, kind: str, summary: str, severity: str, confidence: float,
             evidence: list[dict], tags: list[str], lineno: int, symbol: Optional[str] = None) -> None:
        if not any(e.get("name") == "lineno" for e in evidence):
            evidence = [{"type": "file_excerpt", "name": "lineno", "value": lineno}] + evidence

        # Composite risk scoring
        history_penalty = 0.0
        if self.baseline:
            rec = _make(
                run_id=self.run_id, repo=self.repo, file=self.rel,
                kind=kind, summary=summary, severity=severity,
                confidence=confidence, evidence=evidence, tags=tags, symbol=symbol,
                created_at=self.created_at,
            )
            fp = _finding_fingerprint(rec)
            if self.baseline.is_suppressed(fp):
                return  # skip suppressed finding
            history_penalty = self.baseline.get_history_penalty(fp)

        # Calculate privilege delta (H5)
        priv_delta = 0.0
        if kind in ("dangerous_shell_exec", "ssrf_risk", "sql_injection_risk"):
            priv_delta = 0.15
        if tags and "critical" in tags:
            priv_delta = 0.3

        risk = RiskScore(base=confidence, reachability=self._file_reachability, 
                         privilege_delta=priv_delta, history_penalty=history_penalty)

        # Include risk explanation in evidence for transparency (H5)
        evidence.append({"type": "metric", "name": "risk_explanation", "value": risk.explanation})

        self.findings.append(_make(
            run_id=self.run_id, repo=self.repo, file=self.rel,
            kind=kind, summary=summary, severity=risk.severity(),
            confidence=risk.final, evidence=evidence, tags=tags, symbol=symbol,
            created_at=self.created_at,
        ))

    # ── H1: dangerous shell execution ────────────────────────────────────────

    def _check_h1(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id

        if attr in _SUBPROCESS_ATTRS:
            # Check for shell=True OR tainted string argument (when not a list)
            is_shell = any(kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                           for kw in node.keywords)
            
            if is_shell:
                self._add("dangerous_shell_exec", f"subprocess.{attr}(shell=True) at line {ln}",
                          "critical", 1.0, [], ["exec", "shell", "h1"], ln)
            elif node.args and not isinstance(node.args[0], (ast.List, ast.Tuple)):
                arg0 = node.args[0]
                # A tainted string command is a confirmed injection path.
                if self.taint.is_tainted(arg0, INJECTION):
                    self._add("dangerous_shell_exec", f"subprocess.{attr}() with tainted string command at line {ln}",
                              "high", 0.8, [], ["exec", "h1"], ln)
                # //why flag constant-built strings here but NOT for URL/SQL/path sinks:
                # the safe form of subprocess is a token LIST; building the command as a
                # single string (f-string/concat) is itself the smell, taint aside. The
                # same f-string is normal for an HTTP URL or SQL text, so H5/H6/H7 gate
                # strictly on taint instead. EXCEPT list/tuple concatenation
                # (`["git"] + list(args)`) builds an argv, not a shell string — shell=False,
                # no injection. (#313)
                elif isinstance(arg0, (ast.JoinedStr, ast.BinOp)) and not self._binop_builds_sequence(arg0):
                    self._add("dangerous_shell_exec", f"subprocess.{attr}() with string-built command at line {ln}",
                              "high", 0.7, [], ["exec", "h1"], ln)

        if attr in _EXEC_ATTRS:
            # os.system/os.popen are discouraged. A tainted argument is a confirmed
            # injection (critical); a controlled/constant argument is a code smell worth
            # surfacing but not a merge-blocking injection (medium). //why calibrate by
            # taint (#313): flagging every os.system at critical inflated test scaffolding
            # with controlled args into gate failures.
            is_tainted = bool(node.args) and self.taint.is_tainted(node.args[0], INJECTION)
            sev = "critical" if is_tainted else "medium"
            conf = 0.9 if is_tainted else 0.45
            self._add("dangerous_shell_exec", f"os.{attr}() call at line {ln}",
                      sev, conf, [], ["exec", "h1"], ln)

        if attr in {"eval", "exec"}:
            if node.args and not isinstance(node.args[0], ast.Constant):
                self._add("dangerous_shell_exec", f"{attr}() with dynamic argument at line {ln}",
                          "critical", 0.9, [], ["eval", "exec", "h1"], ln)

    @staticmethod
    def _binop_builds_sequence(node: ast.AST) -> bool:
        """True if a BinOp is list/tuple concatenation (argv construction), not string
        building — detected by a List/Tuple literal on either side, recursively."""
        if not isinstance(node, ast.BinOp):
            return False
        for side in (node.left, node.right):
            if isinstance(side, (ast.List, ast.Tuple)):
                return True
            if isinstance(side, ast.BinOp) and _Visitor._binop_builds_sequence(side):
                return True
        return False

    # ── H5: SSRF Risk detection ──────────────────────────────────────────────

    def _net_receiver_root(self, recv: ast.AST) -> Optional[str]:
        """If `recv` resolves to a known network client/module, return its root name.

        Handles `requests.get(...)` (recv = Name 'requests'), `session.get(...)`
        (recv = Name bound to a Session), and `urllib.request.urlopen` style chains.
        A plain dict/object (`pkt`, `cfg`) returns None → its `.get()` is not a request."""
        if isinstance(recv, ast.Name):
            return recv.id if recv.id in self.net_names else None
        if isinstance(recv, ast.Attribute):
            # walk to the root Name of the attribute chain (e.g. urllib.request)
            cur: ast.AST = recv
            parts: list[str] = []
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                chain = ".".join(reversed(parts))
                root = cur.id
                if root in self.net_names or chain in _NET_MODULES:
                    return root
        return None

    def _check_h5(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)

        # Decide whether this call is genuinely an outbound network request.
        is_net_sink = False
        if attr == "urlopen":
            is_net_sink = True                                   # urllib only — unambiguous
        elif attr in _NET_VERB_ATTRS and isinstance(func, ast.Attribute):
            if self._net_receiver_root(func.value) is not None:  # requests.get / session.get
                is_net_sink = True
        elif isinstance(func, ast.Name) and func.id in self.net_funcs:
            is_net_sink = True                                   # `from requests import get; get(url)`

        if not is_net_sink:
            return
        if "_remote_allowed" in self.guards_found:
            return

        # SSRF = the URL/target is attacker-controlled. Check the URL argument(s) for
        # INJECTION taint — a constant or config endpoint is not SSRF.
        url_tainted = any(self.taint.is_tainted(arg, INJECTION) for arg in node.args)
        if url_tainted:
            self._add("ssrf_risk", f"network request to attacker-controlled URL '{attr}()' at line {ln}",
                      "high", 0.7, [], ["network", "ssrf", "h5"], ln)

    # ── H6: Path Traversal detection ─────────────────────────────────────────

    def _check_h6(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id

        if attr in _PATH_SINK_ATTRS:
            # Traversal risk needs an ATTACKER-CONTROLLED path component. A path built
            # from a fixed name or controlled config (gnn_dir/"nodes.csv") is not it.
            tainted = any(self.taint.is_tainted(arg, INJECTION) for arg in node.args)
            # Check the object itself (e.g. p.read_text() where p is tainted)
            if not tainted and isinstance(node.func, ast.Attribute) and self.taint.is_tainted(node.func.value, INJECTION):
                tainted = True

            if tainted:
                if "is_relative_to" in self.guards_found:
                    return

                self._add("path_traversal_risk", f"file operation on attacker-controlled path '{attr}()' at line {ln}",
                          "high", 0.7, [], ["file", "traversal", "h6"], ln)
                return

    # ── H7: SQL Injection detection ──────────────────────────────────────────

    def _check_h7(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id

        if attr in _SQL_ATTRS:
            # First argument is typically the SQL string; injection = attacker-controlled.
            if node.args and self.taint.is_tainted(node.args[0], INJECTION):
                self._add("sql_injection_risk", f"dynamic SQL string in '{attr}()' at line {ln}",
                          "high", 0.85, [], ["sql", "injection", "h7"], ln)

    # ── H8: File Storage Risk ────────────────────────────────────────────────

    def _check_h8(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id

        if attr in _WRITE_ATTRS:
            # Risk = writing to an ATTACKER-CONTROLLED destination path. A write to a
            # path the program controls (key-derived vault entry, run_id report) is not.
            tainted = isinstance(node.func, ast.Attribute) and self.taint.is_tainted(node.func.value, INJECTION)
            if tainted:
                self._add("file_storage_risk", f"file write to attacker-controlled path '{attr}()' at line {ln}",
                          "high", 0.7, [], ["file", "upload", "h8"], ln)

    # ── H2: unsafe file mutation ─────────────────────────────────────────────

    def _check_h2(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id
        if attr in _BROAD_DELETE:
            # //why gate on taint (#313): a recursive delete is dangerous when the path is
            # attacker-controlled (`shutil.rmtree(user_dir)`). Flagging every `tmp.unlink()`
            # and test-fixture cleanup as "critical" was 62 FPs and trained reviewers to
            # ignore the class. Fire only when the deletion target is injection-tainted.
            target_tainted = any(self.taint.is_tainted(arg, INJECTION) for arg in node.args)
            if not target_tainted and isinstance(node.func, ast.Attribute):
                target_tainted = self.taint.is_tainted(node.func.value, INJECTION)
            if target_tainted:
                self._add("unsafe_file_mutation", f"broad delete '{attr}' on attacker-controlled path at line {ln}",
                          "critical", 0.9, [], ["file", "delete", "h2"], ln)

    # ── H3: unbounded network egress ─────────────────────────────────────────

    def _flag_net_import(self, module: str, lineno: int) -> None:
        if self._net_safe:
            return
        top = module.split(".")[0]
        # Egress-capable only: exact submodule match (urllib.request, http.client) or a
        # client package by top (requests, httpx, ...). urllib.parse/error and http.server
        # cannot open an outbound connection — not egress.
        if module in _EGRESS_EXACT or top in _EGRESS_TOPS:
            self._add("unbounded_network_egress",
                      f"network import '{module}' in non-network module",
                      "medium", 0.55, [], ["network", "egress", "h3"], lineno)

    @staticmethod
    def _is_net_module(module: str) -> bool:
        top = module.split(".")[0]
        return module in _NET_MODULES or module in _EGRESS_EXACT or top in _EGRESS_TOPS

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._flag_net_import(alias.name, node.lineno)
            if self._is_net_module(alias.name):
                # the name code calls through: `import httpx as h` -> 'h'; `import requests` -> 'requests'
                self.net_names.add(alias.asname or alias.name.split(".")[0])
            if "_remote_allowed" in alias.name:
                self.guards_found.add("_remote_allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module:
            self._flag_net_import(node.module, node.lineno)
            if self._is_net_module(node.module):
                for alias in node.names:
                    bound = alias.asname or alias.name
                    if alias.name == "urlopen" or alias.name in _NET_VERB_ATTRS:
                        self.net_funcs.add(bound)            # from requests import get
                    elif alias.name in _NET_CLIENT_FACTORIES:
                        self.net_names.add(bound)            # from requests import Session
        for alias in node.names:
            if alias.name in {"_remote_allowed", "is_relative_to"}:
                self.guards_found.add(alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None: # noqa: N802
        if node.name in {"_remote_allowed", "is_relative_to"}:
            self.guards_found.add(node.name)
        self.generic_visit(node)

    # ── H4: secret exposure / logging risk WITH taint tracking ──────────────

    def _binds_net_client(self, value: ast.AST) -> bool:
        """True when `value` produces a network client: requests.Session(),
        httpx.Client(), a bare imported factory call, or an alias of a net name."""
        if isinstance(value, ast.Name):
            return value.id in self.net_names                # s = requests (rebind)
        if isinstance(value, ast.Call):
            f = value.func
            if isinstance(f, ast.Attribute) and f.attr in _NET_CLIENT_FACTORIES:
                return self._net_receiver_root(f.value) is not None
            if isinstance(f, ast.Name) and (f.id in _NET_CLIENT_FACTORIES or f.id in self.net_names):
                return True
        return False

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        # Bind network clients so a later `client.get(url)` resolves as a real request.
        if self._binds_net_client(node.value):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    self.net_names.add(tgt.id)

        # Class-aware taint propagation: the target inherits exactly the taint classes
        # its value carries (SECRET and/or INJECTION). A name matching the credential
        # regex is itself a SECRET source. //why no generic "inferred_taint" anymore: a
        # value being "tainted" said nothing about WHICH risk it feeds — that conflation
        # was the FP engine (#313).
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                classes = set(self.taint.propagated_classes(node.value))
                if _SECRET_NAME_RE.search(tgt.id):
                    classes.add(SECRET)
                if classes:
                    self.taint.register_source(tgt.id, node.lineno, kind="inferred_taint",
                                               classes=frozenset(classes))
        self.generic_visit(node)

    def _check_h4(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        is_print = isinstance(func, ast.Name) and func.id == "print"
        is_log = (
            isinstance(func, ast.Attribute) and func.attr in _LOG_ATTRS
            and isinstance(func.value, ast.Name) and _LOG_OBJ_RE.match(func.value.id)
        )
        if not (is_print or is_log):
            return
        fname = "print" if is_print else f"{func.value.id}.{func.attr}"

        # Layer 2: taint flow detection
        for arg in node.args:
            flows = self.taint.check_flow(arg, fname, ln, "log")
            for src, sink, conf in flows:
                self._add("secret_exposure_risk",
                          f"taint flow: '{src.name}' ({src.kind}) → {sink.name}() at line {ln}",
                          "high", conf,
                          [
                              {"type": "trace", "name": "source", "value": f"{src.name} defined at L{src.lineno}"},
                              {"type": "trace", "name": "sink", "value": f"{sink.name}() at L{sink.lineno}"},
                              {"type": "trace", "name": "leaked_name", "value": src.name},
                          ],
                          ["secret", "logging", "taint", "h4"], ln)
                return

        # Fallback: naive name-only detection for variables we didn't track
        for arg in node.args:
            if isinstance(arg, ast.Name) and _SECRET_NAME_RE.search(arg.id):
                self._add("secret_exposure_risk",
                          f"possible credential '{arg.id}' in {fname}() at line {ln}",
                          "medium", 0.5,
                          [{"type": "trace", "name": "leaked_name", "value": arg.id}],
                          ["secret", "logging", "h4"], ln)
                return

    # ── combined Call dispatch ───────────────────────────────────────────────

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in {"_remote_allowed", "is_relative_to"}:
                self.guards_found.add(func.id)
        elif isinstance(func, ast.Attribute):
            if func.attr in {"_remote_allowed", "is_relative_to"}:
                self.guards_found.add(func.attr)

        self._check_h1(node)
        self._check_h2(node)
        self._check_h4(node)
        self._check_h5(node)
        self._check_h6(node)
        self._check_h7(node)
        self._check_h8(node)
        self.generic_visit(node)


# ── File scanner ────────────────────────────────────────────────────────────

def _scan_file(path: Path, rel: str, run_id: str, repo: str, baseline: Baseline | None,
               created_at: Optional[str] = None, graph: Any = None) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [_failure_record(run_id, repo, rel, str(exc), created_at=created_at)]
    except Exception as exc:
        return [_failure_record(run_id, repo, rel, str(exc), created_at=created_at)]
    v = _Visitor(rel, run_id, repo, baseline=baseline, created_at=created_at, graph=graph)
    v.visit(tree)
    return v.findings


# ── Public API ──────────────────────────────────────────────────────────────

def run(
    repo: Path | str,
    changed_files: Optional[list[str]] = None,
    graph: Any = None,
    run_id: Optional[str] = None,
    baseline_path: Optional[Path] = None,
    update_baseline: bool = False,
    emit_sarif: bool = False,
    created_at: Optional[str] = None,
) -> list[dict]:
    """
    Scan *repo* for H1–H4 findings with enterprise fraud-engine quality.

    Args:
        repo: path to the repo root.
        changed_files: if given, scan only these relative paths.
        graph: CodeGraph object for blast-radius / reachability scoring (H5).
        run_id: stable run identifier; generated from repo path when omitted.
        baseline_path: path to JSON baseline for false-positive suppression.
        emit_sarif: if True, also write SARIF to repo/.lgwks/code-hacker.sarif.

    Returns list of lgwks.bot.record.v1 records.
    """
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = "code-hacker:" + _run_seed(repo_str)
    # //why one timestamp for the whole run: stamped here and threaded into every
    # finding so a re-scan of unchanged code is byte-identical (T4 determinism).
    # Callers may pin it explicitly (tests, replay) for full reproducibility.
    if created_at is None:
        created_at = _ts()

    baseline = Baseline(baseline_path)

    if changed_files is not None:
        targets = [repo / f for f in changed_files if f.endswith(".py")]
        rels = [f for f in changed_files if f.endswith(".py")]
    else:
        # canonical enumerator: excludes 3rd-party libs/caches AND in-repo copies
        # (worktrees/.claude/archive) — the dirs whose duplicates were review noise
        import lgwks_repo_scan
        py_files = lgwks_repo_scan.py_files(repo)
        targets = py_files
        rels = [str(p.relative_to(repo)) for p in py_files]

    findings: list[dict] = []
    for path, rel in zip(targets, rels):
        p = Path(path)
        if not p.is_file():
            continue
        findings.extend(_scan_file(p, rel, run_id, repo_str, baseline, 
                                   created_at=created_at, graph=graph))

    # Persist the baseline ONLY on explicit --update-baseline intent. Writing it on
    # every run is self-certification: the scan absorbs its own new findings into the
    # baseline it gates against, so the next run sees 0-new and passes — a gate that
    # can never block twice (#304). Read-only by default makes the verdict
    # deterministic; baseline curation (FP suppression) is a reviewed, opt-in action.
    if baseline_path and update_baseline:
        baseline.record(findings)

    # Optional SARIF export
    if emit_sarif:
        sarif_dir = repo / ".lgwks"
        sarif_dir.mkdir(parents=True, exist_ok=True)
        converter = SARIFConverter()
        sarif = converter.convert(findings, repo)
        (sarif_dir / "code-hacker.sarif").write_text(
            json.dumps(sarif, indent=2), encoding="utf-8"
        )

    return findings


if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Logical Works Code Hacker — AST-based security scanner (H5–H8)")
    parser.add_argument("--scan", default=".", help="Directory to scan")
    parser.add_argument("--baseline", type=Path, help="Path to JSON baseline for FP suppression")
    parser.add_argument("--update-baseline", action="store_true", help="Overwrite the baseline with new findings")
    parser.add_argument("--sarif", action="store_true", help="Emit SARIF output")
    args = parser.parse_args()
    
    # repo root is parent of this script's directory if run from within
    repo_path = Path(args.scan).resolve()
    
    try:
        prior_baseline = Baseline(args.baseline) if args.baseline else None
        findings = run(repo_path, baseline_path=args.baseline, emit_sarif=args.sarif, update_baseline=args.update_baseline)
        print(f"Scan complete: {len(findings)} findings.")
        
        # Exit 1 only for open high-severity findings that are new to the supplied
        # baseline. Historical findings remain visible and stay in the baseline,
        # but do not make every subsequent gate unusable.
        high_risk = []
        for finding in findings:
            # //why both "high" AND "critical": severity() emits "critical" for
            # final>=0.9. The old gate matched only =="high", so every critical
            # finding silently bypassed the merge gate — the most severe class was
            # the one NOT enforced. Fail on both (#313).
            if finding.get("status") != "open" or finding.get("severity") not in ("high", "critical"):
                continue
            fp = _finding_fingerprint(finding)
            if prior_baseline is not None and prior_baseline.has(fp):
                continue
            high_risk.append(finding)
        if high_risk:
            print(f"FAILED: {len(high_risk)} new high/critical-severity findings remain open.")
            for f in high_risk[:5]:
                 print(f"  - {f['summary']} in {f['links']['file']}")
            sys.exit(1)
            
        sys.exit(0)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
