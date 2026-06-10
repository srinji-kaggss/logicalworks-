//! The crawl orchestrator. Ties the deterministic core (frontier, robots,
//! politeness, dedup, extract) to the async fetch layer and produces one
//! CrawlResult (`lgwks.crawl.v1`). Every URL terminates with an explicit
//! frontier status — the audit log is complete by construction.

use crate::config::CrawlConfig;
use crate::dedup::{cid, simhash, DedupIndex, DupVerdict};
use crate::fetch::{Conditional, Fetcher};
use crate::fingerprint;
use crate::frontier::{registrable_host, Frontier};
use crate::robots::RobotsRules;
use crate::schema::*;
use crate::{extract, politeness::Politeness};
use std::collections::HashMap;
use std::time::{SystemTime, UNIX_EPOCH};

pub struct Engine {
    cfg: CrawlConfig,
    fetcher: Fetcher,
}

impl Engine {
    pub fn new(cfg: CrawlConfig) -> crate::error::Result<Self> {
        let fetcher = Fetcher::new(&cfg)?;
        Ok(Self { cfg, fetcher })
    }

    pub async fn crawl(&self, seed: &str) -> CrawlResult {
        let run_id = format!("crawl-{}", &cid(seed)[4..16]);
        let mut result = CrawlResult::new(run_id, seed.to_string());

        let mut frontier = Frontier::new(seed, self.cfg.best_first, self.cfg.allow_offsite);
        let mut politeness = Politeness::new(self.cfg.min_host_delay_ms);
        let mut dedup = DedupIndex::new();
        let mut robots_cache: HashMap<String, RobotsRules> = HashMap::new();

        while let Some(target) = frontier.pop() {
            if result.pages.len() >= self.cfg.max_pages {
                break;
            }
            if target.depth > self.cfg.max_depth {
                result.frontier.push(entry(&target, FrontierStatus::DepthExceeded, None, 0));
                continue;
            }

            let host = match registrable_host(&target.url) {
                Some(h) => h,
                None => {
                    result.frontier.push(entry(&target, FrontierStatus::Error, Some("no host"), 0));
                    result.stats.errors += 1;
                    continue;
                }
            };

            // robots: load once per host (honest UA), cache.
            if !robots_cache.contains_key(&host) {
                let rules = self.load_robots(&target.url, &host).await;
                robots_cache.insert(host.clone(), rules);
            }
            let rules = robots_cache.get(&host).unwrap();

            if self.cfg.respect_robots && !rules.allowed(&target.url) {
                result.frontier.push(entry(&target, FrontierStatus::RobotsDisallowed, None, 0));
                result.stats.robots_disallowed += 1;
                continue;
            }
            let crawl_delay = rules.crawl_delay_ms;

            // fetch with retry/backoff; politeness wait before each attempt.
            let mut attempt = 0u32;
            let outcome = loop {
                let wait = politeness.wait_for(&host, crawl_delay, seed_jitter(&target.url));
                if !wait.is_zero() {
                    tokio::time::sleep(wait).await;
                }
                let fp = fingerprint::select(&host, attempt, self.cfg.stealth);
                politeness.record_hit(&host);
                match self.fetcher.get(&target.url, &fp, None as Option<&Conditional>).await {
                    Ok(resp) => {
                        politeness.record_success(&host);
                        break Ok(resp);
                    }
                    Err(e) => {
                        politeness.record_error(&host);
                        if attempt >= self.cfg.max_retries {
                            break Err(e);
                        }
                        attempt += 1;
                    }
                }
            };

            let resp = match outcome {
                Ok(r) => r,
                Err(e) => {
                    result
                        .frontier
                        .push(entry(&target, FrontierStatus::Error, Some(e.code()), attempt));
                    result.stats.errors += 1;
                    continue;
                }
            };

            result.stats.bytes_fetched += resp.content_length.unwrap_or(resp.body.len() as u64);
            result.stats.total_elapsed_ms += resp.elapsed_ms;

            if resp.not_modified {
                result.frontier.push(entry(&target, FrontierStatus::NotModified, None, attempt));
                continue;
            }
            if resp.status >= 400 {
                result.frontier.push(entry(
                    &target,
                    FrontierStatus::HttpError,
                    Some(&resp.status.to_string()),
                    attempt,
                ));
                result.stats.errors += 1;
                continue;
            }

            let ex = extract::extract(&resp.body, &target.url);

            match dedup.check_and_insert(&ex.text, self.cfg.near_dup_distance) {
                DupVerdict::Exact => {
                    result.frontier.push(entry(&target, FrontierStatus::Duplicate, None, attempt));
                    result.stats.duplicates_dropped += 1;
                    continue;
                }
                DupVerdict::Near(d) => {
                    result.frontier.push(entry(
                        &target,
                        FrontierStatus::NearDuplicate,
                        Some(&format!("hamming={d}")),
                        attempt,
                    ));
                    result.stats.near_duplicates_dropped += 1;
                    continue;
                }
                DupVerdict::Fresh => {}
            }

            // enqueue children before recording, at depth+1.
            if target.depth + 1 <= self.cfg.max_depth {
                for link in &ex.links {
                    frontier.push(&link.url, target.depth + 1, &target.url);
                }
            }

            let chunks = if self.cfg.discover_only {
                Vec::new()
            } else {
                crate::chunk::chunk_text(&ex.text, self.cfg.chunk_words, self.cfg.chunk_overlap)
            };

            let page = Page {
                cid: cid(&ex.text),
                url: target.url.clone(),
                canonical_url: ex.canonical.clone(),
                title: ex.title.clone(),
                word_count: ex.text.split_whitespace().count(),
                simhash: simhash(&ex.text),
                text: ex.text,
                markdown: ex.markdown,
                links: ex.links,
                assets: ex.assets,
                chunks,
                depth: target.depth,
                discovered_by: target.discovered_by.clone(),
                http: HttpMeta {
                    status: resp.status,
                    content_type: resp.content_type,
                    etag: resp.etag,
                    last_modified: resp.last_modified,
                    content_length: resp.content_length,
                    elapsed_ms: resp.elapsed_ms,
                },
                fetched_at: now_millis(),
            };
            result.pages.push(page);
            result.frontier.push(entry(&target, FrontierStatus::Fetched, None, attempt));
            result.stats.pages_fetched += 1;
        }

        result.stats.urls_seen = frontier.urls_seen;
        result
    }

    /// Fetch + parse robots.txt for the host. Failure → allow_all (fail open) but
    /// the engine never crashes on a missing/garbled robots.
    async fn load_robots(&self, sample_url: &str, host: &str) -> RobotsRules {
        let robots_url = match url::Url::parse(sample_url) {
            Ok(u) => format!("{}://{}/robots.txt", u.scheme(), host),
            Err(_) => return RobotsRules::allow_all(),
        };
        let fp = fingerprint::select(host, 0, self.cfg.stealth);
        match self.fetcher.get(&robots_url, &fp, None as Option<&Conditional>).await {
            Ok(resp) if resp.status < 400 && !resp.body.is_empty() => {
                match RobotsRules::parse(&fp.user_agent, resp.body.as_bytes()) {
                    Ok(r) => r,
                    Err(_) => RobotsRules::allow_all(),
                }
            }
            _ => RobotsRules::allow_all(),
        }
    }
}

fn entry(t: &crate::frontier::Target, status: FrontierStatus, reason: Option<&str>, attempt: u32) -> FrontierEntry {
    FrontierEntry {
        url: t.url.clone(),
        depth: t.depth,
        discovered_by: t.discovered_by.clone(),
        status,
        reason: reason.map(|s| s.to_string()),
        attempt,
    }
}

fn seed_jitter(url: &str) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in url.as_bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

fn now_millis() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis().to_string())
        .unwrap_or_default()
}
