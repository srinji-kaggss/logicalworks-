// src/screens/runs.rs — RUNS screen: research run list + STREAM event tail
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, ListState, Paragraph},
};

use crate::bridge::{DaemonEvent, DaemonState, ResearchRun, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd};

/// Kinds surfaced in the STREAM pane — transcript/output signal only.
const STREAM_KINDS: &[&str] = &["model_output", "terminal_output", "transcript_turn"];

pub struct RunsScreen {
    list_state: ListState,
    detail_mode: bool,
}

impl RunsScreen {
    pub fn new() -> Self {
        let mut s = Self { list_state: ListState::default(), detail_mode: false };
        s.list_state.select(Some(0));
        s
    }

    fn selected_run<'a>(&self, state: &'a DaemonState) -> Option<&'a ResearchRun> {
        self.list_state.selected().and_then(|i| state.runs.get(i))
    }
}

/// Render one daemon event as a stream row. Mirrors the badge+lane pattern from
/// flight.rs render_event_row — same style, same colour rules, same char-safety.
fn stream_event_row(e: &DaemonEvent) -> ListItem<'static> {
    let ts = e.ts.as_deref().unwrap_or("").get(11..19).unwrap_or("").to_string();
    let kind = e.kind.as_deref().unwrap_or("?").to_string();
    let lane = e.lane.as_deref().unwrap_or("").to_string();
    let preview = e.payload.as_ref()
        .map(|p| crate::util::head_ellipsis(&p.to_string(), 55))
        .unwrap_or_default();

    let (badge_text, badge_color) = if e.agent_id.as_deref() == Some("opus") {
        ("[opus]".to_string(), EMERALD)
    } else if e.agent_id.as_deref() == Some("codex") {
        ("[codex]".to_string(), EMERALD)
    } else if e.actor.as_deref() == Some("human") {
        ("[human]".to_string(), SLATE)
    } else if matches!(e.actor.as_deref(), Some("system") | Some("daemon")) {
        ("[sys]".to_string(), SLATE)
    } else if let Some(actor) = e.actor.as_deref() {
        (format!("[{actor}]"), SLATE)
    } else if let Some(agent) = e.agent_id.as_deref() {
        (format!("[{agent}]"), EMERALD)
    } else {
        ("[?]".to_string(), MUTED)
    };

    let lane_color = match lane.as_str() {
        "control"   => AMBER,
        "ingress"   => EMERALD,
        "telemetry" => SLATE,
        "human"     => CREAM,
        _           => MUTED,
    };

    let shared = e.scope.as_deref() == Some("shared_referee");

    let mut spans = vec![
        Span::styled(format!(" {} ", ts), Style::default().fg(SLATE_DIM)),
    ];
    if shared {
        spans.push(Span::styled("★ ", Style::default().fg(AMBER)));
    }
    spans.extend([
        Span::styled(format!("{badge_text} "), Style::default().fg(badge_color)),
        Span::styled("· ", Style::default().fg(SLATE_DIM)),
        Span::styled(kind, Style::default().fg(lane_color).add_modifier(Modifier::BOLD)),
        Span::styled("  ", Style::default()),
        Span::styled(preview, Style::default().fg(MUTED)),
    ]);

    ListItem::new(Line::from(spans))
}

impl Screen for RunsScreen {
    fn on_daemon_tick(&mut self, _state: &DaemonState) {}

    fn handle_event(&mut self, event: &Event, state: &DaemonState) -> ScreenCmd {
        match event {
            Event::Key(key) => {
                match key.code {
                    KeyCode::Char('j') | KeyCode::Down => {
                        let max = state.runs.len().saturating_sub(1);
                        let next = self.list_state.selected().map(|i| (i + 1).min(max)).unwrap_or(0);
                        self.list_state.select(Some(next));
                    }
                    KeyCode::Char('k') | KeyCode::Up => {
                        let prev = self.list_state.selected().map(|i| i.saturating_sub(1)).unwrap_or(0);
                        self.list_state.select(Some(prev));
                    }
                    KeyCode::Enter => { self.detail_mode = !self.detail_mode; }
                    KeyCode::Esc   => { self.detail_mode = false; }
                    _ => {}
                }
            }
            Event::Mouse(m) => {
                match m.kind {
                    crossterm::event::MouseEventKind::ScrollDown => {
                        let max = state.runs.len().saturating_sub(1);
                        let next = self.list_state.selected().map(|i| (i + 1).min(max)).unwrap_or(0);
                        self.list_state.select(Some(next));
                    }
                    crossterm::event::MouseEventKind::ScrollUp => {
                        let prev = self.list_state.selected().map(|i| i.saturating_sub(1)).unwrap_or(0);
                        self.list_state.select(Some(prev));
                    }
                    _ => {}
                }
            }
            _ => {}
        }
        ScreenCmd::None
    }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        if self.detail_mode {
            if let Some(run) = self.selected_run(state) {
                let detail = format!(
                    "Run ID:  {}\nURL:     {}\nStatus:  {}\nCreated: {}\nDone:    {}",
                    run.run_id,
                    run.target_url.as_deref().unwrap_or("—"),
                    run.status,
                    run.created_at.as_deref().unwrap_or("—"),
                    run.done_at.as_deref().unwrap_or("—"),
                );
                let para = Paragraph::new(detail)
                    .block(Block::default().borders(Borders::ALL)
                        .border_style(Style::default().fg(SLATE_DIM))
                        .title(Span::styled(" RUN DETAIL ", Style::default().fg(AMBER))));
                frame.render_widget(para, area);
                return;
            }
        }

        // ── Split: left = run list, right = STREAM event tail ────────────────
        let panes = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(45),
                Constraint::Percentage(55),
            ])
            .split(area);

        // ── Left: research run list ───────────────────────────────────────────
        let items: Vec<ListItem> = if state.runs.is_empty() {
            vec![ListItem::new(Line::from(vec![
                Span::styled("  no runs found", Style::default().fg(MUTED)),
            ]))]
        } else {
            state.runs.iter().map(|r| {
                let status_color = match r.status.as_str() {
                    "done"    => EMERALD_DIM,
                    "running" | "active" => EMERALD,
                    "error"   => RED_ERR,
                    _         => AMBER,
                };
                ListItem::new(Line::from(vec![
                    Span::styled(format!(" {} ", crate::util::head(&r.run_id, 8)), Style::default().fg(SLATE_DIM)),
                    Span::styled(
                        format!("{} ", crate::util::head(r.target_url.as_deref().unwrap_or("(no url)"), 32)),
                        Style::default().fg(CREAM_DIM),
                    ),
                    Span::styled("  ", Style::default()),
                    Span::styled(r.status.clone(), Style::default().fg(status_color).add_modifier(Modifier::BOLD)),
                ]))
            }).collect()
        };

        let list = List::new(items)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(
                    format!(" RESEARCH RUNS ({}) ", state.runs.len()),
                    Style::default().fg(EMERALD).add_modifier(Modifier::BOLD),
                )))
            .highlight_style(Style::default().fg(AMBER).add_modifier(Modifier::BOLD))
            .highlight_symbol("▶ ");

        frame.render_stateful_widget(list, panes[0], &mut self.list_state.clone());

        // ── Right: STREAM tail — last 50 events of interest, newest at bottom ─
        let stream_events: Vec<&DaemonEvent> = state.events.iter()
            .filter(|e| {
                e.kind.as_deref().map(|k| STREAM_KINDS.contains(&k)).unwrap_or(false)
            })
            .rev()
            .take(50)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()  // restore chronological order (newest at bottom)
            .collect();

        let stream_items: Vec<ListItem> = if stream_events.is_empty() {
            vec![ListItem::new(Line::from(vec![
                Span::styled(
                    "  awaiting model_output / terminal_output / transcript_turn …",
                    Style::default().fg(MUTED),
                ),
            ]))]
        } else {
            stream_events.iter().map(|e| stream_event_row(e)).collect()
        };

        let stream_list = List::new(stream_items)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(
                    format!(" STREAM ─ last {} ", stream_events.len()),
                    Style::default().fg(SLATE).add_modifier(Modifier::BOLD),
                )));

        frame.render_widget(stream_list, panes[1]);
    }
}
