//! Typed errors. No silent failures: every recoverable fault carries a code the
//! caller can branch on. //why thiserror over anyhow at the lib boundary so the
//! API layer can map kinds → HTTP status deterministically.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum CrawlError {
    #[error("invalid url: {0}")]
    InvalidUrl(String),

    #[error("host not allowed by policy: {0}")]
    HostNotAllowed(String),

    #[error("blocked by robots.txt: {0}")]
    RobotsDisallowed(String),

    #[error("fetch failed for {url}: {reason}")]
    Fetch { url: String, reason: String },

    #[error("http status {status} for {url}")]
    HttpStatus { url: String, status: u16 },

    #[error("body too large: {0} bytes")]
    BodyTooLarge(usize),

    #[error("robots fetch/parse failed: {0}")]
    Robots(String),

    #[error("io: {0}")]
    Io(#[from] std::io::Error),
}

/// Stable machine code for each error kind — emitted in the frontier audit log
/// and the API error envelope so consumers never parse human strings.
impl CrawlError {
    pub fn code(&self) -> &'static str {
        match self {
            CrawlError::InvalidUrl(_) => "invalid_url",
            CrawlError::HostNotAllowed(_) => "host_not_allowed",
            CrawlError::RobotsDisallowed(_) => "robots_disallowed",
            CrawlError::Fetch { .. } => "fetch_failed",
            CrawlError::HttpStatus { .. } => "http_status",
            CrawlError::BodyTooLarge(_) => "body_too_large",
            CrawlError::Robots(_) => "robots_error",
            CrawlError::Io(_) => "io_error",
        }
    }
}

pub type Result<T> = std::result::Result<T, CrawlError>;
