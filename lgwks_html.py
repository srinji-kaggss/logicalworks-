"""
lgwks_html — robust, deterministic HTML-to-Markdown and semantic link/table parser.

Designed to serve as a global, schema-free page content extractor (inspired by Crawl4AI
and Firecrawl).
- Ignores layout, navigation, script, style, and other non-content tags.
- Strips cookie banners, headers, footers, and generic page chrome.
- Formats headings, paragraphs, lists, bold/italic, and links.
- Reconstructs complex tables with rowspan and colspan inheritance.
"""

from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

# Unwanted elements that we completely ignore (including their contents)
IGNORE_TAGS = {
    "script", "style", "link", "meta", "svg", "canvas", "iframe", "noscript",
    "aside", "nav", "header", "footer", "form", "button", "dialog"
}

# Chrome-like class/id patterns that we skip to clean the content area
CHROME_CLASS_RE = re.compile(
    r"(topnav|dropdown|toolbar|breadcrumb|sidebar|banner|cookie|gdpr|modal|popup|menu|ad-container|navbar|footer|header|social)",
    re.I
)


class HTMLToMarkdownParser(HTMLParser):
    def __init__(self, base_url: str = "", profile: dict | None = None):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.markdown_parts: list[str] = []
        self.tag_stack: list[tuple[str, bool]] = []  # (tag_name, is_ignored_boundary)
        self.ignore_depth = 0
        self.current_href: str | None = None
        self.link_text_parts: list[str] = []
        self.in_link = False
        
        self.title_parts: list[str] = []
        self.links_found: list[dict[str, str]] = []
        
        # Load profile settings
        if profile and "dom" in profile:
            self.chrome_tags = set(profile["dom"].get("chrome_tags", IGNORE_TAGS))
            patterns = profile["dom"].get("chrome_class_patterns", [])
            self.chrome_class_re = re.compile(r"(" + "|".join(patterns) + ")", re.I) if patterns else None
        else:
            self.chrome_tags = IGNORE_TAGS
            self.chrome_class_re = CHROME_CLASS_RE
            
        # Table tracking
        self.in_table = False
        self.table_rows: list[list[dict]] = []  # list of lists of cells
        self.current_row: list[dict] = []
        self.current_cell: dict | None = None
        
        # Formatting
        self.in_bold = False
        self.in_italic = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        tag = tag.lower()
        attrs_dict = {k: (v or "") for k, v in attrs}
        classes = attrs_dict.get("class", "")
        element_id = attrs_dict.get("id", "")
        
        is_chrome = bool(self.chrome_class_re.search(classes) or self.chrome_class_re.search(element_id)) if self.chrome_class_re else False
        is_ignored_boundary = False
        
        if tag in self.chrome_tags or is_chrome:
            self.ignore_depth += 1
            is_ignored_boundary = True
            
        self.tag_stack.append((tag, is_ignored_boundary))
        
        if self.ignore_depth > 0:
            return

        # Formatting / Structural blocks
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self.markdown_parts.append(f"\n\n{'#' * level} ")
        elif tag in {"p", "div", "blockquote", "section", "article"}:
            # Avoid duplicating newlines if we just appended one
            if self.markdown_parts and not self.markdown_parts[-1].endswith("\n"):
                self.markdown_parts.append("\n\n")
        elif tag == "br":
            self.markdown_parts.append("\n")
        elif tag == "li":
            is_ordered = False
            # Find the nearest list container in the stack
            for parent_tag, _ in reversed(self.tag_stack[:-1]):  # exclude current 'li' tag
                if parent_tag == "ol":
                    is_ordered = True
                    break
                elif parent_tag == "ul":
                    break
            if is_ordered:
                self.markdown_parts.append("\n1. ")
            else:
                self.markdown_parts.append("\n- ")
        elif tag in {"strong", "b"}:
            self.in_bold = True
            self.markdown_parts.append("**")
        elif tag in {"em", "i"}:
            self.in_italic = True
            self.markdown_parts.append("*")
        elif tag == "a":
            href = attrs_dict.get("href", "")
            if href and not href.startswith(("javascript:", "mailto:", "tel:")):
                if self.base_url:
                    href = urljoin(self.base_url, href)
                self.current_href = href
                self.in_link = True
                self.link_text_parts = []
        elif tag == "table":
            self.in_table = True
            self.table_rows = []
        elif tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"}:
            self.current_cell = {
                "text_parts": [],
                "rowspan": int(attrs_dict.get("rowspan", "1") or "1"),
                "colspan": int(attrs_dict.get("colspan", "1") or "1"),
                "is_header": tag == "th"
            }

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        # Find matching tag in stack
        found_idx = -1
        for idx in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[idx][0] == tag:
                found_idx = idx
                break
                
        if found_idx == -1:
            return
            
        popped = self.tag_stack[found_idx:]
        self.tag_stack = self.tag_stack[:found_idx]
        
        for _, is_ignored in popped:
            if is_ignored:
                self.ignore_depth = max(0, self.ignore_depth - 1)
                
        if self.ignore_depth > 0:
            return

        # Formatting closing
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.markdown_parts.append("\n\n")
        elif tag in {"p", "div", "blockquote", "section", "article"}:
            if self.markdown_parts and not self.markdown_parts[-1].endswith("\n"):
                self.markdown_parts.append("\n\n")
        elif tag in {"strong", "b"}:
            self.in_bold = False
            self.markdown_parts.append("**")
        elif tag in {"em", "i"}:
            self.in_italic = False
            self.markdown_parts.append("*")
        elif tag == "a":
            if self.in_link:
                text = " ".join(self.link_text_parts).strip()
                if self.current_href:
                    self.links_found.append({"href": self.current_href, "text": text[:80]})
                    link_md = f"[{text or 'link'}]({self.current_href})"
                    if self.current_cell:
                        self.current_cell["text_parts"].append(link_md)
                    else:
                        self.markdown_parts.append(link_md)
                elif text:
                    if self.current_cell:
                        self.current_cell["text_parts"].append(text)
                    else:
                        self.markdown_parts.append(text)
                self.in_link = False
                self.current_href = None
        elif tag == "table":
            if self.in_table:
                table_md = self._render_table()
                self.markdown_parts.append("\n\n" + table_md + "\n\n")
                self.in_table = False
        elif tag == "tr":
            if self.in_table:
                self.table_rows.append(self.current_row)
        elif tag in {"td", "th"}:
            if self.current_cell:
                cell_text = " ".join(self.current_cell["text_parts"]).strip()
                self.current_cell["text"] = cell_text
                self.current_row.append(self.current_cell)
                self.current_cell = None

    def handle_data(self, data: str):
        if self.ignore_depth > 0:
            return
            
        clean_data = html_lib.unescape(data)
        
        # Collect page title
        if self.tag_stack and self.tag_stack[-1][0] == "title":
            self.title_parts.append(clean_data.strip())
            return
            
        if self.in_link:
            self.link_text_parts.append(clean_data)
        elif self.current_cell:
            self.current_cell["text_parts"].append(clean_data)
        else:
            self.markdown_parts.append(clean_data)

    def _render_table(self) -> str:
        if not self.table_rows:
            return ""
            
        # Reconstruct grid taking rowspans and colspans into account
        grid: list[list[str]] = []
        span_carry: dict[int, tuple[str, int]] = {}  # col_idx -> (text, remaining_rows)
        
        for row_idx, cells in enumerate(self.table_rows):
            col_idx = 0
            row_data: list[str] = []
            
            while True:
                # 1. Apply active carries
                while col_idx in span_carry:
                    carried_text, remaining = span_carry[col_idx]
                    row_data.append(carried_text)
                    if remaining > 1:
                        span_carry[col_idx] = (carried_text, remaining - 1)
                    else:
                        del span_carry[col_idx]
                    col_idx += 1
                    
                # 2. If we run out of cells, check remaining carries
                if not cells:
                    any_more_carries = any(c_idx >= col_idx for c_idx in span_carry)
                    if not any_more_carries:
                        break
                    continue
                    
                cell = cells.pop(0)
                text = cell["text"]
                rowspan = cell["rowspan"]
                colspan = cell["colspan"]
                
                # Register rowspan carry
                if rowspan > 1:
                    span_carry[col_idx] = (text, rowspan - 1)
                    
                # Apply colspan
                for _ in range(colspan):
                    row_data.append(text)
                    col_idx += 1
                    
            grid.append(row_data)
            
        if not grid:
            return ""
            
        max_cols = max(len(r) for r in grid)
        for r in grid:
            while len(r) < max_cols:
                r.append("")
                
        lines: list[str] = []
        for i, row in enumerate(grid):
            # Escape pipe symbols in cell text to prevent markdown table breakage
            escaped_row = [cell.replace("|", "\\|") for cell in row]
            lines.append("| " + " | ".join(escaped_row) + " |")
            if i == 0:
                lines.append("| " + " | ".join("---" for _ in range(max_cols)) + " |")
                
        return "\n".join(lines)


def html_to_markdown(html_str: str, base_url: str = "") -> tuple[str, str, list[dict[str, str]]]:
    """Convert HTML string to clean Markdown text, extracting the title and unique links."""
    from lgwks_site_profile import load_profile
    profile = load_profile(base_url) if base_url else None
    parser = HTMLToMarkdownParser(base_url, profile=profile)
    try:
        parser.feed(html_str)
    except Exception:
        pass
    
    # 1. Title
    title = " ".join(parser.title_parts).strip()
    
    # 2. Text (Markdown)
    markdown = "".join(parser.markdown_parts)
    
    # Clean up whitespace and newlines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = re.sub(r"[ \t]+", " ", markdown)
    markdown = re.sub(r"\n +", "\n", markdown)
    markdown = markdown.strip()
    
    # 3. Links: deduplicate by href
    seen = set()
    links = []
    for link in parser.links_found:
        href = link["href"]
        if href not in seen:
            seen.add(href)
            links.append(link)
            
    return markdown, title, links




