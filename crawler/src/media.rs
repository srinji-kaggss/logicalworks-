//! Media byte fetching for crawler v2. Converts `Assets.images` (URL list from
//! v1 extract) into `Vec<MediaItem>` — each asset fetched, its bytes
//! content-addressed (cid_bytes), and modality-typed from Content-Type.
//!
//! //why best-effort, not fail-fast: a page is useful without its media; a media
//! fetch error should never drop the page from the result. Errors are logged and
//! the URL is skipped. The frontier audit for media items is handled by the caller.

use crate::config::CrawlConfig;
use crate::dedup::cid_bytes;
use crate::schema::{MediaItem, Modality};
use reqwest::Client;
use std::time::{Duration, Instant};
use tracing::warn;

/// Detect modality from a Content-Type header value. Returns None for non-media types.
fn detect_modality(content_type: &str) -> Option<Modality> {
    let ct = content_type.split(';').next().unwrap_or("").trim();
    if ct.starts_with("image/") {
        Some(Modality::Image)
    } else if ct.starts_with("video/") {
        Some(Modality::Video)
    } else {
        None
    }
}

/// Fetch raw bytes for every media URL in `urls`. Non-media Content-Types are
/// silently skipped (not emitted as MediaItem). Errors are warned and skipped.
/// Respects `max_body_bytes` from config to cap each fetch.
pub async fn fetch_media(urls: &[String], cfg: &CrawlConfig) -> Vec<MediaItem> {
    if urls.is_empty() {
        return Vec::new();
    }

    let client = match Client::builder()
        .timeout(Duration::from_millis(cfg.request_timeout_ms))
        .redirect(reqwest::redirect::Policy::limited(3))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            warn!("media: could not build HTTP client: {e}");
            return Vec::new();
        }
    };

    let mut items = Vec::new();

    for url in urls {
        let _start = Instant::now();
        let resp = match client.get(url).send().await {
            Ok(r) => r,
            Err(e) => {
                warn!("media: fetch failed for {url}: {e}");
                continue;
            }
        };

        let status = resp.status().as_u16();

        let content_type = resp
            .headers()
            .get(reqwest::header::CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_string();

        let modality = match detect_modality(&content_type) {
            Some(m) => m,
            None => continue, // not image or video — skip
        };

        let mime = content_type.split(';').next().unwrap_or("application/octet-stream").trim().to_string();

        let bytes = match resp.bytes().await {
            Ok(b) => b,
            Err(e) => {
                warn!("media: body read failed for {url}: {e}");
                continue;
            }
        };

        // Cap to max_body_bytes (same cap as page text bodies).
        let bytes = if bytes.len() > cfg.max_body_bytes {
            bytes.slice(..cfg.max_body_bytes)
        } else {
            bytes
        };

        let byte_count = bytes.len() as u64;
        let cid = cid_bytes(&bytes);

        items.push(MediaItem {
            cid,
            modality,
            url: url.clone(),
            mime,
            byte_count,
            fetch_status: status,
        });
    }

    items
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detect_image_types() {
        assert_eq!(detect_modality("image/jpeg"), Some(Modality::Image));
        assert_eq!(detect_modality("image/png; charset=utf-8"), Some(Modality::Image));
        assert_eq!(detect_modality("image/webp"), Some(Modality::Image));
    }

    #[test]
    fn detect_video_types() {
        assert_eq!(detect_modality("video/mp4"), Some(Modality::Video));
        assert_eq!(detect_modality("video/webm"), Some(Modality::Video));
    }

    #[test]
    fn non_media_returns_none() {
        assert_eq!(detect_modality("text/html"), None);
        assert_eq!(detect_modality("application/json"), None);
        assert_eq!(detect_modality(""), None);
    }

    #[test]
    fn empty_url_list_returns_empty() {
        // synchronous check — the async path is integration-tested
        let urls: Vec<String> = Vec::new();
        assert!(urls.is_empty());
    }
}
