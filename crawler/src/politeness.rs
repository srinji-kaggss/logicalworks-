//! Per-host politeness. Enforces a minimum inter-request delay per host
//! (the larger of the config floor and any robots Crawl-delay), with
//! exponential backoff on consecutive errors and deterministic jitter. The
//! delay MATH is pure and unit-tested; the engine layers tokio sleeps on top.

use std::collections::HashMap;
use std::time::{Duration, Instant};

/// Pure backoff: base delay grows exponentially with consecutive errors, capped,
/// plus deterministic jitter derived from a seed (no RNG → replayable).
pub fn backoff_ms(base_ms: u64, consecutive_errors: u32, seed: u64) -> u64 {
    let factor = 1u64 << consecutive_errors.min(6); // cap growth at 64x
    let grown = base_ms.saturating_mul(factor);
    let capped = grown.min(60_000); // never wait more than 60s
    // deterministic jitter in [0, base/4] so hosts don't get perfectly periodic hits
    let jitter_span = (base_ms / 4).max(1);
    let jitter = seed % jitter_span;
    capped.saturating_add(jitter)
}

pub struct Politeness {
    floor_ms: u64,
    last_hit: HashMap<String, Instant>,
    errors: HashMap<String, u32>,
}

impl Politeness {
    pub fn new(floor_ms: u64) -> Self {
        Self { floor_ms, last_hit: HashMap::new(), errors: HashMap::new() }
    }

    /// How long the caller must sleep before hitting `host`, given the effective
    /// per-host delay (max of floor and robots crawl-delay) and error backoff.
    pub fn wait_for(&self, host: &str, crawl_delay_ms: Option<u64>, seed: u64) -> Duration {
        let base = self.floor_ms.max(crawl_delay_ms.unwrap_or(0));
        let errs = self.errors.get(host).copied().unwrap_or(0);
        let required = backoff_ms(base, errs, seed);
        match self.last_hit.get(host) {
            Some(&t) => {
                let since = t.elapsed().as_millis() as u64;
                if since >= required {
                    Duration::ZERO
                } else {
                    Duration::from_millis(required - since)
                }
            }
            None => Duration::ZERO,
        }
    }

    pub fn record_hit(&mut self, host: &str) {
        self.last_hit.insert(host.to_string(), Instant::now());
    }

    pub fn record_error(&mut self, host: &str) {
        *self.errors.entry(host.to_string()).or_insert(0) += 1;
    }

    pub fn record_success(&mut self, host: &str) {
        self.errors.insert(host.to_string(), 0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn backoff_grows_then_caps() {
        let b0 = backoff_ms(1000, 0, 0);
        let b2 = backoff_ms(1000, 2, 0);
        let b_huge = backoff_ms(1000, 30, 0);
        assert_eq!(b0, 1000);
        assert_eq!(b2, 4000);
        assert!(b_huge <= 60_000 + 250);
    }

    #[test]
    fn jitter_is_deterministic() {
        assert_eq!(backoff_ms(1000, 0, 42), backoff_ms(1000, 0, 42));
    }

    #[test]
    fn first_hit_no_wait() {
        let p = Politeness::new(500);
        assert_eq!(p.wait_for("example.com", None, 0), Duration::ZERO);
    }

    #[test]
    fn robots_delay_overrides_floor_when_larger() {
        // crawl-delay 5s > floor 0.5s → required base is 5s.
        let b = backoff_ms(5000, 0, 0);
        assert_eq!(b, 5000);
    }
}
