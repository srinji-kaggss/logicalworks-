// src/main.rs — lgwks-human entry point
use std::{path::PathBuf, sync::{Arc, RwLock}};

use color_eyre::{eyre::WrapErr, Result};
use clap::Parser;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod app;
mod bridge;
mod screens;
mod tui;
mod ui;
mod util;

use app::{App, run};
use bridge::{DaemonBridge, DaemonState, spawn_poll_task};
use tui::Tui;

#[derive(Parser, Debug)]
#[command(
    name = "lgwks-human",
    about = "Human control surface for the lgwks daemon — flight control display for STEM tasks",
    long_about = None,
    version,
)]
struct Cli {
    /// Path to the lgwks repo root (auto-detected if omitted)
    #[arg(short = 'C', long, value_name = "PATH")]
    repo: Option<PathBuf>,

    /// Frames per second
    #[arg(long, default_value = "15")]
    fps: f64,

    /// Enable debug logging to /tmp/lgwks-human.log
    #[arg(short, long)]
    debug: bool,

    /// Run without auto-managing a daemon (read-only against existing daemon state;
    /// the CHAT pane still composes through the event bus). No separate model client.
    #[arg(long)]
    standalone: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    color_eyre::install()?;
    let cli = Cli::parse();

    // ── Logging ────────────────────────────────────────────────────────────
    // Write logs to a file so they don't corrupt the TUI
    if cli.debug {
        let log_file = std::fs::File::create("/tmp/lgwks-human.log")
            .context("could not open log file")?;
        tracing_subscriber::registry()
            .with(tracing_subscriber::fmt::layer().with_writer(log_file))
            .init();
    }

    // ── Repo root resolution ────────────────────────────────────────────────
    let repo_root = if let Some(r) = cli.repo {
        r.canonicalize().unwrap_or(r)
    } else if let Some(r) = find_repo_root() {
        r
    } else {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    };
    tracing::info!("Using repo root: {:?}", repo_root);

    // ── Bridge + shared state ───────────────────────────────────────────────
    let bridge = Arc::new(DaemonBridge::new(&repo_root));
    
    let event_count = if bridge.db_path.exists() {
        bridge.poll_events(0, 999999).map(|(evts, _)| evts.len()).unwrap_or(0)
    } else {
        0
    };

    eprintln!(
        "lgwks-human cockpit · daemon={} · db={} · events={}",
        bridge.read_status().status,
        bridge.db_path.display(),
        event_count
    );

    if !cli.standalone {
        let payload = serde_json::json!({ "msg": "cockpit_boot" }).to_string();
        let _ = bridge.run_daemon_write(&[
            "ops", "daemon", "emit",
            "--kind", "workflow_event",
            "--lane", "control",
            "--scope", "shared_referee",
            "--actor", "system",
            "--client", "system",
            "--tenant", bridge.tenant_id.as_str(),
            "--session-id", "system-boot",
            "--agent-id", "lgwks-human",
        ], &payload);
    }

    let state  = Arc::new(RwLock::new(DaemonState::default()));

    // ── TUI setup ──────────────────────────────────────────────────────────
    let tui = Tui::new()?
        .frame_rate(Some(cli.fps))
        .tick_rate(Some(4.0))
        .title(Some("lgwks-human".to_string()));

    let event_tx = tui.event_tx.clone();

    // ── Spawn background poll task (U-08) ───────────────────────────────────
    // The cockpit is a projection of the daemon bus — always run the live poll task so
    // the TUI is genuinely interactive. `--standalone` only means "don't auto-manage a
    // daemon" (it skips the boot emit above); it still reads whatever daemon state exists
    // and the CHAT pane composes through the bus. There is no separate in-TUI model client.
    let _poll_task = spawn_poll_task(Arc::clone(&bridge), Arc::clone(&state), event_tx);

    // ── App + run loop ──────────────────────────────────────────────────────
    let app = App::new(bridge, state);
    run(tui, app).await?;

    Ok(())
}

/// Walk up from cwd looking for a directory that contains lgwks_daemon.py
fn find_repo_root() -> Option<PathBuf> {
    let mut dir = std::env::current_dir().ok()?;
    for _ in 0..8 {
        if dir.join("lgwks_daemon.py").exists() || dir.join("lgwks").exists() {
            return Some(dir);
        }
        dir = dir.parent()?.to_path_buf();
    }
    None
}
