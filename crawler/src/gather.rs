//! The ONE upstream entry the AI calls. Where other crawlers expose
//! map/crawl/scrape/search as separate endpoints, here they are MODES of a single
//! `gather()` call — the
//! caller (you, or a research/ctx7-style request) says what it wants, the backend
//! picks the crawl shape. //why one entry: the AI should not orchestrate
//! map-vs-crawl-vs-scrape; it asks once and the backend decides.

use crate::config::{CrawlConfig, StealthLevel};
use crate::schema::CrawlResult;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    /// One page, full extract + chunks. (a.k.a. `scrape`)
    Scrape,
    /// Discover the URL graph of a site fast, no heavy extraction. (a.k.a. `map`)
    Map,
    /// Recursive multi-page crawl with full extract + chunks. (a.k.a. `crawl`)
    Crawl,
}

fn default_mode() -> Mode {
    Mode::Scrape
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GatherRequest {
    pub url: String,
    #[serde(default = "default_mode")]
    pub mode: Mode,
    #[serde(default)]
    pub max_pages: Option<usize>,
    #[serde(default)]
    pub max_depth: Option<u32>,
    #[serde(default)]
    pub stealth: Option<StealthLevel>,
    #[serde(default)]
    pub respect_robots: Option<bool>,
    #[serde(default)]
    pub allow_offsite: Option<bool>,
}

impl GatherRequest {
    pub fn new(url: impl Into<String>, mode: Mode) -> Self {
        Self {
            url: url.into(),
            mode,
            max_pages: None,
            max_depth: None,
            stealth: None,
            respect_robots: None,
            allow_offsite: None,
        }
    }

    pub fn into_config(&self) -> CrawlConfig {
        let mut c = CrawlConfig::default();
        // mode sets the shape; explicit fields override.
        match self.mode {
            Mode::Scrape => {
                c.max_pages = 1;
                c.max_depth = 0;
            }
            Mode::Map => {
                c.max_pages = 500;
                c.max_depth = 4;
                c.discover_only = true;
            }
            Mode::Crawl => {
                c.max_pages = 50;
                c.max_depth = 3;
            }
        }
        if let Some(v) = self.max_pages {
            c.max_pages = v;
        }
        if let Some(v) = self.max_depth {
            c.max_depth = v;
        }
        if let Some(v) = self.stealth {
            c.stealth = v;
        }
        if let Some(v) = self.respect_robots {
            c.respect_robots = v;
        }
        if let Some(v) = self.allow_offsite {
            c.allow_offsite = v;
        }
        c
    }
}

/// The single entry. Internally orchestrates the right crawl shape and returns
/// one `lgwks.crawl.v1` result. (A `Search` mode — web search → gather — is the
/// next mode; it needs a search provider and is intentionally not faked here.)
pub async fn gather(req: &GatherRequest) -> crate::error::Result<CrawlResult> {
    let cfg = req.into_config();
    Ok(crate::engine::Engine::new(cfg)?.crawl(&req.url).await)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scrape_is_single_page() {
        let c = GatherRequest::new("https://x.com", Mode::Scrape).into_config();
        assert_eq!(c.max_pages, 1);
        assert_eq!(c.max_depth, 0);
        assert!(!c.discover_only);
    }

    #[test]
    fn map_is_discover_only_and_wide() {
        let c = GatherRequest::new("https://x.com", Mode::Map).into_config();
        assert!(c.discover_only);
        assert!(c.max_pages >= 100);
    }

    #[test]
    fn explicit_fields_override_mode() {
        let mut r = GatherRequest::new("https://x.com", Mode::Crawl);
        r.max_pages = Some(7);
        assert_eq!(r.into_config().max_pages, 7);
    }
}
