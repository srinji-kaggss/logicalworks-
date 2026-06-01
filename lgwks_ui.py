"""
lgwks_ui — our own terminal visual language. Deliberately NOT Claude Code.

Identity (Director: "visually different from Claude Code"):
  • palette  : slate (structure) · cream (text) · emerald (accent) — never orange.  [project_brand_palette]
  • silhouette: a left SPINE (┃) the work sprawls off — not rounded boxes / not a chat stream.
  • motion   : the data grows DOWN (depth/decomposition) and OUT (breadth) off the spine;
               synthesis ("up") is rendered LAST, after a convergence rule — up-after-down made visible.
  • glyphs   : ◇◈◆✦ phase marks (ours), ▾ down · ▸ out · ▴ up direction marks.

Zero-dependency ANSI. TTY-aware: degrades to clean plain text when piped or NO_COLOR is set, so the
machine surface (--json, pipes) is never polluted by escape codes.
"""

from __future__ import annotations

import os
import sys

# 256-colour brand palette (slate · cream · emerald + caution/danger that stay in-family, not red/yellow).
SLATE, SLATE_DIM = 67, 60
CREAM, CREAM_DIM = 230, 187
EMERALD, EMERALD_DIM = 78, 36
AMBER, RUST, MUTED = 179, 167, 245

_SPINE = "┃"


def color_on(stream=sys.stdout) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def fg(s: str, code: int, *, on: bool, bold: bool = False) -> str:
    if not on:
        return s
    b = "1;" if bold else ""
    return f"\x1b[{b}38;5;{code}m{s}\x1b[0m"


def rule(width: int = 64, ch: str = "━", code: int = SLATE_DIM, *, on: bool) -> str:
    return fg(ch * width, code, on=on)


def band(verb: str, subtitle: str = "", *, on: bool) -> list[str]:
    """Header band — a heavy rule + the verb in emerald + subtitle in cream-dim. Not a box."""
    line = fg("◆ ", EMERALD, on=on, bold=True) + fg(verb, EMERALD, on=on, bold=True)
    if subtitle:
        line += fg("   " + subtitle, CREAM_DIM, on=on)
    return [rule(on=on), line, rule(on=on)]


def _meter(value01: float, width: int) -> tuple[int, int]:
    filled = max(0, min(width, round(value01 * width)))
    return filled, width - filled


def scale(label: str, value: float, lpole: str, rpole: str, *, signed: bool = False, on: bool,
          width: int = 16) -> str:
    """A steering dial as a bar. signed=True maps -1..1 with a centred marker (the lens)."""
    if signed:
        pos = max(0, min(width, round((value + 1) / 2 * width)))
        track = ["─"] * width
        track[min(width - 1, pos)] = "◆"
        bar = fg("".join(track), EMERALD, on=on)
        val = f"{value:+.2f}"
    else:
        f, e = _meter(value, width)
        bar = fg("█" * f, EMERALD, on=on) + fg("░" * e, SLATE_DIM, on=on)
        val = f"{value:.2f}"
    lab = fg(f"{label:<13}", CREAM_DIM, on=on)
    poles = fg(f" {lpole}", MUTED, on=on) + " ▕" + bar + "▏ " + fg(rpole, MUTED, on=on)
    return f"  {_SPINE} {lab}{poles} {fg(val, CREAM, on=on)}"


def spine(text: str = "", *, on: bool, pad: int = 1) -> str:
    return f"  {fg(_SPINE, SLATE, on=on)}{' ' * pad}{text}" if text else f"  {fg(_SPINE, SLATE, on=on)}"


_SEV = {"danger": (RUST, "✗"), "caution": (AMBER, "▲"), "info": (MUTED, "·")}


def branch(severity: str, head: str, depth: int, *, last: bool, on: bool) -> str:
    """A finding as a down+out tree node hanging off the spine. depth = how far DOWN; siblings = OUT."""
    code, mark = _SEV.get(severity, (CREAM, "·"))
    connector = ("┗" if last else "┣") + "━ "
    indent = "  " * depth
    return (f"  {fg(_SPINE, SLATE, on=on)} {fg(indent + connector, SLATE_DIM, on=on)}"
            f"{fg(mark, code, on=on, bold=True)} {fg(head, CREAM, on=on)}")


def twig(text: str, depth: int, kind: str, *, on: bool) -> str:
    """A sub-line under a finding: kind 'next' (→ action) or 'proof' (∵ citation)."""
    glyph, code = ("→", EMERALD_DIM) if kind == "next" else ("∵", MUTED)
    indent = "  " * (depth + 1)
    return f"  {fg(_SPINE, SLATE, on=on)} {fg(indent + glyph, code, on=on)} {fg(text, CREAM_DIM, on=on)}"


def convergence(label: str, *, on: bool) -> list[str]:
    """The 'up' marker — synthesis rendered AFTER the down/out sprawl."""
    return [spine(on=on),
            f"  {fg('┗━▴ ', EMERALD, on=on)}{fg(label, EMERALD, on=on, bold=True)}"]


def footer(mark: str, *, on: bool) -> str:
    return fg(mark, SLATE_DIM, on=on)
