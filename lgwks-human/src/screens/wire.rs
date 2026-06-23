// src/screens/wire.rs — WIRE screen: daemon diagnostics / referee view
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Gauge, Paragraph},
};

use crate::bridge::{DaemonState, DaemonStatus, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd, ScreenId};

pub struct WireScreen;

impl WireScreen {
    pub fn new() -> Self { Self }
}

impl Screen for WireScreen {
    fn id(&self) -> ScreenId { ScreenId::Wire }
    fn on_daemon_tick(&mut self, _state: &DaemonState) {}
    fn handle_event(&mut self, _event: &Event, _state: &DaemonState) -> ScreenCmd { ScreenCmd::None }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(6),  // daemon health
                Constraint::Length(5),  // harvest bar
                Constraint::Min(0),     // sessions / worktrees
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

        // ── Harvest progress bar (toward 1M RLHF turns) ──────────────────────
        // TODO: pull from harvest_metrics when available
        let harvest_gauge = Gauge::default()
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(" HARVEST PROGRESS ", Style::default().fg(AMBER))))
            .gauge_style(Style::default().fg(EMERALD).bg(SLATE_DIM))
            .ratio(0.0)
            .label("0 / 1,000,000 turns · harvest data unavailable");
        frame.render_widget(harvest_gauge, chunks[1]);

        // ── Active sessions / worktrees ───────────────────────────────────────
        let session_lines: Vec<Line> = vec![
            Line::from(vec![
                Span::styled(
                    "  (session/worktree data from daemon events not yet indexed)",
                    Style::default().fg(MUTED),
                ),
            ]),
        ];
        let sessions_para = Paragraph::new(session_lines)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(" SESSIONS · WORKTREES ", Style::default().fg(SLATE))));
        frame.render_widget(sessions_para, chunks[2]);
    }
}
