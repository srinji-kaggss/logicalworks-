//! Deterministic noise minimization — NO AI. Two layers:
//!   1. exact dedup via blake2 content-id (cid) over normalized text;
//!   2. near-duplicate detection via 64-bit simhash + Hamming distance.
//! Bots are "noisy and overlappy" by design; this strips the overlap before the
//! research model ever sees it, cheaply and reproducibly. //why simhash over
//! shingling+jaccard: O(1) compare via popcount, fixed-size signature to store.

use blake2::{Blake2b512, Digest};
use std::collections::HashSet;

/// Content id of normalized text. Stable across runs — the dedup key + audit anchor.
pub fn cid(text: &str) -> String {
    let normalized = normalize(text);
    let mut hasher = Blake2b512::new();
    hasher.update(normalized.as_bytes());
    let digest = hasher.finalize();
    format!("cid-{}", hex::encode(&digest[..16]))
}

/// Content id of raw bytes — same blake2b-512 scheme, no normalization.
/// Used for media assets (images, video) where byte identity matters, not text identity.
pub fn cid_bytes(data: &[u8]) -> String {
    let mut hasher = Blake2b512::new();
    hasher.update(data);
    let digest = hasher.finalize();
    format!("cid-{}", hex::encode(&digest[..16]))
}

/// Lowercase, collapse whitespace. The normalization that makes "same content,
/// different spacing" collapse to one cid.
fn normalize(text: &str) -> String {
    text.split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

/// 64-bit simhash over whitespace tokens. Near-identical documents land at small
/// Hamming distance; unrelated documents spread apart.
pub fn simhash(text: &str) -> u64 {
    let mut bins = [0i32; 64];
    for tok in normalize(text).split_whitespace() {
        let h = token_hash(tok);
        for (i, bin) in bins.iter_mut().enumerate() {
            if (h >> i) & 1 == 1 {
                *bin += 1;
            } else {
                *bin -= 1;
            }
        }
    }
    let mut sig = 0u64;
    for (i, &bin) in bins.iter().enumerate() {
        if bin > 0 {
            sig |= 1 << i;
        }
    }
    sig
}

fn token_hash(tok: &str) -> u64 {
    // FNV-1a — deterministic, platform-stable.
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in tok.as_bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

pub fn hamming(a: u64, b: u64) -> u32 {
    (a ^ b).count_ones()
}

/// Tracks seen content for a run. Exact cids in a set; simhashes in a vec for
/// near-dup scan. //why a linear simhash scan: page counts per run are bounded
/// (max_pages), so O(n) compare is fine and keeps it dependency-free; an LSH
/// banding index is the documented upgrade if runs ever get huge.
#[derive(Default)]
pub struct DedupIndex {
    seen_cids: HashSet<String>,
    simhashes: Vec<u64>,
}

#[derive(Debug, PartialEq, Eq)]
pub enum DupVerdict {
    Fresh,
    Exact,
    Near(u32), // distance to nearest seen
}

impl DedupIndex {
    pub fn new() -> Self {
        Self::default()
    }

    /// Classify text against everything seen, and record it if fresh.
    pub fn check_and_insert(&mut self, text: &str, near_threshold: u32) -> DupVerdict {
        let id = cid(text);
        if self.seen_cids.contains(&id) {
            return DupVerdict::Exact;
        }
        let sh = simhash(text);
        if let Some(min) = self.simhashes.iter().map(|&s| hamming(s, sh)).min() {
            if min <= near_threshold {
                return DupVerdict::Near(min);
            }
        }
        self.seen_cids.insert(id);
        self.simhashes.push(sh);
        DupVerdict::Fresh
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cid_is_whitespace_and_case_stable() {
        assert_eq!(cid("Hello   World"), cid("hello world"));
        assert_ne!(cid("hello world"), cid("goodbye world"));
    }

    #[test]
    fn exact_duplicate_caught() {
        let mut idx = DedupIndex::new();
        assert_eq!(idx.check_and_insert("the quick brown fox", 3), DupVerdict::Fresh);
        assert_eq!(idx.check_and_insert("the   quick BROWN fox", 3), DupVerdict::Exact);
    }

    #[test]
    fn near_duplicate_caught() {
        let mut idx = DedupIndex::new();
        let base = "the quick brown fox jumps over the lazy dog near the river bank today";
        let near = "the quick brown fox jumps over the lazy dog near the river bank now";
        assert_eq!(idx.check_and_insert(base, 5), DupVerdict::Fresh);
        match idx.check_and_insert(near, 5) {
            DupVerdict::Near(_) => {}
            other => panic!("expected near-dup, got {other:?}"),
        }
    }

    #[test]
    fn unrelated_is_fresh() {
        let mut idx = DedupIndex::new();
        assert_eq!(idx.check_and_insert("alpha beta gamma delta", 3), DupVerdict::Fresh);
        assert_eq!(
            idx.check_and_insert("zebra yellow mountain ocean", 3),
            DupVerdict::Fresh
        );
    }

    #[test]
    fn identical_simhash_zero_distance() {
        assert_eq!(hamming(simhash("a b c d"), simhash("a b c d")), 0);
    }
}
