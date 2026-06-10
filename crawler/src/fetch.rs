//! HTTP fetch over reqwest. Honest-first headers from the selected fingerprint,
//! conditional GET (If-None-Match / If-Modified-Since → 304 NotModified for
//! freshness/bandwidth), body-size cap, and decode. The engine owns retry/backoff;
//! this layer reports one attempt faithfully with typed errors.

use crate::config::CrawlConfig;
use crate::error::{CrawlError, Result};
use crate::fingerprint::Fingerprint;
use reqwest::header::{
    HeaderMap, HeaderValue, ACCEPT, ACCEPT_LANGUAGE, IF_MODIFIED_SINCE, IF_NONE_MATCH, USER_AGENT,
};
use std::time::{Duration, Instant};

pub struct Fetcher {
    client: reqwest::Client,
    max_body_bytes: usize,
}

pub struct Conditional {
    pub etag: Option<String>,
    pub last_modified: Option<String>,
}

pub struct FetchResponse {
    pub status: u16,
    pub body: String,
    pub content_type: Option<String>,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
    pub content_length: Option<u64>,
    pub elapsed_ms: u64,
    pub not_modified: bool,
}

impl Fetcher {
    pub fn new(cfg: &CrawlConfig) -> Result<Self> {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_millis(cfg.request_timeout_ms))
            .redirect(reqwest::redirect::Policy::limited(5))
            .build()
            .map_err(|e| CrawlError::Fetch { url: "<client>".into(), reason: e.to_string() })?;
        Ok(Self { client, max_body_bytes: cfg.max_body_bytes })
    }

    pub async fn get(
        &self,
        url: &str,
        fp: &Fingerprint,
        cond: Option<&Conditional>,
    ) -> Result<FetchResponse> {
        let mut headers = HeaderMap::new();
        headers.insert(USER_AGENT, hv(&fp.user_agent)?);
        headers.insert(ACCEPT_LANGUAGE, hv(&fp.accept_language)?);
        headers.insert(ACCEPT, hv(&fp.accept)?);
        if let Some(c) = cond {
            if let Some(etag) = &c.etag {
                headers.insert(IF_NONE_MATCH, hv(etag)?);
            }
            if let Some(lm) = &c.last_modified {
                headers.insert(IF_MODIFIED_SINCE, hv(lm)?);
            }
        }

        let started = Instant::now();
        let resp = self
            .client
            .get(url)
            .headers(headers)
            .send()
            .await
            .map_err(|e| CrawlError::Fetch { url: url.to_string(), reason: e.to_string() })?;

        let status = resp.status().as_u16();
        let content_type = header_str(resp.headers(), reqwest::header::CONTENT_TYPE);
        let etag = header_str(resp.headers(), reqwest::header::ETAG);
        let last_modified = header_str(resp.headers(), reqwest::header::LAST_MODIFIED);
        let content_length = resp.content_length();

        if status == 304 {
            return Ok(FetchResponse {
                status,
                body: String::new(),
                content_type,
                etag,
                last_modified,
                content_length,
                elapsed_ms: started.elapsed().as_millis() as u64,
                not_modified: true,
            });
        }

        if let Some(len) = content_length {
            if len as usize > self.max_body_bytes {
                return Err(CrawlError::BodyTooLarge(len as usize));
            }
        }

        let bytes = resp
            .bytes()
            .await
            .map_err(|e| CrawlError::Fetch { url: url.to_string(), reason: e.to_string() })?;
        if bytes.len() > self.max_body_bytes {
            return Err(CrawlError::BodyTooLarge(bytes.len()));
        }
        let body = String::from_utf8_lossy(&bytes).into_owned();

        Ok(FetchResponse {
            status,
            body,
            content_type,
            etag,
            last_modified,
            content_length,
            elapsed_ms: started.elapsed().as_millis() as u64,
            not_modified: false,
        })
    }
}

fn hv(s: &str) -> Result<HeaderValue> {
    HeaderValue::from_str(s)
        .map_err(|e| CrawlError::Fetch { url: "<header>".into(), reason: e.to_string() })
}

fn header_str(headers: &HeaderMap, name: reqwest::header::HeaderName) -> Option<String> {
    headers.get(name).and_then(|v| v.to_str().ok()).map(|s| s.to_string())
}
