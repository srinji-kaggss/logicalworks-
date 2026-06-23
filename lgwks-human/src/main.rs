// src/main.rs — lgwks-human entry point
use std::{path::PathBuf, sync::{Arc, RwLock}};

use color_eyre::{eyre::{ContextCompat, WrapErr}, Result};
use clap::Parser;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod app;
mod bridge;
mod screens;
mod tui;
mod ui;

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
        r
    } else {
        find_repo_root().context(
            "could not find lgwks repo root. pass --repo /path/to/logicalworks- or cd into it"
        )?
    };
    tracing::info!("Using repo root: {:?}", repo_root);

    // ── Bridge + shared state ───────────────────────────────────────────────
    let bridge = Arc::new(DaemonBridge::new(&repo_root));
    let state  = Arc::new(RwLock::new(DaemonState::default()));

    // ── TUI setup ──────────────────────────────────────────────────────────
    let tui = Tui::new()?
        .frame_rate(Some(cli.fps))
        .tick_rate(Some(4.0))
        .title(Some("lgwks-human".to_string()));

    // ── Spawn background poll task (U-08) ───────────────────────────────────
    // Uses the event_tx clone from the Tui to send DaemonTick events
    // We need the Tui's sender — clone it before moving Tui into run()
    let event_tx = tui.event_tx.clone();
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
