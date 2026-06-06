"""
lgwks_bot_code_hacker — U5: deterministic security-focused static analyzer.

Scans repo Python files for four surface families:
  H1 dangerous shell execution
  H2 unsafe file mutation
  H3 unbounded network egress
  H4 secret exposure / logging risk

No LLM calls. No internet. Fail closed on parse errors (emits analyzer-failure records).
Every finding is a valid lgwks.bot.record.v1 record linking to a repo-local path.
"""

from __future__ import annotations

import ast
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import lgwks_project_artifacts as artifacts

_BOT = "code_hacker"

_SUBPROCESS_ATTRS = {"Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
_BROAD_DELETE = {"rmtree", "remove", "unlink", "rmdir"}
_NET_MODULES = frozenset({"requests", "urllib.request", "httpx", "aiohttp", "http.client", "urllib3"})
_NET_TOPS = frozenset(m.split(".")[0] for m in _NET_MODULES)
# //why: modules with these path tokens are expected to call the network
_NET_SAFE_RE = re.compile(r"(portal|network|search|fetch|browser|public|cohere|provider|auth_runtime)", re.I)
_SECRET_RE = re.compile(r"(token|secret|key|password|api_key|credential|auth|bearer)", re.I)
_LOG_ATTRS = frozenset({"debug", "info", "warning", "error", "critical", "exception", "log"})
_LOG_OBJ_RE = re.compile(r"^(logging|logger|log)", re.I)


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
) -> dict:
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
        "created_at": _ts(),
    }


def _failure_record(run_id: str, repo: str, file: str, reason: str) -> dict:
    return _make(
        run_id=run_id, repo=repo, file=file,
        kind="analyzer_failure",
        summary=f"parse error in {file}: {reason[:120]}",
        severity="info",
        confidence=1.0,
        evidence=[{"type": "trace", "name": "error", "value": reason[:300]}],
        tags=["analyzer", "parse-error"],
    )


def _is_net_safe(path: str) -> bool:
    return bool(_NET_SAFE_RE.search(path))


class _Visitor(ast.NodeVisitor):
    """Single-pass H1-H4 visitor over one Python file."""

    def __init__(self, rel: str, run_id: str, repo: str) -> None:
        self.rel = rel
        self.run_id = run_id
        self.repo = repo
        self.findings: list[dict] = []
        self._secret_vars: set[str] = set()
        self._net_safe = _is_net_safe(rel)

    def _add(self, kind: str, summary: str, severity: str, confidence: float,
             evidence: list[dict], tags: list[str], lineno: int, symbol: Optional[str] = None) -> None:
        # lineno injected into evidence if not already present
        if not any(e.get("name") == "lineno" for e in evidence):
            evidence = [{"type": "file_excerpt", "name": "lineno", "value": lineno}] + evidence
        self.findings.append(_make(
            run_id=self.run_id, repo=self.repo, file=self.rel,
            kind=kind, summary=summary, severity=severity, confidence=confidence,
            evidence=evidence, tags=tags, symbol=symbol,
        ))

    # ── H1: dangerous shell execution ────────────────────────────────────────

    def _check_h1(self, node: ast.Call) -> None:
        func = node.func
        ln = node.lineno

        # os.system(...)
        if (isinstance(func, ast.Attribute) and func.attr == "system"
                and isinstance(func.value, ast.Name) and func.value.id == "os"):
            self._add("dangerous_shell_exec", f"os.system() call at line {ln}",
                      "high", 0.9, [], ["shell", "exec", "h1"], ln)
            return

        # subprocess.* variants
        if isinstance(func, ast.Attribute) and func.attr in _SUBPROCESS_ATTRS:
            obj = func.value
            if isinstance(obj, ast.Name) and obj.id in {"subprocess", "sp"}:
                shell_true = any(
                    isinstance(kw.value, ast.Constant) and kw.value.value is True
                    for kw in node.keywords if kw.arg == "shell"
                )
                string_cmd = bool(node.args) and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp))
                if shell_true:
                    self._add("dangerous_shell_exec", f"subprocess.{func.attr}(shell=True) at line {ln}",
                              "critical", 0.9, [], ["shell", "exec", "h1"], ln)
                elif string_cmd:
                    self._add("dangerous_shell_exec",
                              f"subprocess.{func.attr}() with string-built cmd at line {ln}",
                              "high", 0.7, [], ["shell", "exec", "h1"], ln)

        # eval/exec with dynamic arg
        if isinstance(func, ast.Name) and func.id in {"eval", "exec"}:
            if node.args and not isinstance(node.args[0], ast.Constant):
                self._add("dangerous_shell_exec", f"{func.id}() with dynamic argument at line {ln}",
                          "critical", 0.9, [], ["eval", "exec", "h1"], ln)

    # ── H2: unsafe file mutation ──────────────────────────────────────────────

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
                      "medium", 0.7, [], ["network", "egress", "h3"], lineno)

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._flag_net_import(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module:
            self._flag_net_import(node.module, node.lineno)
        self.generic_visit(node)

    # ── H4: secret exposure / logging risk ───────────────────────────────────

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and _SECRET_RE.search(tgt.id):
                self._secret_vars.add(tgt.id)
        self.generic_visit(node)

    def _leaked_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name) and (
            _SECRET_RE.search(node.id) or node.id in self._secret_vars
        ):
            return node.id
        if isinstance(node, ast.JoinedStr):
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and (
                    _SECRET_RE.search(child.id) or child.id in self._secret_vars
                ):
                    return child.id
        return None

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
        fname = "print" if is_print else f"{func.value.id}.{func.attr}"  # type: ignore[union-attr]
        for arg in node.args:
            leaked = self._leaked_name(arg)
            if leaked:
                self._add("secret_exposure_risk",
                          f"possible credential '{leaked}' in {fname}() at line {ln}",
                          "high", 0.7,
                          [{"type": "trace", "name": "leaked_name", "value": leaked}],
                          ["secret", "logging", "h4"], ln)
                return

    # ── combined Call dispatch ────────────────────────────────────────────────

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self._check_h1(node)
        self._check_h2(node)
        self._check_h4(node)
        self.generic_visit(node)


def _scan_file(path: Path, rel: str, run_id: str, repo: str) -> list[dict]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [_failure_record(run_id, repo, rel, str(exc))]
    except Exception as exc:
        return [_failure_record(run_id, repo, rel, str(exc))]
    v = _Visitor(rel, run_id, repo)
    v.visit(tree)
    return v.findings


def run(
    repo: Path | str,
    changed_files: Optional[list[str]] = None,
    _graph=None,  # reserved; unused in v1 — graph metrics could boost severity later
    run_id: Optional[str] = None,
) -> list[dict]:
    """
    Scan *repo* for H1–H4 findings.

    Args:
        repo: path to the repo root.
        changed_files: if given, scan only these relative paths.
        graph: reserved for future blast-radius scoring.
        run_id: stable run identifier; generated from repo path when omitted.

    Returns list of lgwks.bot.record.v1 records (valid or analyzer-failure).
    """
    _ = _graph
    repo = Path(repo).resolve()
    repo_str = str(repo)
    if run_id is None:
        run_id = "code-hacker:" + _run_seed(repo_str)

    if changed_files is not None:
        targets = [repo / f for f in changed_files if f.endswith(".py")]
        rels = [f for f in changed_files if f.endswith(".py")]
    else:
        py_files = sorted(repo.glob("**/*.py"))
        # //why: skip venv/.git/__pycache__ to avoid scanning installed packages
        py_files = [p for p in py_files if not any(
            part in {".git", "__pycache__", ".venv", "venv", "node_modules"}
            for part in p.parts
        )]
        targets = py_files
        rels = [str(p.relative_to(repo)) for p in py_files]

    findings: list[dict] = []
    for path, rel in zip(targets, rels):
        p = Path(path)
        if not p.is_file():
            continue
        findings.extend(_scan_file(p, rel, run_id, repo_str))

    return findings
