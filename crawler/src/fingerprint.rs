//! Deterministic browser-fingerprint rotation. Pools carried from the Python
//! crawler (lgwks_crawl). Selection is a pure function of (host, attempt) — same
//! input, same fingerprint — so a run is replayable and a test can pin it.
//! //why deterministic, not random: the Director wants no nondeterminism; a
//! seeded hash distributes the fingerprint without breaking replay.

use crate::config::StealthLevel;

const UA_POOL: &[&str] = &[
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
];

const LOCALE_POOL: &[&str] = &["en-US,en;q=0.9", "en-GB,en;q=0.9", "en-CA,en;q=0.8", "fr-FR,fr;q=0.9"];

const HONEST_UA: &str = "lgwks-crawler/0.1 (+https://logicalworks.ca/bot)";

#[derive(Debug, Clone)]
pub struct Fingerprint {
    pub user_agent: String,
    pub accept_language: String,
    pub accept: String,
}

/// FNV-1a — a tiny deterministic hash for pool indexing. No external dep, stable
/// across platforms (unlike DefaultHasher, which is not guaranteed stable).
fn fnv1a(bytes: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in bytes {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

const ACCEPT_HTML: &str =
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8";

pub fn select(host: &str, attempt: u32, level: StealthLevel) -> Fingerprint {
    match level {
        StealthLevel::Honest => Fingerprint {
            user_agent: HONEST_UA.to_string(),
            accept_language: "en-US,en;q=0.9".to_string(),
            accept: ACCEPT_HTML.to_string(),
        },
        StealthLevel::Browserlike => Fingerprint {
            user_agent: UA_POOL[0].to_string(),
            accept_language: LOCALE_POOL[0].to_string(),
            accept: ACCEPT_HTML.to_string(),
        },
        StealthLevel::Rotating | StealthLevel::Aggressive => {
            let seed = fnv1a(format!("{host}:{attempt}").as_bytes());
            let ua = UA_POOL[(seed as usize) % UA_POOL.len()];
            let loc = LOCALE_POOL[((seed >> 17) as usize) % LOCALE_POOL.len()];
            Fingerprint {
                user_agent: ua.to_string(),
                accept_language: loc.to_string(),
                accept: ACCEPT_HTML.to_string(),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn honest_is_truthful_and_stable() {
        let f = select("example.com", 0, StealthLevel::Honest);
        assert!(f.user_agent.contains("lgwks-crawler"));
        let g = select("other.com", 5, StealthLevel::Honest);
        assert_eq!(f.user_agent, g.user_agent);
    }

    #[test]
    fn rotating_is_deterministic_per_host_attempt() {
        let a = select("example.com", 1, StealthLevel::Rotating);
        let b = select("example.com", 1, StealthLevel::Rotating);
        assert_eq!(a.user_agent, b.user_agent);
        assert_eq!(a.accept_language, b.accept_language);
    }

    #[test]
    fn rotating_varies_across_hosts() {
        // Not guaranteed different for every pair, but the seed must spread the
        // space: at least one of several hosts should differ from the first.
        let base = select("aaa.com", 0, StealthLevel::Rotating).user_agent;
        let differs = ["bbb.com", "ccc.com", "ddd.com", "eee.com"]
            .iter()
            .any(|h| select(h, 0, StealthLevel::Rotating).user_agent != base);
        assert!(differs);
    }
}
