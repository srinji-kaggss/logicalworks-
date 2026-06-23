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

    /// Run in standalone mode without a daemon (connects to local LLMs or models.dev API)
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
    let repo_root = if cli.standalone {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    } else if let Some(r) = cli.repo {
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

    let event_tx = tui.event_tx.clone();

    // ── Spawn background poll task (U-08) ───────────────────────────────────
    if cli.standalone {
        tracing::info!("Running in STANDALONE mode");
        let state_clone = Arc::clone(&state);
        tokio::spawn(async move {
            // Seed the state with a standalone stub
            {
                let mut st = state_clone.write().unwrap();
                st.status.alive = true;
                st.status.status = "standalone".to_string();
                st.packet = bridge::ContextPacket {
                    active_task: Some("Standalone Mode".to_string()),
                    next_steps: vec![
                        bridge::NextStep {
                            kind: "connect_models_dev".to_string(),
                            summary: "Configure models.dev API token".to_string(),
                            risk: Some("low".to_string()),
                            args: None,
                            provenance: Some(serde_json::json!({
                                "reason": "Standalone mode initialized without provider keys."
                            })),
                        },
                        bridge::NextStep {
                            kind: "init_local_llm".to_string(),
                            summary: "Start a local model (Ollama/Llama.cpp)".to_string(),
                            risk: Some("low".to_string()),
                            args: None,
                            provenance: Some(serde_json::json!({
                                "reason": "Optionally use local resources."
                            })),
                        }
                    ],
                    ..Default::default()
                };
            }
            // Just periodically send ticks to refresh UI
            let mut tick_count = 0;
            loop {
                tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
                tick_count += 1;
                {
                    let mut st = state_clone.write().unwrap();
                    // Generate a noisy sine wave for entropy
                    let v = ((tick_count as f64 * 0.1).sin() * 50.0 + 50.0 + (rand::random::<f64>() * 20.0)) as u64;
                    st.packet.entropy_history.push(v);
                    if st.packet.entropy_history.len() > 100 {
                        st.packet.entropy_history.remove(0);
                    }
                    st.packet.tps = 45.0 + (rand::random::<f32>() * 10.0);
                    
                    // Simulate steering dials drift
                    let dials = vec![
                        ("safety".to_string(), 0.8 + (rand::random::<f32>() * 0.1)),
                        ("creativity".to_string(), 0.4 + (rand::random::<f32>() * 0.2)),
                        ("formality".to_string(), 0.9),
                        ("deception".to_string(), rand::random::<f32>() * 0.05),
                    ];
                    st.packet.steering_dials = dials;
                }
                let _ = event_tx.send(tui::Event::DaemonTick);
            }
        });
    } else {
        let _poll_task = spawn_poll_task(Arc::clone(&bridge), Arc::clone(&state), event_tx);
    }

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
