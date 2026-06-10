//! Deterministic HTML → {title, canonical, links, markdown text}. Uses scraper's
//! document-order selection over content tags so script/style/nav boilerplate is
//! excluded and the output is reproducible. Links are resolved to absolute URLs
//! against the page base. No AI — pure structural extraction.

use crate::schema::Link;
use scraper::{Html, Selector};
use url::Url;

pub struct Extracted {
    pub title: String,
    pub canonical: Option<String>,
    pub markdown: String,
    pub text: String,
    pub links: Vec<Link>,
    pub assets: Assets,
}

/// Page assets — captured as data (wget-style), NOT stripped. External JS/CSS/img
/// URLs are resolved absolute; inline JS/CSS is measured (bytes) and hashed so the
/// research layer can fingerprint a page's behaviour without storing every byte.
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct Assets {
    pub scripts: Vec<String>,
    pub stylesheets: Vec<String>,
    pub images: Vec<String>,
    pub inline_script_bytes: usize,
    pub inline_style_bytes: usize,
    pub inline_script_cid: Option<String>,
    pub inline_style_cid: Option<String>,
}

pub fn extract(html: &str, base_url: &str) -> Extracted {
    let doc = Html::parse_document(html);
    let base = Url::parse(base_url).ok();

    let title = select_one(&doc, "title").unwrap_or_default().trim().to_string();

    let canonical = doc
        .select(&sel("link[rel=canonical]"))
        .next()
        .and_then(|e| e.value().attr("href"))
        .and_then(|href| resolve(&base, href));

    // Content blocks in document order. Comma selector yields matches in tree
    // order, so headings/paragraphs/list-items interleave correctly.
    let block_sel = sel("h1, h2, h3, h4, h5, h6, p, li, blockquote, pre, td, th");
    let mut md = String::new();
    let mut plain = String::new();
    for el in doc.select(&block_sel) {
        let txt: String = el.text().collect::<String>().split_whitespace().collect::<Vec<_>>().join(" ");
        if txt.is_empty() {
            continue;
        }
        let name = el.value().name();
        match name {
            "h1" => md.push_str(&format!("# {txt}\n\n")),
            "h2" => md.push_str(&format!("## {txt}\n\n")),
            "h3" => md.push_str(&format!("### {txt}\n\n")),
            "h4" | "h5" | "h6" => md.push_str(&format!("#### {txt}\n\n")),
            "li" => md.push_str(&format!("- {txt}\n")),
            "blockquote" => md.push_str(&format!("> {txt}\n\n")),
            "pre" => md.push_str(&format!("```\n{txt}\n```\n\n")),
            _ => md.push_str(&format!("{txt}\n\n")),
        }
        plain.push_str(&txt);
        plain.push('\n');
    }

    let mut links = Vec::new();
    for a in doc.select(&sel("a[href]")) {
        if let Some(href) = a.value().attr("href") {
            if let Some(abs) = resolve(&base, href) {
                let text: String =
                    a.text().collect::<String>().split_whitespace().collect::<Vec<_>>().join(" ");
                let rel = a.value().attr("rel").map(|r| r.to_string());
                links.push(Link { url: abs, text, rel });
            }
        }
    }

    let assets = extract_assets(&doc, &base);

    Extracted {
        title,
        canonical,
        markdown: md.trim_end().to_string(),
        text: plain.trim_end().to_string(),
        links,
        assets,
    }
}

fn extract_assets(doc: &Html, base: &Option<Url>) -> Assets {
    let mut a = Assets::default();
    for s in doc.select(&sel("script[src]")) {
        if let Some(src) = s.value().attr("src") {
            if let Some(abs) = resolve(base, src) {
                a.scripts.push(abs);
            }
        }
    }
    for l in doc.select(&sel("link[rel=stylesheet]")) {
        if let Some(href) = l.value().attr("href") {
            if let Some(abs) = resolve(base, href) {
                a.stylesheets.push(abs);
            }
        }
    }
    for img in doc.select(&sel("img[src]")) {
        if let Some(src) = img.value().attr("src") {
            if let Some(abs) = resolve(base, src) {
                a.images.push(abs);
            }
        }
    }
    // inline JS/CSS: measure + hash (don't store full body in the record).
    let inline_js: String = doc.select(&sel("script:not([src])")).map(|e| e.text().collect::<String>()).collect();
    let inline_css: String = doc.select(&sel("style")).map(|e| e.text().collect::<String>()).collect();
    a.inline_script_bytes = inline_js.len();
    a.inline_style_bytes = inline_css.len();
    if !inline_js.is_empty() {
        a.inline_script_cid = Some(crate::dedup::cid(&inline_js));
    }
    if !inline_css.is_empty() {
        a.inline_style_cid = Some(crate::dedup::cid(&inline_css));
    }
    a
}

fn sel(s: &str) -> Selector {
    // Selectors here are all static literals; parse cannot fail at runtime.
    Selector::parse(s).expect("static selector parses")
}

fn select_one(doc: &Html, s: &str) -> Option<String> {
    doc.select(&sel(s)).next().map(|e| e.text().collect::<String>())
}

/// Resolve a possibly-relative href against the page base. Drops fragments and
/// non-http(s) schemes (mailto:, javascript:, etc.) — noise the crawler ignores.
fn resolve(base: &Option<Url>, href: &str) -> Option<String> {
    let joined = match base {
        Some(b) => b.join(href).ok()?,
        None => Url::parse(href).ok()?,
    };
    if !matches!(joined.scheme(), "http" | "https") {
        return None;
    }
    let mut u = joined;
    u.set_fragment(None);
    Some(u.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    const PAGE: &str = r#"
        <html><head>
          <title>Test Page</title>
          <link rel="canonical" href="https://example.com/canonical">
        </head><body>
          <script src="/app.js"></script>
          <link rel="stylesheet" href="https://cdn.example.com/site.css">
          <img src="/logo.png">
          <script>var noise = "should not appear";</script>
          <style>.x{color:red}</style>
          <h1>Heading One</h1>
          <p>First paragraph here.</p>
          <ul><li>Item A</li><li>Item B</li></ul>
          <a href="/relative">Rel</a>
          <a href="https://other.com/abs">Abs</a>
          <a href="mailto:x@y.com">Mail</a>
        </body></html>"#;

    #[test]
    fn title_and_canonical() {
        let e = extract(PAGE, "https://example.com/start");
        assert_eq!(e.title, "Test Page");
        assert_eq!(e.canonical.as_deref(), Some("https://example.com/canonical"));
    }

    #[test]
    fn script_and_style_excluded() {
        let e = extract(PAGE, "https://example.com/start");
        assert!(!e.text.contains("should not appear"));
        assert!(!e.text.contains("color:red"));
        assert!(e.markdown.contains("# Heading One"));
        assert!(e.markdown.contains("- Item A"));
    }

    #[test]
    fn links_resolved_and_filtered() {
        let e = extract(PAGE, "https://example.com/start");
        let urls: Vec<&str> = e.links.iter().map(|l| l.url.as_str()).collect();
        assert!(urls.contains(&"https://example.com/relative"));
        assert!(urls.contains(&"https://other.com/abs"));
        // mailto: dropped
        assert!(!urls.iter().any(|u| u.starts_with("mailto")));
    }

    #[test]
    fn assets_captured_not_stripped() {
        let e = extract(PAGE, "https://example.com/start");
        assert_eq!(e.assets.scripts, vec!["https://example.com/app.js"]);
        assert_eq!(e.assets.stylesheets, vec!["https://cdn.example.com/site.css"]);
        assert_eq!(e.assets.images, vec!["https://example.com/logo.png"]);
        // inline JS/CSS measured + hashed, not dumped into text
        assert!(e.assets.inline_script_bytes > 0);
        assert!(e.assets.inline_style_bytes > 0);
        assert!(e.assets.inline_script_cid.is_some());
        assert!(!e.text.contains("should not appear"));
    }
}
