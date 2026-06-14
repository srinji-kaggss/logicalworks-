from __future__ import annotations

import pytest
from lgwks_html import html_to_markdown


def test_html_to_markdown_basic():
    html_input = """
    <html>
      <head>
        <title>Test Page Title</title>
        <style>body { color: red; }</style>
      </head>
      <body>
        <nav class="topnav">Home | About</nav>
        <h1>Main Title</h1>
        <p>This is a <strong>bold</strong> paragraph and <em>italic</em> text.</p>
        <div>Here is some text in a div.</div>
        <script>console.log("hello");</script>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """
    markdown, title, links, _media = html_to_markdown(html_input)

    assert title == "Test Page Title"
    assert "Home" not in markdown
    assert "Copyright" not in markdown
    assert "console.log" not in markdown
    assert "# Main Title" in markdown
    assert "This is a **bold** paragraph and *italic* text." in markdown
    assert "Here is some text in a div." in markdown


def test_html_to_markdown_links():
    html_input = """
    <p>Check out <a href="/docs/guide.html">the guide</a> and the <a href="https://example.com/about">about page</a>.</p>
    """
    markdown, _, links, _media = html_to_markdown(html_input, base_url="https://example.com/start/")
    
    assert "[the guide](https://example.com/docs/guide.html)" in markdown
    assert "[about page](https://example.com/about)" in markdown
    assert {"href": "https://example.com/docs/guide.html", "text": "the guide"} in links
    assert {"href": "https://example.com/about", "text": "about page"} in links


def test_html_to_markdown_lists():
    html_input = """
    <ul>
      <li>First bullet</li>
      <li>Second bullet</li>
    </ul>
    """
    markdown, _, _, _ = html_to_markdown(html_input)
    assert "- First bullet" in markdown
    assert "- Second bullet" in markdown


def test_html_to_markdown_table_colspan_rowspan():
    html_input = """
    <table>
      <tr>
        <th>Col 1</th>
        <th>Col 2</th>
        <th>Col 3</th>
      </tr>
      <tr>
        <td rowspan="2">Rowspan 1-2 Col 1</td>
        <td>Row 1 Col 2</td>
        <td colspan="2">Colspan 3-4</td>
      </tr>
      <tr>
        <td>Row 2 Col 2</td>
        <td>Row 2 Col 3</td>
      </tr>
    </table>
    """
    markdown, _, _, _ = html_to_markdown(html_input)

    lines = [ln.strip() for ln in markdown.split("\n") if ln.strip()]
    assert "| Col 1 | Col 2 | Col 3 | |" in lines
    assert "| --- | --- | --- | --- |" in lines
    assert "| Rowspan 1-2 Col 1 | Row 1 Col 2 | Colspan 3-4 | Colspan 3-4 |" in lines
    assert "| Rowspan 1-2 Col 1 | Row 2 Col 2 | Row 2 Col 3 | |" in lines
