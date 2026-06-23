// src/screens/queue.rs — QUEUE screen: daemon_work_queue inspector
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, ListState},
};

use crate::bridge::{DaemonState, WorkItem, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd, ScreenId};

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
    fn id(&self) -> ScreenId { ScreenId::Queue }
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
        let items: Vec<ListItem> = if state.queue.is_empty() {
            vec![ListItem::new(Line::from(vec![
                Span::styled("  queue is empty", Style::default().fg(MUTED)),
            ]))]
        } else {
            state.queue.iter().map(|item| {
                ListItem::new(Line::from(vec![
                    Span::styled(
                        format!(" {} ", &item.item_id[..item.item_id.len().min(8)]),
                        Style::default().fg(SLATE_DIM),
                    ),
                    Span::styled(item.agent_id.clone(), Style::default().fg(CREAM_DIM)),
                    Span::styled("  ", Style::default()),
                    Span::styled(item.kind.clone(), Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
                    Span::styled("  ", Style::default()),
                    Span::styled(
                        item.status.clone(),
                        Style::default().fg(status_color(&item.status)).add_modifier(Modifier::BOLD),
                    ),
                    Span::styled(
                        format!("  p={}", item.priority),
                        Style::default().fg(SLATE_DIM),
                    ),
                ]))
            }).collect()
        };

        let list = List::new(items)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(
                    format!(" WORK QUEUE ({}) ", state.queue.len()),
                    Style::default().fg(AMBER).add_modifier(Modifier::BOLD),
                )))
            .highlight_style(Style::default().fg(EMERALD).add_modifier(Modifier::BOLD))
            .highlight_symbol("▶ ");

        frame.render_stateful_widget(list, area, &mut self.list_state.clone());
    }
}
