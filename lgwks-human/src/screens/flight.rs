// src/screens/flight.rs — FLIGHT screen: cognition stream + affordance panel
// Primary screen. Observe daemon events, steer via affordances or free intent.
use crossterm::event::{KeyCode, KeyModifiers};
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, BorderType, Padding, List, ListItem, Paragraph, Wrap},
};
use tui_input::{Input, backend::crossterm::EventHandler};

use crate::{
    bridge::{DaemonState, DaemonEvent, palette::*},
    tui::Event,
};
use super::{Screen, ScreenCmd, ScreenId};

pub struct FlightScreen {
    scroll_offset: usize,   // lines scrolled from bottom
    input: Input,
    input_active: bool,
    status_msg: Option<String>,
    last_event_count: usize,
}

impl FlightScreen {
    pub fn new() -> Self {
        Self {
            scroll_offset: 0,
            input: Input::default(),
            input_active: true,
            status_msg: None,
            last_event_count: 0,
        }
    }

    fn render_stream(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let events: Vec<&DaemonEvent> = state.events.iter().collect();
        let total = events.len();

        // Build rendered lines (newest at bottom)
        let mut items: Vec<ListItem> = events
            .iter()
            .rev()
            .skip(self.scroll_offset)
            .take(area.height as usize)
            .rev()
            .map(|e| render_event_row(e))
            .collect();

        if items.is_empty() {
            items.push(ListItem::new(Line::from(vec![
                Span::styled("  no events yet — is the daemon running?", Style::default().fg(MUTED)),
            ])));
        }

        let list = List::new(items)
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_type(BorderType::Rounded)
                    .border_style(Style::default().fg(SLATE_DIM))
                    .padding(Padding::symmetric(2, 1))
                    .title(Span::styled(
                        format!(" COGNITION STREAM ({} events) ", total),
                        Style::default().fg(EMERALD).add_modifier(Modifier::BOLD),
                    )),
            );
        frame.render_widget(list, area);
    }

    fn render_affordance_panel(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(3),    // affordances list
                Constraint::Length(3), // input box
            ])
            .split(area);

        // Affordances
        let affordance_items: Vec<ListItem> = if state.packet.next_steps.is_empty() {
            vec![ListItem::new(Line::from(vec![
                Span::styled("  awaiting context packet…", Style::default().fg(MUTED)),
            ]))]
        } else {
            state
                .packet
                .next_steps
                .iter()
                .enumerate()
                .map(|(i, step)| {
                    let risk_color = match step.risk.as_deref() {
                        Some("high")   => RED_ERR,
                        Some("medium") => AMBER,
                        _              => EMERALD_DIM,
                    };
                    ListItem::new(Line::from(vec![
                        Span::styled(format!(" [{}] ", i + 1), Style::default().fg(SLATE)),
                        Span::styled(step.kind.clone(), Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
                        Span::styled("  ", Style::default()),
                        Span::styled(step.summary.clone(), Style::default().fg(CREAM_DIM)),
                        Span::styled(
                            step.risk.as_deref().map(|r| format!("  ·{}", r)).unwrap_or_default(),
                            Style::default().fg(risk_color),
                        ),
                    ]))
                })
                .collect()
        };

        let task_title = state
            .packet
            .active_task
            .as_deref()
            .map(|t| format!(" NEXT MOVES · active: {} ", t))
            .unwrap_or_else(|| " NEXT MOVES ".to_string());

        let affordance_list = List::new(affordance_items).block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(SLATE_DIM))
                .padding(Padding::symmetric(2, 1))
                .title(Span::styled(task_title, Style::default().fg(AMBER))),
        );
        frame.render_widget(affordance_list, chunks[0]);

        // Input box
        let input_val = self.input.value();
        let hint = if input_val.is_empty() {
            if self.status_msg.is_some() {
                self.status_msg.as_deref().unwrap_or("")
            } else {
                "type intent or [1-9] affordance · enter to send · ↑↓ scroll stream"
            }
        } else {
            input_val
        };

        let border_color = if self.input_active { EMERALD } else { SLATE_DIM };
        let input_widget = Paragraph::new(Line::from(vec![
            Span::styled(" ❯ ", Style::default().fg(EMERALD)),
            Span::styled(hint, Style::default().fg(CREAM)),
        ]))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(border_color))
                .padding(Padding::horizontal(1)),
        )
        .wrap(Wrap { trim: false });
        frame.render_widget(input_widget, chunks[1]);
    }
}

impl Screen for FlightScreen {
    fn id(&self) -> ScreenId { ScreenId::Flight }

    fn on_daemon_tick(&mut self, state: &DaemonState) {
        // If new events arrived and we're pinned to bottom, stay there
        if self.scroll_offset == 0 {
            // already at bottom, nothing to do
        }
        self.last_event_count = state.events.len();
    }

    fn handle_event(&mut self, event: &Event, state: &DaemonState) -> ScreenCmd {
        match event {
            Event::Key(key) => {
                // Scroll stream (vim-style)
                match key.code {
                    KeyCode::Char('j') | KeyCode::Down if !self.input_active => {
                        self.scroll_offset = self.scroll_offset.saturating_sub(1);
                        return ScreenCmd::None;
                    }
                    KeyCode::Char('k') | KeyCode::Up if !self.input_active => {
                        let max = state.events.len().saturating_sub(1);
                        self.scroll_offset = (self.scroll_offset + 1).min(max);
                        return ScreenCmd::None;
                    }
                    KeyCode::Char('g') if !self.input_active => {
                        self.scroll_offset = state.events.len().saturating_sub(1);
                        return ScreenCmd::None;
                    }
                    KeyCode::Char('G') if !self.input_active => {
                        self.scroll_offset = 0;
                        return ScreenCmd::None;
                    }
                    // Ctrl+D / Ctrl+U half-page scroll
                    KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) && !self.input_active => {
                        self.scroll_offset = self.scroll_offset.saturating_sub(10);
                        return ScreenCmd::None;
                    }
                    KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) && !self.input_active => {
                        let max = state.events.len().saturating_sub(1);
                        self.scroll_offset = (self.scroll_offset + 10).min(max);
                        return ScreenCmd::None;
                    }
                    // Tab toggles focus between stream-scroll and input
                    KeyCode::Tab => {
                        self.input_active = !self.input_active;
                        return ScreenCmd::None;
                    }
                    // Number keys 1-9 activate affordances
                    KeyCode::Char(c @ '1'..='9') if self.input_active => {
                        let idx = (c as usize) - ('1' as usize);
                        if let Some(step) = state.packet.next_steps.get(idx) {
                            let payload = step.args.clone().unwrap_or(serde_json::Value::Null);
                            
                            let is_high_risk = step.risk.as_deref() == Some("high");
                            let inject_cmd = ScreenCmd::InjectIntent {
                                kind:    step.kind.clone(),
                                scope:   "human_affordance".to_string(),
                                payload,
                            };

                            if is_high_risk {
                                return ScreenCmd::Confirm {
                                    prompt: format!("Execute high-risk affordance: {}?", step.kind),
                                    on_confirm: Box::new(inject_cmd),
                                };
                            } else {
                                self.status_msg = Some(format!("→ {}", step.kind));
                                return inject_cmd;
                            }
                        }
                        return ScreenCmd::None;
                    }
                    // Enter submits free-text intent
                    KeyCode::Enter if self.input_active => {
                        let text = self.input.value().trim().to_string();
                        if text.is_empty() { return ScreenCmd::None; }
                        self.input = Input::default();
                        self.status_msg = Some(format!("→ intent queued: {}", &text[..text.len().min(40)]));
                        return ScreenCmd::InjectIntent {
                            kind:    "human_message".to_string(),
                            scope:   "human_intent".to_string(),
                            payload: serde_json::json!({ "message": text }),
                        };
                    }
                    // Esc clears input
                    KeyCode::Esc => {
                        self.input = Input::default();
                        self.status_msg = None;
                        return ScreenCmd::None;
                    }
                    _ => {
                        if self.input_active {
                            self.input.handle_event(&crossterm::event::Event::Key(*key));
                        }
                    }
                }
            }
            _ => {}
        }
        ScreenCmd::None
    }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(0),    // cognition stream — takes remaining space
                Constraint::Length(12), // affordance panel + input
            ])
            .split(area);

        self.render_stream(frame, chunks[0], state);
        self.render_affordance_panel(frame, chunks[1], state);
    }
}

/// Render one daemon event as a list row.
/// Format: [HH:MM:SS] agent_id · kind · payload_preview
fn render_event_row(e: &DaemonEvent) -> ListItem<'static> {
    let ts = e.ts.as_deref().unwrap_or("").get(11..19).unwrap_or("").to_string();
    let agent = e.agent_id.as_deref().unwrap_or("?").to_string();
    let kind = e.kind.as_deref().unwrap_or("?").to_string();
    let lane = e.lane.as_deref().unwrap_or("").to_string();
    let preview = e.payload.as_ref().map(|p| {
        let s = p.to_string();
        if s.len() > 60 { format!("{}…", &s[..60]) } else { s }
    }).unwrap_or_default();

    let lane_color = match lane.as_str() {
        "control"   => AMBER,
        "ingress"   => EMERALD,
        "telemetry" => SLATE,
        "human"     => CREAM,
        _           => MUTED,
    };

    ListItem::new(Line::from(vec![
        Span::styled(format!(" {} ", ts), Style::default().fg(SLATE_DIM)),
        Span::styled(format!("{} ", agent), Style::default().fg(CREAM_DIM)),
        Span::styled("· ", Style::default().fg(SLATE_DIM)),
        Span::styled(kind, Style::default().fg(lane_color).add_modifier(Modifier::BOLD)),
        Span::styled("  ", Style::default()),
        Span::styled(preview, Style::default().fg(MUTED)),
    ]))
}
