//! The wire contract — `lgwks.crawl.v1`. This is the SAME JSON the AI calls and
//! the end product's frontend calls (the control-bus principle: one machine
//! contract, many renderers). Everything content-addressed for replay/audit.

use serde::{Deserialize, Serialize};

pub const SCHEMA_VERSION: &str = "lgwks.crawl.v1";

/// One crawled page. `cid` is the blake2 content id of the normalized text —
/// stable across runs, the dedup key, and the audit anchor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Page {
    pub cid: String,
    pub url: String,
    pub canonical_url: Option<String>,
    pub title: String,
    pub text: String,
    pub markdown: String,
    pub links: Vec<Link>,
    /// External JS/CSS/img + inline-asset fingerprints (wget-style capture).
    pub assets: crate::extract::Assets,
    /// Content-addressed text chunks — the cleanup/synthesis layer.
    pub chunks: Vec<crate::chunk::Chunk>,
    pub depth: u32,
    pub discovered_by: String,
    pub http: HttpMeta,
    /// simhash of the content for near-duplicate detection (deterministic).
    pub simhash: u64,
    pub word_count: usize,
    pub fetched_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Link {
    pub url: String,
    pub text: String,
    pub rel: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HttpMeta {
    pub status: u16,
    pub content_type: Option<String>,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
    pub content_length: Option<u64>,
    pub elapsed_ms: u64,
}

/// Frontier entry — the append-only audit log. EVERY url ends with an explicit
/// terminal status; nothing is silently dropped. Carried forward from the
/// Python crawler's frontier discipline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FrontierEntry {
    pub url: String,
    pub depth: u32,
    pub discovered_by: String,
    pub status: FrontierStatus,
    pub reason: Option<String>,
    pub attempt: u32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FrontierStatus {
    Queued,
    Fetched,
    Blocked,        // host/policy gate
    RobotsDisallowed,
    Duplicate,      // exact cid seen
    NearDuplicate,  // simhash within threshold
    Error,
    HttpError,
    DepthExceeded,
    NotModified,    // conditional GET 304
}

/// Per-run statistics — cheap signals for the research model downstream and for
/// the cockpit, all computed deterministically with zero AI.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CrawlStats {
    pub pages_fetched: usize,
    pub urls_seen: usize,
    pub duplicates_dropped: usize,
    pub near_duplicates_dropped: usize,
    pub robots_disallowed: usize,
    pub errors: usize,
    pub bytes_fetched: u64,
    pub total_elapsed_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrawlResult {
    pub schema: String,
    pub run_id: String,
    pub seed: String,
    pub pages: Vec<Page>,
    pub frontier: Vec<FrontierEntry>,
    pub stats: CrawlStats,
}

impl CrawlResult {
    pub fn new(run_id: String, seed: String) -> Self {
        Self {
            schema: SCHEMA_VERSION.to_string(),
            run_id,
            seed,
            pages: Vec::new(),
            frontier: Vec::new(),
            stats: CrawlStats::default(),
        }
    }
}
