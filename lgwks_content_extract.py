#!/usr/bin/env python3
"""lgwks_content_extract — boilerplate-pruning HTML → clean-text extractor.

THE ONE SEAM for the "grab the core, own the use-case" HTML decision
(Director, 2026-06-21): the parser core is CPython's stdlib ``html.parser`` —
zero dependency chain (no bs4 → soupsieve, no lxml → libxml2). The *cognition*
is a node-scoring pruning pass that strips nav/chrome/ads and low-value blocks,
ported from crawl4ai's PruningContentFilter (Apache-2.0) and tuned for our
extraction. "wget but better": wget mirrors raw HTML; we prune to the core.

Reversibility contract: this module is the ONLY place a parser is chosen. If
the core is ever swapped for lxml/selectolax for raw speed, only the tree
builder here changes — every caller goes through ``extract_main_content`` /
``prune_html`` and never sees the parser. The pruned HTML is handed to the
existing canonical converter (``lgwks_html.html_to_markdown``) so downstream
output shape (markdown, links) is unchanged.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from html import escape

# Tags that are pure chrome/boilerplate or non-content — dropped wholesale
# (subtree skipped during parse, so their text never enters scoring).
_EXCLUDED_TAGS = {
    "nav", "footer", "header", "aside", "script", "style",
    "form", "iframe", "noscript", "template", "svg", "button",
}
# HTML void elements: no closing tag, no children.
_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
# class/id substrings that signal non-content regions (crawl4ai negative_patterns,
# extended for our corpora). A node whose class/id matches is penalised.
_NEGATIVE = re.compile(
    r"nav|footer|header|sidebar|ad[s_-]|comment|promo|advert|social|share|"
    r"cookie|banner|menu|widget|popup|modal|breadcrumb|pagination|related",
    re.I,
)
# Per-tag content importance (crawl4ai tag_weights; max 1.5 → normalised by /1.5).
_TAG_WEIGHTS = {
    "article": 1.5, "main": 1.4, "section": 1.0, "p": 1.0, "blockquote": 1.0,
    "pre": 1.0, "code": 0.9, "div": 0.5, "span": 0.3, "li": 0.5, "ul": 0.5,
    "ol": 0.5, "dl": 0.5, "table": 0.8, "td": 0.6, "th": 0.6,
    "h1": 1.2, "h2": 1.1, "h3": 1.0, "h4": 0.9, "h5": 0.8, "h6": 0.7,
    "figure": 0.7, "figcaption": 0.6,
}
# Composite-score metric weights (crawl4ai metric_weights).
_W_TEXT_DENSITY = 0.4
_W_LINK_DENSITY = 0.2
_W_TAG_WEIGHT = 0.2
_W_CLASS_ID = 0.1
_W_TEXT_LENGTH = 0.1
# Fixed prune threshold (crawl4ai default). Block-level nodes scoring below this
# (and not carrying enough text) are removed.
_THRESHOLD = 0.48
# A node with at least this much subtree text is always kept (a long, dense block
# is content regardless of wrapper-tag weighting).
_KEEP_TEXT_LEN = 200
# Attributes preserved into the pruned HTML (everything else is dropped — the
# downstream converter only needs links/images).
_KEEP_ATTRS = {"href", "src", "alt", "title"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None,
                 parent: "_Node | None" = None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_Node] = []
        self.parent = parent
        self.text = ""  # direct text owned by this node


class _TreeBuilder(HTMLParser):
    """Builds a lightweight DOM tree on the stdlib tokenizer, skipping excluded
    subtrees entirely (their content never reaches scoring)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("[root]")
        self.cur = self.root
        self._skip_depth = 0
        self._skip_tag: str | None = None

    def handle_starttag(self, tag: str, attrs):
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if tag in _EXCLUDED_TAGS:
            self._skip_tag = tag
            self._skip_depth = 1
            return
        node = _Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID_TAGS:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        # explicit self-closing (e.g. <img/>) — never descends
        if self._skip_depth:
            return
        node = _Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)

    def handle_endtag(self, tag: str):
        if self._skip_depth:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth == 0:
                    self._skip_tag = None
            return
        if tag in _VOID_TAGS:
            return
        # close to the nearest matching ancestor (tolerant of malformed nesting)
        n: _Node | None = self.cur
        while n is not None and n is not self.root and n.tag != tag:
            n = n.parent
        if n is not None and n is not self.root and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        if data.strip():
            self.cur.text += data


def _text_len(node: _Node) -> int:
    total = len(node.text.strip())
    for c in node.children:
        total += _text_len(c)
    return total


def _link_text_len(node: _Node) -> int:
    total = len(node.text.strip()) if node.tag == "a" else 0
    if node.tag == "a":
        # all descendant text counts as link text
        return _text_len(node)
    for c in node.children:
        total += _link_text_len(c)
    return total


def _markup_len(node: _Node) -> int:
    # cheap proxy for crawl4ai's tag_len (rendered byte size): text + tag overhead
    total = len(node.text)
    for c in node.children:
        total += _markup_len(c) + len(c.tag) + 4
    return total


def _composite_score(node: _Node) -> float:
    text_len = _text_len(node)
    if text_len == 0:
        return 0.0
    markup_len = max(_markup_len(node), 1)
    link_len = _link_text_len(node)

    text_density = min(text_len / markup_len, 1.0)
    link_density_score = 1.0 - min(link_len / text_len, 1.0)  # fewer links → higher
    tag_weight = min(_TAG_WEIGHTS.get(node.tag, 0.5) / 1.5, 1.0)
    cls_id = (node.attrs.get("class", "") + " " + node.attrs.get("id", ""))
    class_id_score = 0.0 if _NEGATIVE.search(cls_id) else 1.0
    text_length_score = min(text_len / 100.0, 1.0)

    return (
        _W_TEXT_DENSITY * text_density
        + _W_LINK_DENSITY * link_density_score
        + _W_TAG_WEIGHT * tag_weight
        + _W_CLASS_ID * class_id_score
        + _W_TEXT_LENGTH * text_length_score
    )


def _prune(node: _Node) -> None:
    """Post-order prune: drop block children that score below threshold and don't
    carry enough text on their own. Wrappers around real content survive because
    text length/density aggregate over the subtree."""
    kept: list[_Node] = []
    for child in node.children:
        _prune(child)
        if child.tag in _VOID_TAGS or child.tag == "a":
            kept.append(child)
            continue
        text_len = _text_len(child)
        if text_len == 0 and not child.children:
            continue  # empty leaf
        if text_len >= _KEEP_TEXT_LEN:
            kept.append(child)
            continue
        if _composite_score(child) >= _THRESHOLD:
            kept.append(child)
    node.children = kept


def _serialize(node: _Node, out: list[str]) -> None:
    for child in node.children:
        attrs = "".join(
            f' {k}="{escape(v, quote=True)}"'
            for k, v in child.attrs.items() if k in _KEEP_ATTRS
        )
        if child.tag in _VOID_TAGS:
            out.append(f"<{child.tag}{attrs}/>")
            continue
        out.append(f"<{child.tag}{attrs}>")
        if child.text.strip():
            out.append(escape(child.text))
        _serialize(child, out)
        out.append(f"</{child.tag}>")


def prune_html(html: str) -> str:
    """Strip chrome/boilerplate and low-value blocks; return the surviving HTML.

    Pure heuristic, deterministic, stdlib-only. Safe on malformed input."""
    if not html or not isinstance(html, str):
        return ""
    builder = _TreeBuilder()
    try:
        builder.feed(html)
        builder.close()
    except Exception:
        return html  # never fail the pipeline; fall back to raw HTML
    _prune(builder.root)
    out: list[str] = []
    _serialize(builder.root, out)
    return "".join(out)


def extract_main_content(html: str, base_url: str = "", *, max_chars: int = 0) -> str:
    """Seam entrypoint: prune boilerplate, then convert to clean markdown via the
    canonical converter. Returns markdown text (optionally length-capped)."""
    from lgwks_html import html_to_markdown

    pruned = prune_html(html)
    text, _, _, _ = html_to_markdown(pruned, base_url)
    if not text.strip():
        # pruning removed everything (e.g. tiny page) — fall back to full convert
        text, _, _, _ = html_to_markdown(html, base_url)
    return text[:max_chars] if max_chars and max_chars > 0 else text
