use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DaemonEvent {
    pub event_id: String,
    pub tenant_id: String,
    pub agent_id: String,
    pub session_id: String,
    pub actor: String,
    pub client: String,
    pub lane: String,
    pub kind: String,
    pub scope: String,
    pub ts: String,
    pub payload: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkItem {
    pub item_id: String,
    pub tenant_id: String,
    pub session_id: String,
    pub agent_id: String,
    pub kind: String,
    pub priority: i32,
    pub status: String,
    pub payload: Value,
    pub enqueued_at: String,
    pub started_at: Option<String>,
    pub done_at: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DaemonStatus {
    pub pid: Option<u32>,
    pub status: String,
    pub repo_root: String,
    pub heartbeat_at: String,
    pub alive: bool,
    pub lock_present: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowDef {
    pub description: String,
    pub args: HashMap<String, String>,
    pub verbs: Vec<String>,
    pub tokens: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NavModule {
    pub purpose: String,
    pub loc: u32,
    pub staleness: String,
    pub subsystem: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NavMapIndex {
    pub modules: HashMap<String, NavModule>,
}

// ── Model selector (epic #335 / S3 #338) ────────────────────────────────────
// Mirror of `lgwks models list --json` (lgwks.model.catalog.v1). The TUI holds
// NO catalog of its own — these structs only deserialize the Python projection.
#[derive(Debug, Clone, Deserialize)]
pub struct LocalModel {
    pub role: String,
    pub law_name: String,
    pub runtime_id: String,
    #[serde(default)]
    pub trust_class: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct CloudProvider {
    pub id: String,
    pub models: u32,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct CloudPlane {
    #[serde(default)]
    pub opt_in: bool,
    #[serde(default)]
    pub providers: Vec<CloudProvider>,
    #[serde(default)]
    pub degraded: bool,
    // NOTE: the catalog JSON also carries `models` (per-provider drilldown from
    // `models list --provider X`). The TUI does not drill in yet, so it is left
    // out here — serde ignores the extra field until that screen lands.
}

#[derive(Debug, Clone, Deserialize)]
pub struct ModelCatalog {
    pub active_locality: String,
    pub default_locality: String,
    pub local: Vec<LocalModel>,
    #[serde(default)]
    pub cloud: CloudPlane,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HarvestMetrics {
    pub turns_collected: u32,
    pub goal: u32,
    pub coverage: f32,
    pub gap: f32,
    pub confidence: f32,
    pub streams: Vec<String>,
}
