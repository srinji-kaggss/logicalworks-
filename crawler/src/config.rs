//! Crawl configuration and the escalation policy. Default posture is HONEST:
//! identify truthfully, respect robots, stay polite. Stealth is an explicit,
//! configured escalation ladder — never the default. //why this mirrors the
//! Python crawler's "honest the right way past JS walls" ethic and the PRD's
//! "honest-first, human-auth only on true exhaustion."

use serde::{Deserialize, Serialize};

/// The anti-detection ladder. Each rung is opt-in; the engine only climbs when
/// the level permits AND a lower rung was insufficient.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StealthLevel {
    /// Identify as lgwks-crawler, respect robots strictly. The good-citizen bot.
    Honest,
    /// Present as a real desktop browser UA + full header set. Still robots-respecting.
    Browserlike,
    /// Rotate fingerprints (UA/headers/locale) deterministically per host to
    /// distribute load fingerprint. Robots still respected unless overridden.
    Rotating,
    /// Full evasion budget: rotation + retry-with-jitter past soft blocks.
    /// Reserved for explicitly authorized targets; robots override must be set.
    Aggressive,
}

impl Default for StealthLevel {
    fn default() -> Self {
        StealthLevel::Honest
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CrawlConfig {
    pub max_pages: usize,
    pub max_depth: u32,
    /// Stay on the seed's registrable host unless true.
    pub allow_offsite: bool,
    pub respect_robots: bool,
    pub stealth: StealthLevel,
    /// Minimum delay between requests to the same host, in ms (politeness floor).
    pub min_host_delay_ms: u64,
    /// Cap on a single response body.
    pub max_body_bytes: usize,
    pub max_retries: u32,
    /// simhash Hamming distance below which two pages are "near-duplicate".
    pub near_dup_distance: u32,
    pub request_timeout_ms: u64,
    /// Frontier ordering: BFS (depth-first-discovered) or best-first by score.
    pub best_first: bool,
    /// Map mode: discover URLs only — skip chunking/asset detail for speed.
    pub discover_only: bool,
    /// Chunk window (words) and overlap for the cleanup/synthesis layer.
    pub chunk_words: usize,
    pub chunk_overlap: usize,
}

impl Default for CrawlConfig {
    fn default() -> Self {
        Self {
            max_pages: 50,
            max_depth: 3,
            allow_offsite: false,
            respect_robots: true,
            stealth: StealthLevel::Honest,
            min_host_delay_ms: 500,
            max_body_bytes: 8 * 1024 * 1024,
            max_retries: 2,
            near_dup_distance: 3,
            request_timeout_ms: 15_000,
            best_first: false,
            discover_only: false,
            chunk_words: 320,
            chunk_overlap: 48,
        }
    }
}
