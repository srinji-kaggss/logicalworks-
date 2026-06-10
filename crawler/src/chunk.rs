//! The cleanup/synthesis layer: turn a page's text into content-addressed chunks.
//! This is what makes the crawl output consumable downstream — each chunk carries
//! its own cid (exact key) and simhash (near-dup key), so the substrate/embed
//! stage can dedup, retrieve, and audit at chunk granularity. Deterministic; no AI.
//! //why word-windowed with overlap: mirrors the Python substrate `_chunk_text`
//! (size/overlap) so the contract matches what the substrate already expects.

use crate::dedup::{cid, simhash};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chunk {
    pub cid: String,
    pub position: usize,
    pub text: String,
    pub word_count: usize,
    pub simhash: u64,
}

/// Split text into overlapping word windows. `size` words per chunk, `overlap`
/// words shared with the previous chunk. Empty/whitespace text → no chunks.
pub fn chunk_text(text: &str, size: usize, overlap: usize) -> Vec<Chunk> {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.is_empty() {
        return Vec::new();
    }
    let size = size.max(1);
    let step = size.saturating_sub(overlap).max(1);
    let mut chunks = Vec::new();
    let mut start = 0usize;
    let mut position = 0usize;
    while start < words.len() {
        let end = (start + size).min(words.len());
        let body = words[start..end].join(" ");
        chunks.push(Chunk {
            cid: cid(&body),
            position,
            word_count: end - start,
            simhash: simhash(&body),
            text: body,
        });
        position += 1;
        if end == words.len() {
            break;
        }
        start += step;
    }
    chunks
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_text_no_chunks() {
        assert!(chunk_text("   ", 10, 2).is_empty());
    }

    #[test]
    fn windows_with_overlap_cover_all_words() {
        let text = (1..=10).map(|i| i.to_string()).collect::<Vec<_>>().join(" ");
        let chunks = chunk_text(&text, 4, 1); // step = 3
        // windows start at 0,3,6; the 6-window reaches the end and stops → 3 chunks
        assert_eq!(chunks.len(), 3);
        assert_eq!(chunks[0].text, "1 2 3 4");
        assert_eq!(chunks[1].text, "4 5 6 7"); // overlap of 1 word ("4")
        assert_eq!(chunks[2].text, "7 8 9 10");
        assert!(chunks.last().unwrap().text.ends_with("10"));
    }

    #[test]
    fn each_chunk_is_content_addressed() {
        let chunks = chunk_text("alpha beta gamma delta epsilon", 2, 0);
        for c in &chunks {
            assert!(c.cid.starts_with("cid-"));
            assert_eq!(c.cid, cid(&c.text));
        }
    }

    #[test]
    fn deterministic() {
        let a = chunk_text("one two three four five six", 3, 1);
        let b = chunk_text("one two three four five six", 3, 1);
        assert_eq!(a.len(), b.len());
        assert_eq!(a[0].cid, b[0].cid);
    }
}
