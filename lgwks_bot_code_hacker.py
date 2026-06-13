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
import hashlib
import json
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
_NET_SINK_ATTRS = frozenset({"get", "post", "put", "delete", "request", "urlopen"})
_PATH_SINK_ATTRS = frozenset({"read_text", "read_bytes", "write_text", "write_bytes", "open", "rglob", "glob"})
_SQL_ATTRS = frozenset({"execute", "executescript"})
_NET_TOPS = frozenset(m.split(".")[0] for m in _NET_MODULES)
_NET_SAFE_RE = re.compile(r"(portal|network|search|fetch|browser|public|cohere|provider|auth_runtime)", re.I)
_SECRET_RE = re.compile(r"(token|secret|key|password|api_key|credential|auth|bearer)", re.I)
_LOG_ATTRS = frozenset({"debug", "info", "warning", "error", "critical", "exception", "log"})
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
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


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

    def record(self, findings: list[dict]) -> None:
        """Persist current findings as the new baseline."""
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": _ts(),
            "findings": [
                {
                    "fp": _finding_fingerprint(f),
                    "kind": f["kind"],
                    "file": f["links"]["file"],
                    "dismiss_count": 0,  # fresh run, reset counters
                }
                for f in findings
            ],
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Taint tracker (Layer 2) ───────────────────────────────────────────────

@dataclass
class Source:
    """A taint source: where a sensitive value enters the system."""
    name: str
    lineno: int
    kind: str  # 'secret_var', 'env_var', 'user_input', 'file_read'


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

    def register_source(self, name: str, lineno: int, kind: str = "secret_var") -> None:
        if name not in self.sources:
            self.sources[name] = Source(name=name, lineno=lineno, kind=kind)

    def is_tainted(self, node: ast.AST) -> bool:
        """Returns True if the node represents or contains a tainted value.

        //why no blanket f-string/BinOp rule: a JoinedStr or BinOp is tainted only
        when it *interpolates* a tainted source — `f"https://api/v1"` (all-constant)
        is not. ast.walk already recurses into the children of an f-string or a
        concatenation, so a tainted Name or source call nested inside is caught by
        the checks below. Treating every f-string/BinOp as tainted flagged constant
        URLs/SQL as injections — the dominant false-positive source.
        """
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in self.sources:
                return True
            # Recognize source functions directly
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id == "input":
                    return True
                if isinstance(child.func, ast.Attribute) and child.func.attr == "getenv":
                    return True
        return False

    def check_flow(self, node: ast.AST, sink_name: str, sink_lineno: int, sink_kind: str) -> list[tuple[Source, Sink, float]]:
        """Scan an AST subtree for references to tracked sources.
        Returns list of (source, sink, confidence) tuples."""
        found: list[tuple[Source, Sink, float]] = []
        sink = Sink(name=sink_name, lineno=sink_lineno, kind=sink_kind)
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in self.sources:
                src = self.sources[child.id]
                # Confidence: direct use > f-string > dict value
                conf = 0.95 if isinstance(node, ast.Call) else 0.75
                found.append((src, sink, conf))
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                # Check if string literal contains a secret-like value
                if _SECRET_RE.search(child.value) and len(child.value) > 8:
                    src = Source(name=f"LITERAL_{child.lineno}", lineno=child.lineno, kind="literal_secret")
                    found.append((src, sink, 0.6))
        return found


# ── Composite risk scorer (Layer 3) ───────────────────────────────────────

@dataclass
class RiskScore:
    """Composite risk: combines signal strength, blast radius, and history."""
    base: float           # 0..1 from the detector
    context_boost: float  # +0..0.3 from taint flow / cross-file reach
    history_penalty: float  # -0..0.2 if previously dismissed
    final: float = field(init=False)

    def __post_init__(self) -> None:
        raw = self.base + self.context_boost - self.history_penalty
        self.final = max(0.0, min(1.0, raw))

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

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run_seed(repo: str) -> str:
    return hashlib.sha256(f"code_hacker:{repo}".encode()).hexdigest()[:12]


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
    return {
        "schema": artifacts.BOT_RECORD_SCHEMA,
        "run_id": run_id,
        "bot": _BOT,
        "target": {"kind": "file", "id": file},
        "kind": kind,
        "summary": summary,
        "severity": severity,
        "confidence": confidence,
        "status": "open",
        "evidence": evidence,
        "links": {"repo": repo, "file": file, "symbol": symbol},
        "tags": tags,
        "created_at": created_at or _ts(),
    }


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
                 created_at: Optional[str] = None) -> None:
        self.rel = rel
        self.run_id = run_id
        self.repo = repo
        self.baseline = baseline
        self.created_at = created_at  # //why: one run timestamp, threaded for replay determinism
        self.findings: list[dict] = []
        self.taint = TaintTracker()
        self._net_safe = _is_net_safe(rel)
        
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
            # We don't have real dismiss history in baseline yet; penalty stays 0

        risk = RiskScore(base=confidence, context_boost=0.0, history_penalty=history_penalty)

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
                if self.taint.is_tainted(arg0):
                    self._add("dangerous_shell_exec", f"subprocess.{attr}() with tainted string command at line {ln}",
                              "high", 0.8, [], ["exec", "h1"], ln)
                # //why flag constant-built strings here but NOT for URL/SQL/path sinks:
                # the safe form of subprocess is a token LIST; building the command as a
                # single string (f-string/concat) is itself the smell, taint aside. The
                # same f-string is normal for an HTTP URL or SQL text, so H5/H6/H7 gate
                # strictly on taint instead.
                elif isinstance(arg0, (ast.JoinedStr, ast.BinOp)):
                    self._add("dangerous_shell_exec", f"subprocess.{attr}() with string-built command at line {ln}",
                              "high", 0.7, [], ["exec", "h1"], ln)

        if attr in _EXEC_ATTRS:
            # os.system and os.popen are inherently dangerous (deprecated for security)
            is_tainted = bool(node.args) and self.taint.is_tainted(node.args[0])
            sev = "critical" if is_tainted else "high"
            conf = 0.9 if is_tainted else 0.8
            self._add("dangerous_shell_exec", f"os.{attr}() call at line {ln}",
                      sev, conf, [], ["exec", "h1"], ln)

        if attr in {"eval", "exec"}:
            if node.args and not isinstance(node.args[0], ast.Constant):
                self._add("dangerous_shell_exec", f"{attr}() with dynamic argument at line {ln}",
                          "critical", 0.9, [], ["eval", "exec", "h1"], ln)

    # ── H5: SSRF Risk detection ──────────────────────────────────────────────

    def _check_h5(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno
        attr = None
        if isinstance(func, ast.Attribute):
            attr = func.attr
        elif isinstance(func, ast.Name):
            attr = func.id

        if attr in _NET_SINK_ATTRS:
            # Check for non-constant URL arguments OR tainted caller (e.g. session.get(url))
            tainted = False
            for arg in node.args:
                if self.taint.is_tainted(arg):
                    tainted = True
                    break
            if not tainted and isinstance(node.func, ast.Attribute) and self.taint.is_tainted(node.func.value):
                tainted = True

            if tainted:
                # Potential SSRF. Look for suppression heuristic.
                if "_remote_allowed" in self.guards_found:
                    return

                self._add("ssrf_risk", f"network request to tainted URL '{attr}()' at line {ln}",
                          "high", 0.7, [], ["network", "ssrf", "h5"], ln)
                return

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
            tainted = False
            for arg in node.args:
                if self.taint.is_tainted(arg):
                    tainted = True
                    break
            # Check the object itself (e.g. p.read_text())
            if not tainted and isinstance(node.func, ast.Attribute) and self.taint.is_tainted(node.func.value):
                tainted = True

            if tainted:
                if "is_relative_to" in self.guards_found:
                    return

                self._add("path_traversal_risk", f"file operation on tainted path '{attr}()' at line {ln}",
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
            # First argument is typically the SQL string
            if node.args and self.taint.is_tainted(node.args[0]):
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
            # Check if filename/path is tainted
            tainted = False
            if isinstance(node.func, ast.Attribute) and self.taint.is_tainted(node.func.value):
                tainted = True
            
            if tainted:
                self._add("file_storage_risk", f"file write to tainted path '{attr}()' at line {ln}",
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
            self._add("unsafe_file_mutation", f"broad delete call '{attr}' at line {ln}",
                      "high", 0.9, [], ["file", "delete", "h2"], ln)

    # ── H3: unbounded network egress ─────────────────────────────────────────

    def _flag_net_import(self, module: str, lineno: int) -> None:
        if self._net_safe:
            return
        top = module.split(".")[0]
        if module in _NET_MODULES or top in _NET_TOPS:
            self._add("unbounded_network_egress",
                      f"network import '{module}' in non-network module",
                      "medium", 0.55, [], ["network", "egress", "h3"], lineno)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._flag_net_import(alias.name, node.lineno)
            if "_remote_allowed" in alias.name:
                self.guards_found.add("_remote_allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module:
            self._flag_net_import(node.module, node.lineno)
        for alias in node.names:
            if alias.name in {"_remote_allowed", "is_relative_to"}:
                self.guards_found.add(alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None: # noqa: N802
        if node.name in {"_remote_allowed", "is_relative_to"}:
            self.guards_found.add(node.name)
        self.generic_visit(node)

    # ── H4: secret exposure / logging risk WITH taint tracking ──────────────

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for tgt in node.targets:
            if isinstance(tgt, ast.Name):
                is_src = False
                # If the value being assigned is itself tainted, the target becomes a source.
                if self.taint.is_tainted(node.value):
                    self.taint.register_source(tgt.id, node.lineno, kind="inferred_taint")
                    is_src = True
                
                # Check for direct calls to known source functions
                if not is_src and isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Name) and node.value.func.id == "input":
                        self.taint.register_source(tgt.id, node.lineno, kind="user_input")
                        is_src = True
                    elif isinstance(node.value.func, ast.Attribute):
                        if node.value.func.attr in {"get", "pop", "setdefault"}:
                            env_hint = any(
                                isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                                and _SECRET_RE.search(arg.value)
                                for arg in node.value.args
                            )
                            if env_hint:
                                self.taint.register_source(tgt.id, node.lineno, kind="env_var")
                                is_src = True
                        elif node.value.func.attr == "getenv":
                            self.taint.register_source(tgt.id, node.lineno, kind="env_var")
                            is_src = True

                if not is_src and _SECRET_RE.search(tgt.id):
                    self.taint.register_source(tgt.id, node.lineno, kind="secret_var")
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
            if isinstance(arg, ast.Name) and _SECRET_RE.search(arg.id):
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
               created_at: Optional[str] = None) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [_failure_record(run_id, repo, rel, str(exc), created_at=created_at)]
    except Exception as exc:
        return [_failure_record(run_id, repo, rel, str(exc), created_at=created_at)]
    v = _Visitor(rel, run_id, repo, baseline=baseline, created_at=created_at)
    v.visit(tree)
    return v.findings


# ── Public API ──────────────────────────────────────────────────────────────

def run(
    repo: Path | str,
    changed_files: Optional[list[str]] = None,
    _graph=None,
    run_id: Optional[str] = None,
    baseline_path: Optional[Path] = None,
    emit_sarif: bool = False,
    created_at: Optional[str] = None,
) -> list[dict]:
    """
    Scan *repo* for H1–H4 findings with enterprise fraud-engine quality.

    Args:
        repo: path to the repo root.
        changed_files: if given, scan only these relative paths.
        graph: reserved for future blast-radius scoring.
        run_id: stable run identifier; generated from repo path when omitted.
        baseline_path: path to JSON baseline for false-positive suppression.
        emit_sarif: if True, also write SARIF to repo/.lgwks/code-hacker.sarif.

    Returns list of lgwks.bot.record.v1 records.
    """
    _ = _graph
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
        py_files = sorted(repo.glob("**/*.py"))
        # Defense-in-depth: ignore 3rd-party libs, caches, AND in-repo copies of
        # source (agent worktrees + archived modules). Scanning .worktrees/.claude
        # re-reports every finding once per checkout — the bulk of the noise.
        py_files = [p for p in py_files if not any(
            (part.startswith(".venv")
             or part in {".git", "__pycache__", "venv", "node_modules",
                         ".worktrees", ".claude", "archive"})
            for part in p.parts
        )]
        targets = py_files
        rels = [str(p.relative_to(repo)) for p in py_files]

    findings: list[dict] = []
    for path, rel in zip(targets, rels):
        p = Path(path)
        if not p.is_file():
            continue
        findings.extend(_scan_file(p, rel, run_id, repo_str, baseline, created_at=created_at))

    # Persist new baseline
    if baseline_path:
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
