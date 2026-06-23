// src/screens/runs.rs — RUNS screen: research run list + inspector
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, ListState, Paragraph},
};

use crate::bridge::{DaemonState, ResearchRun, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd, ScreenId};

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

impl Screen for RunsScreen {
    fn id(&self) -> ScreenId { ScreenId::Runs }
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
                    Span::styled(format!(" {} ", &r.run_id[..r.run_id.len().min(8)]), Style::default().fg(SLATE_DIM)),
                    Span::styled(
                        r.target_url.as_deref().unwrap_or("(no url)").get(..50).unwrap_or("").to_string(),
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

        frame.render_stateful_widget(list, area, &mut self.list_state.clone());
    }
}
