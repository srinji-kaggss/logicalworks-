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
