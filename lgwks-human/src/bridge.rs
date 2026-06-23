// src/bridge.rs — DaemonBridge: reads daemon-events.db + state, emits intent
// Ported from the existing tui/src/db.rs (Rust, our own code) + lgwks_daemon_store.py schema
use color_eyre::{eyre::eyre as anyhow, Result};
use color_eyre::eyre::WrapErr;
use rusqlite::Connection;
use serde::{Deserialize, Serialize};
use std::{
    collections::VecDeque,
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::{Arc, RwLock},
};

// ── Palette ────────────────────────────────────────────────────────────────
// Matches lgwks_ui.py — single source of truth lives here, render modules import
pub mod palette {
    use ratatui::style::Color;
    // Opencode-like rich dark palette
    pub const BG_MAIN:     Color = Color::Rgb(8, 8, 8); // Rich black
    pub const SLATE:       Color = Color::Rgb(160, 160, 175);
    pub const SLATE_DIM:   Color = Color::Rgb(80, 80, 95);
    pub const CREAM:       Color = Color::Rgb(240, 240, 245);
    pub const CREAM_DIM:   Color = Color::Rgb(190, 190, 200);
    pub const EMERALD:     Color = Color::Rgb(0, 255, 170); // Neon green/cyan
    pub const EMERALD_DIM: Color = Color::Rgb(0, 120, 80);
    pub const AMBER:       Color = Color::Rgb(255, 180, 0); // Warning/Highlight
    pub const MUTED:       Color = Color::Rgb(100, 100, 110);
    pub const RED_ERR:     Color = Color::Rgb(255, 60, 80);
}

// ── Data models ────────────────────────────────────────────────────────────
// Mirrors lgwks.daemon.event.v1 envelope

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DaemonEvent {
    pub event_id:   Option<String>,
    pub ts:         Option<String>,
    pub tenant_id:  Option<String>,
    pub agent_id:   Option<String>,
    pub session_id: Option<String>,
    pub lane:       Option<String>,
    pub kind:       Option<String>,
    pub scope:      Option<String>,
    pub actor:      Option<String>,
    pub payload:    Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DaemonStatus {
    pub pid:          Option<i64>,
    pub status:       String,
    pub repo_root:    String,
    pub heartbeat_at: String,
    pub alive:        bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct WorkItem {
    pub item_id:     String,
    pub tenant_id:   String,
    pub session_id:  String,
    pub agent_id:    String,
    pub kind:        String,
    pub priority:    i64,
    pub status:      String,
    pub payload:     serde_json::Value,
    pub enqueued_at: String,
    pub started_at:  Option<String>,
    pub done_at:     Option<String>,
    pub error:       Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ResearchRun {
    pub run_id:     String,
    pub target_url: Option<String>,
    pub status:     String,
    pub created_at: Option<String>,
    pub done_at:    Option<String>,
}

/// A context packet section — the affordance list surfaced in FLIGHT screen
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ContextPacket {
    pub session_head:       Option<serde_json::Value>,
    pub next_steps:         Vec<NextStep>,
    pub active_task:        Option<String>,
    pub recent_event_count: usize,
    pub telemetry:          Option<Vec<serde_json::Value>>,
    pub provenance:         Option<serde_json::Value>,
    pub entropy_history:    Vec<u64>,
    pub tps:                f32,
    pub steering_dials:     Vec<(String, f32)>, // Vector of (Name, Value [0-1])
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct NextStep {
    pub kind:       String,
    pub summary:    String,
    pub risk:       Option<String>,
    pub args:       Option<serde_json::Value>,
    pub provenance: Option<serde_json::Value>,
}

/// Shared daemon state — kept in an Arc<RwLock<>> so the poll task and render thread
/// can both access it without blocking the TUI loop.
#[derive(Debug, Default)]
pub struct DaemonState {
    pub status:  DaemonStatus,
    pub events:  VecDeque<DaemonEvent>,  // ring buffer, newest last
    pub queue:   Vec<WorkItem>,
    pub runs:    Vec<ResearchRun>,
    pub packet:  ContextPacket,
    pub last_event_id: Option<i64>,       // for incremental poll
}

impl DaemonState {
    pub fn push_event(&mut self, e: DaemonEvent) {
        if self.events.len() >= 500 {
            self.events.pop_front();
        }
        self.events.push_back(e);
    }
}

// ── Bridge ─────────────────────────────────────────────────────────────────

pub struct DaemonBridge {
    pub repo_root:   PathBuf,
    pub db_path:     PathBuf,
    pub state_path:  PathBuf,
    pub script_path: PathBuf,
    pub tenant_id:   String,
}

impl DaemonBridge {
    pub fn new(repo_root: &Path) -> Self {
        let daemon_dir = repo_root.join("store").join("daemon");
        let repo_name = repo_root
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        Self {
            repo_root:   repo_root.to_path_buf(),
            db_path:     daemon_dir.join("daemon-events.db"),
            state_path:  daemon_dir.join("daemon.state.json"),
            script_path: repo_root.join("lgwks"),
            tenant_id:   format!("repo:{}", repo_name),
        }
    }

    /// Poll daemon-events.db for new events since last_event_rowid.
    /// Returns (new_events, new_last_rowid). WAL-safe read-only connection.
    pub fn poll_events(&self, after_rowid: i64, limit: usize) -> Result<(Vec<DaemonEvent>, i64)> {
        if !self.db_path.exists() {
            return Ok((vec![], after_rowid));
        }
        // Open read-only in WAL mode — safe to run concurrently with daemon writer
        let conn = Connection::open_with_flags(
            &self.db_path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_URI,
        )?;
        // WAL mode: set journal_mode pragmas for safety
        conn.pragma_update(None, "journal_mode", "WAL").ok();
        conn.pragma_update(None, "query_only", true).ok();

        let mut stmt = conn.prepare(
            "SELECT rowid, raw_json FROM daemon_events
             WHERE rowid > ?1
             ORDER BY rowid ASC
             LIMIT ?2",
        )?;

        let mut events = vec![];
        let mut last_rowid = after_rowid;

        let rows = stmt.query_map(rusqlite::params![after_rowid, limit as i64], |row| {
            let rowid: i64 = row.get(0)?;
            let raw: String = row.get(1)?;
            Ok((rowid, raw))
        })?;

        for row in rows.flatten() {
            let (rowid, raw) = row;
            if let Ok(evt) = serde_json::from_str::<DaemonEvent>(&raw) {
                events.push(evt);
                last_rowid = rowid;
            }
        }

        Ok((events, last_rowid))
    }

    /// Read daemon.state.json — fast, just a file read
    pub fn read_status(&self) -> DaemonStatus {
        if !self.state_path.exists() {
            return DaemonStatus { status: "stopped".into(), ..Default::default() };
        }
        let Ok(raw) = fs::read_to_string(&self.state_path) else {
            return DaemonStatus { status: "error".into(), ..Default::default() };
        };
        serde_json::from_str::<DaemonStatus>(&raw).unwrap_or_else(|_| DaemonStatus {
            status: "parse_error".into(),
            ..Default::default()
        })
    }

    /// Read work queue items
    pub fn poll_queue(&self, limit: usize) -> Result<Vec<WorkItem>> {
        if !self.db_path.exists() { return Ok(vec![]); }
        let conn = Connection::open_with_flags(
            &self.db_path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
        )?;
        conn.pragma_update(None, "query_only", true).ok();
        let mut stmt = conn.prepare(
            "SELECT item_id, tenant_id, session_id, agent_id, kind, priority,
                    status, payload_json, enqueued_at, started_at, done_at, error
             FROM daemon_work_queue
             ORDER BY priority DESC, enqueued_at ASC
             LIMIT ?1",
        )?;
        let rows = stmt.query_map([limit as i64], |row| {
            Ok(WorkItem {
                item_id:     row.get(0)?,
                tenant_id:   row.get(1)?,
                session_id:  row.get(2)?,
                agent_id:    row.get(3)?,
                kind:        row.get(4)?,
                priority:    row.get(5)?,
                status:      row.get(6)?,
                payload:     serde_json::from_str(&row.get::<_, String>(7)?).unwrap_or_default(),
                enqueued_at: row.get(8)?,
                started_at:  row.get(9)?,
                done_at:     row.get(10)?,
                error:       row.get(11)?,
            })
        })?;
        Ok(rows.flatten().collect())
    }

    /// Read daemon_runs table
    pub fn poll_runs(&self, limit: usize) -> Result<Vec<ResearchRun>> {
        if !self.db_path.exists() { return Ok(vec![]); }
        let conn = Connection::open_with_flags(
            &self.db_path,
            rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY,
        )?;
        conn.pragma_update(None, "query_only", true).ok();
        // daemon_runs may not exist on older daemon versions — return empty gracefully
        let exists: bool = conn.query_row(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='daemon_runs'",
            [],
            |r| r.get::<_, i64>(0),
        ).map(|c| c > 0).unwrap_or(false);
        if !exists { return Ok(vec![]); }

        let mut stmt = conn.prepare(
            "SELECT run_id, target_url, status, created_at, done_at
             FROM daemon_runs
             ORDER BY created_at DESC
             LIMIT ?1",
        )?;
        let rows = stmt.query_map([limit as i64], |row| {
            Ok(ResearchRun {
                run_id:     row.get(0)?,
                target_url: row.get(1)?,
                status:     row.get(2)?,
                created_at: row.get(3)?,
                done_at:    row.get(4)?,
            })
        })?;
        Ok(rows.flatten().collect())
    }

    /// Emit an intent work item into the daemon via `lgwks daemon emit`.
    /// This is the human→daemon write path. Fails silently to keep TUI alive.
    pub fn emit_intent(
        &self,
        kind: &str,
        scope: &str,
        session_id: &str,
        payload_json: &str,
    ) -> Result<()> {
        let python = self.venv_python();
        let mut child = Command::new(&python)
            .args([
                self.script_path.to_str().unwrap_or("lgwks"),
                "daemon", "emit",
                "--lane", "human",
                "--kind", kind,
                "--scope", scope,
                "--tenant", &self.tenant_id,
                "--session-id", session_id,
                "--agent-id", "lgwks-human",
            ])
            .current_dir(&self.repo_root)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .map_err(|e| anyhow!("emit spawn failed: {e}"))?;

        if let Some(mut stdin) = child.stdin.take() {
            use std::io::Write;
            let _ = stdin.write_all(payload_json.as_bytes());
        }
        child.wait().ok();
        Ok(())
    }

    fn venv_python(&self) -> String {
        let venv = self.repo_root.join(".venv").join("bin").join("python");
        if venv.exists() { venv.to_string_lossy().to_string() } else { "python3".to_string() }
    }
}

// ── Background poll task ───────────────────────────────────────────────────
/// Spawns a tokio task that polls the daemon every 250ms and updates shared DaemonState.
/// Sends Event::DaemonTick through the TUI channel after each poll cycle so the render
/// loop knows to redraw. Never panics — errors are swallowed and surfaced in status.
pub fn spawn_poll_task(
    bridge: Arc<DaemonBridge>,
    state: Arc<RwLock<DaemonState>>,
    tx: tokio::sync::mpsc::UnboundedSender<crate::tui::Event>,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_millis(250));
        loop {
            interval.tick().await;

            // Read current last_event_id under read lock
            let last_rowid = {
                state.read().map(|s| s.last_event_id.unwrap_or(0)).unwrap_or(0)
            };

            // Poll everything outside the lock
            let new_events = bridge.poll_events(last_rowid, 100).ok();
            let new_status = bridge.read_status();
            let new_queue = bridge.poll_queue(50).ok().unwrap_or_default();
            let new_runs = bridge.poll_runs(30).ok().unwrap_or_default();

            // Write under write lock
            if let Ok(mut s) = state.write() {
                s.status = new_status;
                s.queue = new_queue;
                s.runs = new_runs;
                if let Some((events, new_last)) = new_events {
                    for e in events {
                        s.push_event(e);
                    }
                    if new_last > last_rowid {
                        s.last_event_id = Some(new_last);
                    }
                }
            }

            // Signal the TUI loop to redraw
            let _ = tx.send(crate::tui::Event::DaemonTick);
        }
    })
}
