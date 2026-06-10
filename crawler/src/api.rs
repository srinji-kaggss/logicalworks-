//! HTTP API — the SAME contract the AI calls and the end-product frontend calls.
//! POST /crawl {CrawlRequest} -> CrawlResult (lgwks.crawl.v1); GET /healthz.
//! Errors return a typed JSON envelope, never a raw string or a 500 with no body.

use crate::config::{CrawlConfig, StealthLevel};
use crate::engine::Engine;
use crate::schema::CrawlResult;
use axum::{
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CrawlRequest {
    pub url: String,
    #[serde(default)]
    pub max_pages: Option<usize>,
    #[serde(default)]
    pub max_depth: Option<u32>,
    #[serde(default)]
    pub stealth: Option<StealthLevel>,
    #[serde(default)]
    pub allow_offsite: Option<bool>,
    #[serde(default)]
    pub respect_robots: Option<bool>,
    #[serde(default)]
    pub min_host_delay_ms: Option<u64>,
    #[serde(default)]
    pub best_first: Option<bool>,
}

impl CrawlRequest {
    pub fn into_config(&self) -> CrawlConfig {
        let mut c = CrawlConfig::default();
        if let Some(v) = self.max_pages { c.max_pages = v; }
        if let Some(v) = self.max_depth { c.max_depth = v; }
        if let Some(v) = self.stealth { c.stealth = v; }
        if let Some(v) = self.allow_offsite { c.allow_offsite = v; }
        if let Some(v) = self.respect_robots { c.respect_robots = v; }
        if let Some(v) = self.min_host_delay_ms { c.min_host_delay_ms = v; }
        if let Some(v) = self.best_first { c.best_first = v; }
        c
    }
}

#[derive(Serialize)]
struct ErrorEnvelope {
    error: String,
    code: String,
}

pub fn router() -> Router {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/crawl", post(crawl_handler))
        .route("/gather", post(gather_handler))
}

/// The unified entry — `POST /gather {GatherRequest}`. This is the one route the
/// AI and the end-product call; map/crawl/scrape are modes, not endpoints.
async fn gather_handler(
    Json(req): Json<crate::gather::GatherRequest>,
) -> Result<Json<CrawlResult>, (StatusCode, Json<ErrorEnvelope>)> {
    crate::gather::gather(&req).await.map(Json).map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ErrorEnvelope { error: e.to_string(), code: e.code().to_string() }),
        )
    })
}

async fn healthz() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "ok": true, "schema": crate::schema::SCHEMA_VERSION }))
}

async fn crawl_handler(
    Json(req): Json<CrawlRequest>,
) -> Result<Json<CrawlResult>, (StatusCode, Json<ErrorEnvelope>)> {
    let cfg = req.into_config();
    let engine = Engine::new(cfg).map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(ErrorEnvelope { error: e.to_string(), code: e.code().to_string() }),
        )
    })?;
    let result = engine.crawl(&req.url).await;
    Ok(Json(result))
}

/// Bind and serve until shutdown.
pub async fn serve(addr: &str) -> anyhow::Result<()> {
    let listener = tokio::net::TcpListener::bind(addr).await?;
    tracing::info!(%addr, "lgwks-crawler API listening");
    axum::serve(listener, router()).await?;
    Ok(())
}
