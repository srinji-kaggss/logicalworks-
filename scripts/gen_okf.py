#!/usr/bin/env python3
"""gen_okf — render `docs/` as a conformant Open Knowledge Format bundle (stdlib only).

LGWKS OKF is **Google Cloud's Open Knowledge Format (OKF v0.1, 2026-06-12)**, adopted
verbatim for our documentation knowledge bundle. See `docs/concepts/knowledge-format.md`
for the lineage (and how it relates to the browser engine's same-named *Optimized*
Knowledge Format and the lgwks research "OKF artifact" — different sibling artifacts).

The spec (GoogleCloudPlatform/knowledge-catalog/okf/SPEC.md) in one breath: a Knowledge
Bundle is a directory tree of markdown **concepts**, each with a YAML frontmatter block
whose ONLY required field is `type`; `index.md` files give **progressive disclosure**;
`log.md` records history; plain markdown links form a cross-linked knowledge graph.

This generator does for docs what `gen_navmap.py` does for code: the bundle is
GENERATED FROM SOURCE, never hand-maintained, so it cannot rot. Frontmatter is derived
deterministically (a human can reconstruct every field with the rules below), index
files are synthesized from frontmatter, and `--check` is a CI conformance gate (§9).

Modes:
  --check   validate OKF v0.1 conformance; exit 1 on any violation (the CI gate).
  --write   inject derived frontmatter where missing + (re)generate every index.md.
  (default) dry-run: report what --write would change, touch nothing.

Run from repo root:  python3 scripts/gen_okf.py --write
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "docs"
OKF_VERSION = "0.1"
RESERVED = {"index.md", "log.md"}

# ── Type derivation (deterministic; the ONE place a concept's `type` is decided) ──
# A human reconstructs `type` from the path with these ordered rules — no model, no
# magic. Producers can override by hand-setting `type` in a doc's frontmatter; the
# generator preserves any existing non-empty type.
def derive_type(rel: Path) -> str:
    parts = [p.lower() for p in rel.parts]
    name = rel.name.lower()
    subdir = parts[0] if len(parts) > 1 else ""
    if "archive" in parts:
        return "Archive"
    if name.startswith("adr-") or "/adr" in "/".join(parts) or name == "adr.md":
        return "ADR"
    if subdir == "schemas" or "schema" in name:
        return "Schema"
    if subdir in ("research", "research-artifacts"):
        return "Research"
    if subdir == "handoff" or "handoff" in name:
        return "Handoff"
    if subdir == "proofs" or "proof" in name:
        return "Proof"
    if subdir == "navmap":
        return "Navmap"
    if "-law" in name or "law" == subdir:
        return "Law"
    if "spec" in name:
        return "Spec"
    if "plan" in name or subdir == "axiom-plans":
        return "Plan"
    if "thesis" in name:
        return "Thesis"
    return "Reference"


def humanize(stem: str) -> str:
    return re.sub(r"[-_]+", " ", stem).strip().title()


_HEADING = re.compile(r"^#{1,6}\s+(.*)$")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
# strip code-span / emphasis / blockquote markers, but NOT underscores — intra-word
# underscores are load-bearing here (identifiers like `lgwks_pipeline.py`), and `_`
# emphasis is vanishingly rare in these docs.
_INLINE = re.compile(r"[`*>]+")


def derive_title(body: str, stem: str) -> str:
    for line in body.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            return _strip_inline(m.group(1))[:120]
    return humanize(stem)


def derive_description(body: str) -> str:
    """First substantive prose line: not a heading, list bullet, fence, or table."""
    in_fence = False
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith(("#", "-", "*", "|", ">", "<!--", "1.", "2.")):
            continue
        text = _strip_inline(line)
        if len(text) < 12:
            continue
        # one sentence, capped
        text = re.split(r"(?<=[.!?])\s", text)[0]
        return text[:200].rstrip()
    return ""


def _strip_inline(s: str) -> str:
    s = _MD_LINK.sub(r"\1", s)
    s = _INLINE.sub("", s)
    return s.strip()


def git_timestamp(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=10,
        )
        stamp = out.stdout.strip()
        if stamp:
            return stamp
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return ""


# ── Minimal frontmatter IO (stdlib only — no yaml dep, like gen_navmap) ──────────
# We parse only the small OKF surface we emit (scalar key: value, key: [a, b]); rich
# YAML is out of scope and producers needing it can hand-author. Parsing is just for
# IDEMPOTENCY (don't clobber an existing block) and conformance (§9 needs a non-empty
# `type`), so a tolerant line parser is sufficient and predictable.
def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n") == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm: dict[str, str] = {}
    for ln in lines[1:end]:
        if ":" in ln and not ln.startswith((" ", "\t", "#")):
            k, _, v = ln.partition(":")
            fm[k.strip()] = v.strip()
    body = "".join(lines[end + 1:]).lstrip("\n")
    return fm, body


def emit_frontmatter(fm: dict[str, str]) -> str:
    order = ["type", "title", "description", "resource", "tags", "timestamp", "okf_version"]
    keys = [k for k in order if k in fm] + [k for k in fm if k not in order]
    out = ["---"]
    for k in keys:
        out.append(f"{k}: {fm[k]}")
    out.append("---")
    return "\n".join(out) + "\n\n"


def yaml_list(items: list[str]) -> str:
    return "[" + ", ".join(items) + "]"


# ── Concept model ────────────────────────────────────────────────────────────────
class Concept:
    def __init__(self, path: Path):
        self.path = path
        self.rel = path.relative_to(BUNDLE)
        raw = path.read_text(encoding="utf-8", errors="replace")
        self.fm, self.body = split_frontmatter(raw)
        self.had_fm = bool(self.fm)

    @property
    def concept_id(self) -> str:
        return str(self.rel.with_suffix(""))

    def derived_frontmatter(self) -> dict[str, str]:
        fm = dict(self.fm)
        if not fm.get("type"):
            fm["type"] = derive_type(self.rel)
        if not fm.get("title"):
            fm["title"] = derive_title(self.body, self.path.stem)
        if not fm.get("description"):
            desc = derive_description(self.body)
            if desc:
                fm["description"] = desc
        if not fm.get("tags"):
            tags = sorted({p for p in self.rel.parts[:-1]} | {fm["type"].lower().replace(" ", "-")})
            if tags:
                fm["tags"] = yaml_list(tags)
        if not fm.get("timestamp"):
            ts = git_timestamp(self.path)
            if ts:
                fm["timestamp"] = ts
        return fm

    def title(self) -> str:
        return self.fm.get("title") or derive_title(self.body, self.path.stem)

    def description(self) -> str:
        return self.fm.get("description") or derive_description(self.body)


def iter_concepts() -> list[Concept]:
    out = []
    for p in sorted(BUNDLE.rglob("*.md")):
        if p.name in RESERVED:
            continue
        out.append(Concept(p))
    return out


# ── index.md synthesis (§6 progressive disclosure) ───────────────────────────────
def build_index(directory: Path, is_root: bool) -> str:
    """Synthesize one directory's index.md from its children's frontmatter."""
    concepts: list[Concept] = []
    subdirs: list[Path] = []
    for child in sorted(directory.iterdir()):
        if child.is_dir():
            if any(child.rglob("*.md")):
                subdirs.append(child)
        elif child.suffix == ".md" and child.name not in RESERVED:
            concepts.append(Concept(child))

    lines: list[str] = []
    if is_root:
        lines.append(emit_frontmatter({"okf_version": f'"{OKF_VERSION}"'}).rstrip("\n"))
        lines.append("")
        lines.append("# lgwks — Knowledge Bundle")
        lines.append("")
        lines.append("> Generated by `scripts/gen_okf.py` from concept frontmatter — "
                     "**do not hand-edit**. Open Knowledge Format (OKF) v" + OKF_VERSION +
                     ", Google-Cloud-inspired; see "
                     "[concepts/knowledge-format](concepts/knowledge-format.md).")
        lines.append("")
    else:
        lines.append(f"# {humanize(directory.name)}")
        lines.append("")

    # concepts grouped by type
    by_type: dict[str, list[Concept]] = {}
    for c in concepts:
        by_type.setdefault(c.derived_frontmatter()["type"], []).append(c)
    for typ in sorted(by_type):
        lines.append(f"## {typ}")
        lines.append("")
        for c in sorted(by_type[typ], key=lambda x: x.title().lower()):
            desc = c.description()
            tail = f" — {desc}" if desc else ""
            lines.append(f"* [{c.title()}]({c.path.name}){tail}")
        lines.append("")

    if subdirs:
        lines.append("## Subdirectories")
        lines.append("")
        for d in subdirs:
            n = sum(1 for _ in d.rglob("*.md"))
            lines.append(f"* [{humanize(d.name)}]({d.name}/) — {n} concept(s)")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def dirs_with_concepts() -> list[Path]:
    seen = {BUNDLE}
    for p in BUNDLE.rglob("*.md"):
        if p.name in RESERVED:
            continue
        seen.add(p.parent)
    return sorted(seen)


# ── modes ─────────────────────────────────────────────────────────────────────────
def cmd_write() -> int:
    changed = 0
    for c in iter_concepts():
        fm = c.derived_frontmatter()
        if c.had_fm and c.fm.get("type"):
            continue  # already conformant — preserve hand-authored frontmatter
        new = emit_frontmatter(fm) + c.body.rstrip("\n") + "\n"
        c.path.write_text(new, encoding="utf-8")
        changed += 1
        print(f"  + frontmatter: {c.rel}  (type={fm['type']})")
    idx = 0
    for d in dirs_with_concepts():
        (d / "index.md").write_text(build_index(d, is_root=(d == BUNDLE)), encoding="utf-8")
        idx += 1
    print(f"\nwrote frontmatter into {changed} concept(s); regenerated {idx} index.md file(s)")
    return 0


def cmd_check() -> int:
    violations: list[str] = []
    concepts = iter_concepts()
    for c in concepts:
        if not c.fm:
            violations.append(f"{c.rel}: no YAML frontmatter (§9.1)")
        elif not c.fm.get("type"):
            violations.append(f"{c.rel}: frontmatter has no non-empty `type` (§9.2)")
    if not (BUNDLE / "index.md").exists():
        violations.append("docs/index.md: bundle-root index missing (§6)")
    if violations:
        print(f"OKF conformance: {len(violations)} violation(s) in {len(concepts)} concepts\n")
        for v in violations:
            print(f"  ✗ {v}")
        return 1
    print(f"OKF v{OKF_VERSION} conformant: {len(concepts)} concepts, all frontmatter valid ✓")
    return 0


def cmd_verify() -> int:
    """Conformance (§9) AND freshness — the 'docs updated before CI' gate.

    Fails if any concept lacks a `type` (would be injected by --write) or if any
    generated `index.md` is stale (its body changed but the bundle wasn't
    regenerated). A green run means: the bundle is conformant and current. CI does
    not care WHO ran --write (human, agent, or eventually the daemon); only that it
    was run after the docs changed."""
    rc = cmd_check()
    stale: list[str] = []
    for c in iter_concepts():
        if not (c.had_fm and c.fm.get("type")):
            stale.append(f"{c.rel}: frontmatter not generated (run gen_okf.py --write)")
    for d in dirs_with_concepts():
        want = build_index(d, is_root=(d == BUNDLE))
        idx = d / "index.md"
        have = idx.read_text(encoding="utf-8") if idx.exists() else ""
        if have != want:
            stale.append(f"{idx.relative_to(BUNDLE)}: index stale (run gen_okf.py --write)")
    if stale:
        print(f"\nOKF freshness: {len(stale)} stale artifact(s) — docs not updated before CI:")
        for s in stale:
            print(f"  ✗ {s}")
        return 1
    if rc == 0:
        print("OKF bundle is fresh (indexes + frontmatter current) ✓")
    return rc


def cmd_dryrun() -> int:
    missing = [c for c in iter_concepts() if not (c.had_fm and c.fm.get("type"))]
    print(f"dry-run: {len(missing)} concept(s) would gain derived frontmatter; "
          f"{len(dirs_with_concepts())} index.md would be (re)generated.")
    for c in missing[:20]:
        fm = c.derived_frontmatter()
        print(f"  {c.rel}  type={fm['type']!r}  title={fm.get('title','')!r}")
    if len(missing) > 20:
        print(f"  … +{len(missing) - 20} more")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_okf", description="render docs/ as an OKF bundle")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--write", action="store_true", help="inject frontmatter + regenerate indexes")
    g.add_argument("--check", action="store_true", help="validate OKF conformance (§9)")
    g.add_argument("--verify", action="store_true", help="conformance + freshness (the CI gate)")
    args = ap.parse_args(argv)
    if not BUNDLE.exists():
        print(f"no bundle at {BUNDLE}", file=sys.stderr)
        return 2
    if args.verify:
        return cmd_verify()
    if args.check:
        return cmd_check()
    if args.write:
        return cmd_write()
    return cmd_dryrun()


if __name__ == "__main__":
    raise SystemExit(main())
