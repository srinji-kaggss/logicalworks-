use anyhow::Result;
use rusqlite::Connection;
use std::path::{Path, PathBuf};
use crate::models::{DaemonEvent, WorkItem, DaemonStatus, NavMapIndex};
use std::fs;

pub struct Db {
    db_path: PathBuf,
    state_path: PathBuf,
    navmap_path: PathBuf,
}

impl Db {
    pub fn new(repo_root: &Path) -> Self {
        let daemon_dir = repo_root.join("store").join("daemon");
        Self {
            db_path: daemon_dir.join("daemon-events.db"),
            state_path: daemon_dir.join("daemon.state.json"),
            navmap_path: repo_root.join("docs").join("navmap").join("index.json"),
        }
    }

    pub fn get_navmap(&self) -> Result<NavMapIndex> {
        if !self.navmap_path.exists() {
            return Err(anyhow::anyhow!("NavMap not found at {:?}", self.navmap_path));
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
                repo_root: "".to_string(),
                heartbeat_at: "".to_string(),
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

    pub fn emit_telemetry(&self, lane: &str, kind: &str, scope: &str, payload_msg: &str) -> Result<()> {
        let repo_path = std::env::current_dir()?;
        let tenant_id = format!("repo:{}", repo_path.file_name().unwrap_or_default().to_string_lossy());
        
        let payload = serde_json::json!({
            "message": payload_msg,
        });

        // Layer 4: Debug Instrumentation & Telemetry Audit
        // Use std::process::Command to securely execute the emit command, avoiding shell injection.
        let status = std::process::Command::new("python3")
            .args([
                "lgwks", "daemon", "emit",
                "--lane", lane,
                "--kind", kind,
                "--scope", scope,
                "--tenant", &tenant_id,
                "--session-id", "tui_session",
                "--agent-id", "tui",
            ])
            .current_dir(&repo_path)
            .env("LGWKS_DAEMON_DB", self.db_path.to_str().unwrap_or(""))
            // We pass the payload via stdin to avoid exposing it to process arguments.
            .stdin(std::process::Stdio::piped())
            .spawn();

        if let Ok(mut child) = status {
            if let Some(mut stdin) = child.stdin.take() {
                use std::io::Write;
                let _ = stdin.write_all(payload.to_string().as_bytes());
            }
            let _ = child.wait();
        }

        Ok(())
    }
}
