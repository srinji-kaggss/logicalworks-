use anyhow::{Result, anyhow};
use rusqlite::Connection;
use std::path::{Path, PathBuf};
use crate::models::{DaemonEvent, WorkItem, DaemonStatus, NavMapIndex, WorkflowDef, HarvestMetrics, ModelCatalog};
use std::fs;
use std::collections::HashMap;

pub struct Db {
    repo_root: PathBuf,
    script_path: PathBuf,
    db_path: PathBuf,
    state_path: PathBuf,
    navmap_path: PathBuf,
}

impl Db {
    pub fn new(repo_root: &Path) -> Self {
        let daemon_dir = repo_root.join("store").join("daemon");
        Self {
            repo_root: repo_root.to_path_buf(),
            script_path: repo_root.join("lgwks"),
            db_path: daemon_dir.join("daemon-events.db"),
            state_path: daemon_dir.join("daemon.state.json"),
            navmap_path: repo_root.join("docs").join("navmap").join("index.json"),
        }
    }

    pub fn get_workflows(&self) -> Result<HashMap<String, WorkflowDef>> {
        let output = std::process::Command::new("python3")
            .args([self.script_path.to_str().unwrap_or("lgwks"), "workflow", "list", "--json"])
            .current_dir(&self.repo_root)
            .output()?;
        
        if !output.status.success() {
            return Err(anyhow!("Failed to list workflows: {}", String::from_utf8_lossy(&output.stderr)));
        }

        let workflows: HashMap<String, WorkflowDef> = serde_json::from_slice(&output.stdout)?;
        Ok(workflows)
    }

    /// The unified two-plane model catalog, sourced from the Python selector
    /// (`lgwks models list --json`). Offline-safe: the Python side serves a cached
    /// cloud snapshot, so this never depends on the network.
    pub fn get_model_catalog(&self) -> Result<ModelCatalog> {
        let output = std::process::Command::new("python3")
            .args([self.script_path.to_str().unwrap_or("lgwks"), "models", "list", "--json"])
            .current_dir(&self.repo_root)
            .output()?;
        if !output.status.success() {
            return Err(anyhow!("models list failed: {}", String::from_utf8_lossy(&output.stderr)));
        }
        let catalog: ModelCatalog = serde_json::from_slice(&output.stdout)?;
        Ok(catalog)
    }

    pub fn get_navmap(&self) -> Result<NavMapIndex> {
        if !self.navmap_path.exists() {
            return Err(anyhow!("NavMap not found at {:?}", self.navmap_path));
        }
        let content = fs::read_to_string(&self.navmap_path)?;
        let index: NavMapIndex = serde_json::from_str(&content)?;
        Ok(index)
    }

    pub fn get_status(&self) -> Result<DaemonStatus> {
        if !self.state_path.exists() {
            return Ok(DaemonStatus {
                pid: None,
                status: "stopped".to_string(),
                repo_root: self.repo_root.to_string_lossy().to_string(),
                heartbeat_at: "".to_string(),
                alive: false,
                lock_present: false,
            });
        }
        let content = fs::read_to_string(&self.state_path)?;
        let status: DaemonStatus = serde_json::from_str(&content)?;
        Ok(status)
    }

    pub fn get_events(&self, limit: usize) -> Result<Vec<DaemonEvent>> {
        if !self.db_path.exists() {
            return Ok(vec![]);
        }
        let conn = Connection::open(&self.db_path)?;
        let mut stmt = conn.prepare(
            "SELECT raw_json FROM daemon_events ORDER BY ts DESC, event_id DESC LIMIT ?"
        )?;
        let rows = stmt.query_map([limit], |row| {
            let raw_json: String = row.get(0)?;
            Ok(raw_json)
        })?;

        let mut events = Vec::new();
        for row in rows {
            if let Ok(raw) = row {
                if let Ok(event) = serde_json::from_str::<DaemonEvent>(&raw) {
                    events.push(event);
                }
            }
        }
        Ok(events)
    }

    pub fn get_queue(&self, limit: usize) -> Result<Vec<WorkItem>> {
        if !self.db_path.exists() {
            return Ok(vec![]);
        }
        let conn = Connection::open(&self.db_path)?;
        let mut stmt = conn.prepare(
            "SELECT item_id, tenant_id, session_id, agent_id, kind, priority, status, payload_json, enqueued_at, started_at, done_at, error 
             FROM daemon_work_queue 
             ORDER BY priority DESC, enqueued_at ASC 
             LIMIT ?"
        )?;
        
        let rows = stmt.query_map([limit], |row| {
            Ok(WorkItem {
                item_id: row.get(0)?,
                tenant_id: row.get(1)?,
                session_id: row.get(2)?,
                agent_id: row.get(3)?,
                kind: row.get(4)?,
                priority: row.get(5)?,
                status: row.get(6)?,
                payload: serde_json::from_str(&row.get::<_, String>(7)?).unwrap_or_default(),
                enqueued_at: row.get(8)?,
                started_at: row.get(9)?,
                done_at: row.get(10)?,
                error: row.get(11)?,
            })
        })?;

        let mut items = Vec::new();
        for row in rows {
            if let Ok(item) = row {
                items.push(item);
            }
        }
        Ok(items)
    }

    pub fn get_thoughts(&self, limit: usize) -> Result<Vec<serde_json::Value>> {
        let cognition_dir = self.repo_root.join("store").join("cognition");
        if !cognition_dir.exists() {
            return Ok(vec![]);
        }
        
        let mut entries = fs::read_dir(cognition_dir)?
            .filter_map(|e| e.ok())
            .filter(|e| e.file_name().to_string_lossy().ends_with(".jsonl"))
            .collect::<Vec<_>>();
        
        entries.sort_by_key(|e| e.metadata().and_then(|m| m.modified()).ok());
        
        if let Some(entry) = entries.last() {
            let content = fs::read_to_string(entry.path())?;
            let mut thoughts = Vec::new();
            for line in content.lines().rev().take(limit) {
                if let Ok(v) = serde_json::from_str::<serde_json::Value>(line) {
                    thoughts.push(v);
                }
            }
            Ok(thoughts)
        } else {
            Ok(vec![])
        }
    }

    pub fn get_harvest_metrics(&self) -> Result<HarvestMetrics> {
        let store_dir = self.repo_root.join("store");
        let cortex_dir = store_dir.join("cortex");
        let cognition_dir = store_dir.join("cognition");
        
        let mut turns = 0;
        
        // Count from store/cortex (*.cortex.jsonl)
        if let Ok(entries) = fs::read_dir(&cortex_dir) {
            for entry in entries.filter_map(|e| e.ok()) {
                if entry.file_name().to_string_lossy().ends_with(".cortex.jsonl") {
                    if let Ok(content) = fs::read_to_string(entry.path()) {
                        turns += content.lines().count() as u32;
                    }
                }
            }
        }

        // Count from store/cognition (*.cognition.jsonl)
        if let Ok(entries) = fs::read_dir(&cognition_dir) {
            for entry in entries.filter_map(|e| e.ok()) {
                if entry.file_name().to_string_lossy().ends_with(".cognition.jsonl") {
                    if let Ok(content) = fs::read_to_string(entry.path()) {
                        turns += content.lines().count() as u32;
                    }
                }
            }
        }

        let goal = 1_000_000;
        let coverage = (turns as f32 / goal as f32).min(1.0);
        let gap = 1.0 - coverage;

        Ok(HarvestMetrics {
            turns_collected: turns,
            goal,
            coverage,
            gap,
            confidence: 0.92, // Placeholder until P-Engine lands
            streams: vec![
                "cognition.jsonl".into(),
                "learning-records.jsonl".into(),
                "token-ledger.jsonl".into(),
                "daemon-events.db".into(),
                "fleet-audit.jsonl".into(),
                "transcript.jsonl".into(),
            ],
        })
    }

    pub fn emit_telemetry(&self, lane: &str, kind: &str, scope: &str, payload_msg: &str) -> Result<()> {
        let tenant_id = format!("repo:{}", self.repo_root.file_name().unwrap_or_default().to_string_lossy());
        let payload = serde_json::json!({ "message": payload_msg });

        let mut child = std::process::Command::new("python3")
            .args([
                self.script_path.to_str().unwrap_or("lgwks"), "daemon", "emit",
                "--lane", lane, "--kind", kind, "--scope", scope,
                "--tenant", &tenant_id, "--session-id", "tui_session", "--agent-id", "tui",
            ])
            .current_dir(&self.repo_root)
            .stdin(std::process::Stdio::piped())
            .spawn()?;

        if let Some(mut stdin) = child.stdin.take() {
            use std::io::Write;
            let _ = stdin.write_all(payload.to_string().as_bytes());
        }
        let _ = child.wait();
        Ok(())
    }
}
