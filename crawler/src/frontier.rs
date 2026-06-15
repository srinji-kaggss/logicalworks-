//! The crawl frontier: a deduplicated queue of URLs to visit, BFS or best-first.
//! URL canonicalization collapses trivial variants (fragment, default port, case
//! in host) so the same page is never queued twice. Host-scoping keeps the crawl
//! on-site unless offsite is allowed. Pure and deterministic.

use std::collections::{BinaryHeap, HashSet, VecDeque};
use url::Url;

#[derive(Debug, Clone)]
pub struct Target {
    pub url: String,
    pub depth: u32,
    pub discovered_by: String,
}

/// Canonical form for dedup: lowercase scheme+host, strip fragment and default
/// port, normalize empty path to "/". Query is preserved (it can be meaningful).
pub fn canonicalize(raw: &str) -> Option<String> {
    let mut u = Url::parse(raw).ok()?;
    if !matches!(u.scheme(), "http" | "https") {
        return None;
    }
    u.set_fragment(None);
    // strip default ports
    if (u.scheme() == "http" && u.port() == Some(80))
        || (u.scheme() == "https" && u.port() == Some(443))
    {
        let _ = u.set_port(None);
    }
    if u.path().is_empty() {
        u.set_path("/");
    }
    Some(u.as_str().to_string())
}

pub fn registrable_host(raw: &str) -> Option<String> {
    Url::parse(raw).ok()?.host_str().map(|h| h.to_lowercase())
}

/// True if `host` is a loopback/private/link-local IP literal or a local-only
/// name. SSRF guard (#154 M12): refuse fetches to internal services (incl. the
/// cloud metadata endpoint 169.254.169.254, which is link-local) when the
/// crawler is driven by untrusted input.
pub fn is_private_host(host: &str) -> bool {
    let h = host.trim().trim_start_matches('[').trim_end_matches(']');
    if let Ok(ip) = h.parse::<std::net::IpAddr>() {
        return match ip {
            std::net::IpAddr::V4(v4) => {
                v4.is_loopback() || v4.is_private() || v4.is_link_local()
                    || v4.is_unspecified() || v4.is_broadcast()
            }
            std::net::IpAddr::V6(v6) => {
                v6.is_loopback()
                    || v6.is_unspecified()
                    || (v6.segments()[0] & 0xfe00) == 0xfc00 // unique-local fc00::/7
                    || (v6.segments()[0] & 0xffc0) == 0xfe80 // link-local fe80::/10
            }
        };
    }
    let lower = h.to_ascii_lowercase();
    lower == "localhost"
        || lower.ends_with(".localhost")
        || lower.ends_with(".local")
        || lower.ends_with(".internal")
}

struct Scored {
    target: Target,
    score: i64,
}
impl PartialEq for Scored {
    fn eq(&self, other: &Self) -> bool {
        self.score == other.score
    }
}
impl Eq for Scored {}
impl Ord for Scored {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        // higher score first; tie-break on url for determinism
        self.score
            .cmp(&other.score)
            .then_with(|| other.target.url.cmp(&self.target.url))
    }
}
impl PartialOrd for Scored {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

pub struct Frontier {
    bfs: VecDeque<Target>,
    best: BinaryHeap<Scored>,
    seen: HashSet<String>,
    best_first: bool,
    seed_host: Option<String>,
    allow_offsite: bool,
    pub urls_seen: usize,
}

impl Frontier {
    pub fn new(seed: &str, best_first: bool, allow_offsite: bool) -> Self {
        let mut f = Self {
            bfs: VecDeque::new(),
            best: BinaryHeap::new(),
            seen: HashSet::new(),
            best_first,
            seed_host: registrable_host(seed),
            allow_offsite,
            urls_seen: 0,
        };
        if let Some(c) = canonicalize(seed) {
            f.push_raw(c, 0, "seed");
        }
        f
    }

    /// Returns true if the url was newly enqueued (passed dedup + host scope).
    pub fn push(&mut self, raw: &str, depth: u32, discovered_by: &str) -> bool {
        match canonicalize(raw) {
            Some(c) => self.push_raw(c, depth, discovered_by),
            None => false,
        }
    }

    fn push_raw(&mut self, canon: String, depth: u32, discovered_by: &str) -> bool {
        if self.seen.contains(&canon) {
            return false;
        }
        if !self.allow_offsite {
            if let (Some(seed_host), Some(h)) = (&self.seed_host, registrable_host(&canon)) {
                if &h != seed_host {
                    return false;
                }
            }
        }
        self.seen.insert(canon.clone());
        self.urls_seen += 1;
        let target = Target { url: canon, depth, discovered_by: discovered_by.to_string() };
        if self.best_first {
            // shallower is better; on-host already guaranteed unless offsite.
            let score = -(depth as i64);
            self.best.push(Scored { target, score });
        } else {
            self.bfs.push_back(target);
        }
        true
    }

    pub fn pop(&mut self) -> Option<Target> {
        if self.best_first {
            self.best.pop().map(|s| s.target)
        } else {
            self.bfs.pop_front()
        }
    }

    pub fn is_empty(&self) -> bool {
        if self.best_first { self.best.is_empty() } else { self.bfs.is_empty() }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_collapses_fragment_and_port() {
        assert_eq!(
            canonicalize("https://Example.com:443/path#frag"),
            Some("https://example.com/path".to_string())
        );
    }

    #[test]
    fn dedup_blocks_revisit() {
        let mut f = Frontier::new("https://example.com/", false, false);
        assert!(!f.push("https://example.com/", 1, "link")); // already seeded
        assert!(f.push("https://example.com/a", 1, "link"));
        assert!(!f.push("https://example.com/a#x", 1, "link")); // same after canon
    }

    #[test]
    fn offsite_blocked_by_default() {
        let mut f = Frontier::new("https://example.com/", false, false);
        assert!(!f.push("https://evil.com/", 1, "link"));
        assert!(f.push("https://example.com/ok", 1, "link"));
    }

    #[test]
    fn bfs_order_is_fifo() {
        let mut f = Frontier::new("https://example.com/", false, false);
        f.push("https://example.com/a", 1, "link");
        f.push("https://example.com/b", 1, "link");
        assert_eq!(f.pop().unwrap().url, "https://example.com/"); // seed first
        assert_eq!(f.pop().unwrap().url, "https://example.com/a");
        assert_eq!(f.pop().unwrap().url, "https://example.com/b");
    }
}
