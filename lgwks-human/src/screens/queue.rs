// src/screens/queue.rs — QUEUE screen: daemon_work_queue inspector
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, ListState},
};

use crate::bridge::{DaemonState, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd};

pub struct QueueScreen {
    list_state: ListState,
}

impl QueueScreen {
    pub fn new() -> Self {
        let mut s = Self { list_state: ListState::default() };
        s.list_state.select(Some(0));
        s
    }
}

fn status_color(status: &str) -> ratatui::style::Color {
    match status {
        "pending"    => AMBER,
        "active"     => EMERALD,
        "done"       => EMERALD_DIM,
        "dead_letter"| "error" => RED_ERR,
        _            => MUTED,
    }
}

impl Screen for QueueScreen {
    fn on_daemon_tick(&mut self, _state: &DaemonState) {}

    fn handle_event(&mut self, event: &Event, state: &DaemonState) -> ScreenCmd {
        match event {
            Event::Key(key) => {
                match key.code {
                    KeyCode::Char('j') | KeyCode::Down => {
                        let max = state.queue.len().saturating_sub(1);
                        let n = self.list_state.selected().map(|i| (i+1).min(max)).unwrap_or(0);
                        self.list_state.select(Some(n));
                    }
                    KeyCode::Char('k') | KeyCode::Up => {
                        let p = self.list_state.selected().map(|i| i.saturating_sub(1)).unwrap_or(0);
                        self.list_state.select(Some(p));
                    }
                    _ => {}
                }
            }
            Event::Mouse(m) => {
                match m.kind {
                    crossterm::event::MouseEventKind::ScrollDown => {
                        let max = state.queue.len().saturating_sub(1);
                        let n = self.list_state.selected().map(|i| (i+1).min(max)).unwrap_or(0);
                        self.list_state.select(Some(n));
                    }
                    crossterm::event::MouseEventKind::ScrollUp => {
                        let p = self.list_state.selected().map(|i| i.saturating_sub(1)).unwrap_or(0);
                        self.list_state.select(Some(p));
                    }
                    _ => {}
                }
            }
            _ => {}
        }
        ScreenCmd::None
    }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
            .split(area);

        // Left: work queue
        let items: Vec<ListItem> = state.queue.iter().map(|wi| {
            let color = status_color(&wi.status);
            let status_sym = match wi.status.as_str() {
                "pending" => "○",
                "active" => "●",
                "done" => "✓",
                "dead_letter" | "error" => "✗",
                _ => "·",
            };
            let mut line = vec![
                Span::styled(format!("{} ", status_sym), Style::default().fg(color)),
                Span::styled(crate::util::head(&wi.kind, 14), Style::default().fg(CREAM)),
                Span::raw(" "),
                Span::styled(crate::util::head(&wi.agent_id, 8), Style::default().fg(SLATE_DIM)),
                Span::raw(" "),
                Span::styled(format!("p{}", wi.priority), Style::default().fg(MUTED)),
            ];
            if let Some(ref err) = wi.error {
                line.push(Span::raw(" "));
                line.push(Span::styled(crate::util::head_ellipsis(err, 30), Style::default().fg(RED_ERR)));
            }
            ListItem::new(Line::from(line))
        }).collect();

        let queue_list = List::new(items)
            .block(Block::default()
                .borders(Borders::ALL)
                .title(Span::styled(
                    format!(" QUEUE ─ WORK ITEMS ({}) ", state.queue.len()),
                    Style::default().fg(AMBER).add_modifier(Modifier::BOLD),
                )))
            .highlight_style(Style::default().add_modifier(Modifier::REVERSED));

        let mut ls = self.list_state;
        frame.render_stateful_widget(queue_list, chunks[0], &mut ls);

        // Right: KV-CACHE uncertainty slots
        let uncertainties: Vec<_> = state.events.iter().rev()
            .filter(|ev| {
                ev.kind.as_deref() == Some("transcript_turn") &&
                ev.payload.as_ref().and_then(|p| p.as_object()).and_then(|o| o.get("type")).and_then(|v| v.as_str()) == Some("uncertainty")
            })
            .take(20)
            .collect();

        let count = uncertainties.len();
        let kv_items: Vec<ListItem> = if uncertainties.is_empty() {
            vec![ListItem::new(Line::from(Span::styled(
                "  no open questions",
                Style::default().fg(MUTED),
            )))]
        } else {
            uncertainties.iter().map(|ev| {
                let question = ev.payload.as_ref()
                    .and_then(|p| p.as_object())
                    .and_then(|o| o.get("question"))
                    .and_then(|v| v.as_str())
                    .unwrap_or("?");
                let mut line = vec![
                    Span::styled("❓ ", Style::default().fg(AMBER).add_modifier(Modifier::BOLD)),
                    Span::styled(question.to_string(), Style::default().fg(CREAM)),
                ];
                if let Some(opts) = ev.payload.as_ref()
                    .and_then(|p| p.as_object())
                    .and_then(|o| o.get("options"))
                    .and_then(|v| v.as_array())
                {
                    let opt_strs: Vec<String> = opts.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect();
                    if !opt_strs.is_empty() {
                        line.push(Span::styled(
                            format!(" [{}]", opt_strs.join(" | ")),
                            Style::default().fg(MUTED),
                        ));
                    }
                }
                ListItem::new(Line::from(line))
            }).collect()
        };

        let kv_list = List::new(kv_items)
            .block(Block::default()
                .borders(Borders::ALL)
                .title(Span::styled(
                    format!(" KV-CACHE ─ OPEN QUESTIONS ({}) ", count),
                    Style::default().fg(AMBER).add_modifier(Modifier::BOLD),
                )));

        frame.render_widget(kv_list, chunks[1]);
    }
}
