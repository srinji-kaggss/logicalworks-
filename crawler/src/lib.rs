//! lgwks-crawler — a standalone, non-LLM, frontier web crawler. Callable three
//! ways over ONE contract (`lgwks.crawl.v2`): the library `crawl()` fn, the
//! `lgwks-crawler` CLI, and the HTTP API. The AI and the end-product frontend
//! both speak the API. Deterministic noise minimization (cid + simhash) is built
//! in so the noisy/overlapping output is cleaned before any model sees it.

pub mod api;
pub mod chunk;
pub mod config;
pub mod dedup;
pub mod engine;
pub mod error;
pub mod extract;
pub mod fetch;
pub mod fingerprint;
pub mod frontier;
pub mod gather;
pub mod media;
pub mod politeness;
pub mod robots;
pub mod schema;

pub use chunk::Chunk;
pub use config::{CrawlConfig, StealthLevel};
pub use error::{CrawlError, Result};
pub use gather::{gather, GatherRequest, Mode};
pub use schema::{CrawlResult, CrawlStats, FrontierEntry, FrontierStatus, Link, Page};

/// One-shot crawl with a config. Convenience over `engine::Engine`.
pub async fn crawl(cfg: CrawlConfig, seed: &str) -> Result<CrawlResult> {
    Ok(engine::Engine::new(cfg)?.crawl(seed).await)
}
