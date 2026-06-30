// src/screens/wire.rs — WIRE screen: daemon diagnostics / referee view
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
};

use crate::bridge::{DaemonState, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd};

pub struct WireScreen;

impl WireScreen {
    pub fn new() -> Self { Self }
}

impl Screen for WireScreen {
    fn on_daemon_tick(&mut self, _state: &DaemonState) {}
    fn handle_event(&mut self, _event: &Event, _state: &DaemonState) -> ScreenCmd { ScreenCmd::None }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(6),  // daemon health
                Constraint::Length(7),  // env & queue
                Constraint::Min(0),     // sessions / worktrees
                Constraint::Length(12), // sources panel
            ])
            .split(area);

        // ── Daemon health panel ──────────────────────────────────────────────
        let s = &state.status;
        let status_color = if s.alive { EMERALD } else { RED_ERR };
        let health_text = vec![
            Line::from(vec![
                Span::styled("  Status:     ", Style::default().fg(SLATE_DIM)),
                Span::styled(s.status.clone(), Style::default().fg(status_color).add_modifier(Modifier::BOLD)),
            ]),
            Line::from(vec![
                Span::styled("  PID:        ", Style::default().fg(SLATE_DIM)),
                Span::styled(
                    s.pid.map(|p| p.to_string()).unwrap_or_else(|| "—".to_string()),
                    Style::default().fg(CREAM),
                ),
            ]),
            Line::from(vec![
                Span::styled("  Repo:       ", Style::default().fg(SLATE_DIM)),
                Span::styled(s.repo_root.clone(), Style::default().fg(CREAM_DIM)),
            ]),
            Line::from(vec![
                Span::styled("  Heartbeat:  ", Style::default().fg(SLATE_DIM)),
                Span::styled(s.heartbeat_at.clone(), Style::default().fg(MUTED)),
            ]),
        ];

        let health_para = Paragraph::new(health_text)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(" DAEMON HEALTH ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD))));
        frame.render_widget(health_para, chunks[0]);

        // ── Environment & Queue ──────────────────────────────────────────────
        let queue_depth = state.queue.len();
        let e = &state.env_status;
        
        let up_style = Style::default().fg(EMERALD);
        let down_style = Style::default().fg(MUTED);
        
        let fmt_up = |b| if b { Span::styled("UP", up_style) } else { Span::styled("DOWN", down_style) };
        
        let queue_text = vec![
            Line::from(vec![
                Span::styled("  CANARY:     ", Style::default().fg(SLATE_DIM)),
                Span::styled(&e.canary_state, Style::default().fg(CREAM)),
            ]),
            Line::from(vec![
                Span::styled("  EXECUTORS:  ", Style::default().fg(SLATE_DIM)),
                Span::styled("opencode=", Style::default().fg(CREAM_DIM)), fmt_up(e.opencode_up),
                Span::styled(" · cursor=", Style::default().fg(CREAM_DIM)), fmt_up(e.cursor_up),
                Span::styled(" · agy=", Style::default().fg(CREAM_DIM)), fmt_up(e.agy_up),
                Span::styled(" · ollama=", Style::default().fg(CREAM_DIM)), fmt_up(e.ollama_up),
            ]),
            Line::from(vec![
                Span::styled("  QUEUE:      ", Style::default().fg(SLATE_DIM)),
                Span::styled(
                    format!("{queue_depth} items"),
                    Style::default().fg(if queue_depth > 0 { AMBER } else { CREAM }),
                ),
            ]),
            Line::from(vec![
                Span::styled("  CAP:        ", Style::default().fg(SLATE_DIM)),
                match e.cap_pct {
                    Some(p) => {
                        let tier = e.cap_tier.as_deref().unwrap_or("");
                        let col = match tier { "crit" => RED_ERR, "warn" => AMBER, _ => EMERALD };
                        let label = if tier.is_empty() { format!("{p}%") } else { format!("{p}% ({tier})") };
                        Span::styled(label, Style::default().fg(col).add_modifier(Modifier::BOLD))
                    }
                    None => Span::styled("— (no telemetry)", Style::default().fg(MUTED)),
                },
            ]),
        ];
        let queue_para = Paragraph::new(queue_text)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(" ENVIRONMENT & QUEUE ", Style::default().fg(AMBER).add_modifier(Modifier::BOLD))));
        frame.render_widget(queue_para, chunks[1]);

        // ── Active sessions / worktrees ───────────────────────────────────────
        let mut session_stats: std::collections::HashMap<String, (usize, String, String)> = std::collections::HashMap::new();
        
        // events is a ring buffer, newest LAST (push_back). To show true "last
        // activity" we must take the LAST event seen per session, so overwrite on
        // each hit — the previous `if is_empty()` guard kept the FIRST (oldest) one.
        for e in &state.events {
            if let Some(session_id) = &e.session_id {
                let entry = session_stats.entry(session_id.clone()).or_insert((0, String::new(), String::new()));
                entry.0 += 1;
                entry.1 = e.ts.clone().unwrap_or_else(|| "unknown time".to_string());
                entry.2 = e.kind.clone().unwrap_or_else(|| "unknown".to_string());
            }
        }

        let mut session_lines: Vec<Line> = vec![];
        if session_stats.is_empty() {
            session_lines.push(Line::from(vec![
                Span::styled("  No active sessions found in recent events.", Style::default().fg(MUTED)),
            ]));
        } else {
            session_lines.push(Line::from(vec![
                Span::styled(format!("  {:<15} │ {:<6} │ {:<20} │ {}", "SESSION ID", "EVENTS", "LAST ACTIVITY", "LATEST KIND"), Style::default().fg(AMBER).add_modifier(Modifier::BOLD)),
            ]));
            session_lines.push(Line::from(vec![Span::styled("  ────────────────┼────────┼──────────────────────┼───────────────────────", Style::default().fg(SLATE_DIM))]));
            
            let mut stats_vec: Vec<_> = session_stats.into_iter().collect();
            stats_vec.sort_by_key(|b| std::cmp::Reverse(b.1.0)); // Sort by event count descending
            
            for (sess, (count, last_ts, last_kind)) in stats_vec.into_iter().take(15) {
                // char-safe slicing — session ids / timestamps come from event data.
                let short_sess = crate::util::head(&sess, 15).to_string();
                // RFC3339 ts "HH:MM:SS" lives at chars 11..19 when present. Use the
                // canonical char-safe head (a multibyte ts can't land here in practice,
                // but keep the floor consistent with the rest of the crate).
                let short_ts = if last_ts.chars().count() >= 19 {
                    crate::util::head(&last_ts, 19).get(11..).unwrap_or(&last_ts).to_string()
                } else {
                    last_ts.clone()
                };
                session_lines.push(Line::from(vec![
                    Span::styled(format!("  {:<15} │ ", short_sess), Style::default().fg(CREAM)),
                    Span::styled(format!("{:<6} │ ", count), Style::default().fg(EMERALD_DIM)),
                    Span::styled(format!("{:<20} │ ", short_ts), Style::default().fg(SLATE)),
                    Span::styled(last_kind, Style::default().fg(CREAM_DIM)),
                ]));
            }
        }

        let sessions_para = Paragraph::new(session_lines)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(" ACTIVE SESSIONS ANALYSIS ", Style::default().fg(SLATE))));
        frame.render_widget(sessions_para, chunks[2]);

        // ── SOURCES (RAG registry) panel ─────────────────────────────────────
        const SOURCES: &[(&str, &str, &str)] = &[
            ("R1", "Unified Agent Brain", "PRIMARY semantic/code index"),
            ("R2", "Agent Intelligence brain", "failure modes + lessons (query before retrying)"),
            ("R3", "Logic-OS Laws", "governance source-of-truth"),
            ("R4", "AI-Research-Skills", "RAG + agent engineering principles"),
            ("R5", "Cursor Market Blueprint", "agentic-IDE reference architecture"),
            ("R6", "Blackbox2 shared brain", "live session state"),
            ("R7", "Auto-memory", "persistent identity/feedback/project"),
            ("R8", "Ingestion extras", "domain + structure"),
        ];

        let mut source_lines: Vec<Line> = vec![];
        for (id, name, purpose) in SOURCES {
            source_lines.push(Line::from(vec![
                Span::styled(format!("  {}  ", id), Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
                Span::styled(name.to_string(), Style::default().fg(CREAM)),
                Span::styled(" — ", Style::default().fg(SLATE_DIM)),
                Span::styled(purpose.to_string(), Style::default().fg(CREAM_DIM)),
            ]));
        }

        let sources_para = Paragraph::new(source_lines)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(" SOURCES (RAG registry) ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD))));
        frame.render_widget(sources_para, chunks[3]);
    }
}
