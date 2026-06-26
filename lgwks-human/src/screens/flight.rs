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
    bridge::{DaemonState, DaemonEvent, NextStep, palette::*},
    tui::Event,
};
use super::{Screen, ScreenCmd, ScreenId};

/// Does this affordance require a human confirm before it fires?
///
/// Keys off the daemon's PULSE `approval` class, NOT `risk`: an irreversible
/// medium-risk op (worktree_close, workflow) carries approval="once" and MUST
/// confirm even though its risk is "medium". Fail-closed: any value other than
/// the explicit "none" — including a missing/unknown class — requires confirm.
fn needs_confirm(approval: Option<&str>) -> bool {
    approval != Some("none")
}

/// Build the command for a picked affordance: enqueue the daemon WORK item, wrapped
/// in a confirm gate when the approval class demands it. Single source of truth for
/// both the keyboard and mouse affordance paths (they previously duplicated this).
fn affordance_cmd(step: &NextStep) -> ScreenCmd {
    let payload = step.args.clone().unwrap_or(serde_json::Value::Null);
    let work = ScreenCmd::EnqueueWork { kind: step.kind.clone(), payload };
    if needs_confirm(step.approval.as_deref()) {
        let cls = step.approval.as_deref().unwrap_or("unknown");
        ScreenCmd::Confirm {
            prompt: format!("Confirm {} (approval: {cls})?", step.kind),
            on_confirm: Box::new(work),
        }
    } else {
        work
    }
}

pub struct FlightScreen {
    scroll_offset: usize,
    input: Input,
    input_active: bool,
    voice_active: bool,
    status_msg: Option<String>,
    last_event_count: usize,
    last_area: std::cell::Cell<Rect>,
}

impl FlightScreen {
    pub fn new() -> Self {
        Self {
            scroll_offset: 0,
            input: Input::default(),
            input_active: true,
            voice_active: false,
            status_msg: None,
            last_event_count: 0,
            last_area: std::cell::Cell::new(Rect::default()),
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
                Constraint::Length(3), // telemetry sparkline
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
                    let mut spans = vec![
                        Span::styled(format!(" [{}] ", i + 1), Style::default().fg(SLATE)),
                        Span::styled(step.kind.clone(), Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
                        Span::styled("  ", Style::default()),
                        Span::styled(step.summary.clone(), Style::default().fg(CREAM_DIM)),
                        Span::styled(
                            step.risk.as_deref().map(|r| format!("  ·{}", r)).unwrap_or_default(),
                            Style::default().fg(risk_color),
                        ),
                    ];

                    if let Some(prov) = &step.provenance {
                        if let Some(reason) = prov.get("reason").and_then(|v| v.as_str()) {
                            spans.push(Span::styled("  └─ ", Style::default().fg(MUTED)));
                            spans.push(Span::styled(reason.to_string(), Style::default().fg(SLATE).add_modifier(Modifier::ITALIC)));
                        }
                    }

                    ListItem::new(Line::from(spans))
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

        // Input box (Smart Search & Tool Chainer)
        let input_val = self.input.value();
        let hint = if input_val.is_empty() {
            if self.voice_active {
                "🔴 Listening... (wispr active) · press [Ctrl+V] to stop"
            } else {
                "search context · chain tools · type intent · [Ctrl+V] voice (wispr)"
            }
        } else {
            ""
        };
        
        let input_span = if input_val.is_empty() {
            Span::styled("", Style::default())
        } else {
            Span::styled(input_val, Style::default().fg(CREAM))
        };
        
        let hint_style = if input_val.is_empty() {
            if self.voice_active { Style::default().fg(ratatui::style::Color::Red) } else { Style::default().fg(MUTED) }
        } else {
            Style::default()
        };

        let input_border_style = if self.voice_active {
            Style::default().fg(ratatui::style::Color::Red)
        } else if self.input_active { 
            Style::default().fg(EMERALD) 
        } else { 
            Style::default().fg(SLATE_DIM) 
        };

        let icon = if self.voice_active { " 🎙  " } else { " 🔍 " };
        let icon_style = if self.voice_active { Style::default().fg(ratatui::style::Color::Red) } else { Style::default().fg(if self.input_active { EMERALD } else { MUTED }) };

        let input_widget = Paragraph::new(Line::from(vec![
            Span::styled(icon, icon_style),
            input_span,
            Span::styled(hint, hint_style),
        ]))
        .block(
            Block::default()
                .title(Span::styled(" OMNI-INPUT (SEARCH / TOOLS / INTENT) ", Style::default().fg(MUTED)))
                .borders(Borders::ALL)
                .border_type(BorderType::Rounded)
                .border_style(input_border_style)
                .padding(Padding::symmetric(1, 0)),
        );
        frame.render_widget(input_widget, chunks[2]);

        let telemetry_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(50),
                Constraint::Percentage(50),
            ])
            .split(chunks[1]);

        // Telemetry Sparkline
        let entropy_data = &state.packet.entropy_history;
        // simulated ⇒ honest DEMO label; the real daemon path never fabricates these.
        let title = if state.packet.simulated {
            format!(" TELEMETRY · DEMO DATA (simulated) · TPS {:.1} ", state.packet.tps)
        } else {
            format!(" TELEMETRY · TPS: {:.1} · ENTROPY ", state.packet.tps)
        };
        let sparkline = ratatui::widgets::Sparkline::default()
            .block(
                Block::default()
                    .title(Span::styled(title, Style::default().fg(MUTED)))
                    .borders(Borders::ALL)
                    .border_type(BorderType::Rounded)
                    .border_style(Style::default().fg(SLATE_DIM)),
            )
            .data(entropy_data)
            .style(Style::default().fg(EMERALD));
        frame.render_widget(sparkline, telemetry_chunks[0]);

        // Steering Dials
        let dials = &state.packet.steering_dials;
        let mut dial_spans = vec![];
        for (i, (name, val)) in dials.iter().enumerate() {
            let width = 10;
            let filled = (val * width as f32).round() as usize;
            let empty = width - filled;
            let bar = format!("{}{}", "■".repeat(filled), "□".repeat(empty));
            let color = match i % 3 {
                0 => EMERALD,
                1 => AMBER,
                _ => ratatui::style::Color::Rgb(150, 100, 255), // Purple accent
            };
            dial_spans.push(Span::styled(format!(" {} ", name), Style::default().fg(CREAM_DIM)));
            dial_spans.push(Span::styled(bar, Style::default().fg(color)));
            if i < dials.len() - 1 {
                dial_spans.push(Span::raw(" │ "));
            }
        }
        
        let dials_title = if state.packet.simulated { " STEERING DIALS · DEMO DATA " } else { " STEERING DIALS " };
        let dials_widget = Paragraph::new(Line::from(dial_spans))
            .block(
                Block::default()
                    .title(Span::styled(dials_title, Style::default().fg(MUTED)))
                    .borders(Borders::ALL)
                    .border_type(BorderType::Rounded)
                    .border_style(Style::default().fg(SLATE_DIM)),
            );
        frame.render_widget(dials_widget, telemetry_chunks[1]);
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
                    // Enter input mode
                    KeyCode::Char('i') | KeyCode::Char('/') if !self.input_active => {
                        self.input_active = true;
                        return ScreenCmd::None;
                    }
                    // Voice activation toggle (Ctrl+V)
                    KeyCode::Char('v') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                        self.voice_active = !self.voice_active;
                        if self.voice_active {
                            self.input_active = true;
                        }
                        return ScreenCmd::None;
                    }
                    // Alt+1-9 or 1-9 in normal mode activates affordances
                    KeyCode::Char(c @ '1'..='9') => {
                        let is_alt = key.modifiers.contains(crossterm::event::KeyModifiers::ALT);
                        if !self.input_active || is_alt {
                            let idx = (c as usize) - ('1' as usize);
                            if let Some(step) = state.packet.next_steps.get(idx) {
                                return affordance_cmd(step);
                            }
                            return ScreenCmd::None;
                        }
                    }
                    // Enter submits free-text intent
                    KeyCode::Enter if self.input_active => {
                        let text = self.input.value().trim().to_string();
                        if text.is_empty() { return ScreenCmd::None; }
                        self.input = Input::default();
                        return ScreenCmd::EmitEvent {
                            kind:    "human_message".to_string(),
                            payload: serde_json::json!({ "message": text }),
                        };
                    }
                    // Esc clears input or exits input mode
                    KeyCode::Esc => {
                        if self.input_active {
                            self.input_active = false;
                        } else {
                            self.input = tui_input::Input::default();
                            self.status_msg = None;
                        }
                        return ScreenCmd::None;
                    }
                    _ => {
                        if self.input_active {
                            self.input.handle_event(&crossterm::event::Event::Key(*key));
                        }
                    }
                }
            }
            Event::Mouse(m) => {
                match m.kind {
                    crossterm::event::MouseEventKind::ScrollDown if !self.input_active => {
                        self.scroll_offset = self.scroll_offset.saturating_sub(1);
                    }
                    crossterm::event::MouseEventKind::ScrollUp if !self.input_active => {
                        let max = state.events.len().saturating_sub(1);
                        self.scroll_offset = (self.scroll_offset + 1).min(max);
                    }
                    crossterm::event::MouseEventKind::Down(crossterm::event::MouseButton::Left) => {
                        let area = self.last_area.get();
                        let bottom_panel_y = area.height.saturating_sub(15);
                        let is_in_affordances = m.column < area.width * 60 / 100 
                                             && m.row >= bottom_panel_y;
                        if is_in_affordances {
                            // Border + Y padding is 2
                            let list_start_y = bottom_panel_y + 2;
                            if m.row >= list_start_y {
                                let idx = (m.row - list_start_y) as usize;
                                if let Some(step) = state.packet.next_steps.get(idx) {
                                    return affordance_cmd(step);
                                }
                            }
                        } else {
                            // Clicked somewhere else (like stream or input bar), focus input if bottom right
                            if m.row >= area.height.saturating_sub(3) && m.column >= area.width * 60 / 100 {
                                self.input_active = true;
                            } else {
                                self.input_active = false;
                            }
                        }
                    }
                    _ => {}
                }
            }
            _ => {}
        }
        ScreenCmd::None
    }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        self.last_area.set(area);
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Min(0),    // cognition stream — takes remaining space
                Constraint::Length(15), // affordance panel + sparkline + input
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
    // char-safe: a crafted multibyte payload must not panic the render thread.
    let preview = e.payload.as_ref()
        .map(|p| crate::util::head_ellipsis(&p.to_string(), 60))
        .unwrap_or_default();

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

#[cfg(test)]
mod tests {
    use super::*;

    fn step(kind: &str, risk: Option<&str>, approval: Option<&str>) -> NextStep {
        NextStep {
            kind: kind.into(),
            summary: String::new(),
            risk: risk.map(Into::into),
            approval: approval.map(Into::into),
            args: None,
            provenance: None,
        }
    }

    #[test]
    fn none_approval_skips_confirm() {
        assert!(!needs_confirm(Some("none")));
    }

    #[test]
    fn once_and_force_require_confirm() {
        assert!(needs_confirm(Some("once")));
        assert!(needs_confirm(Some("force")));
    }

    #[test]
    fn unknown_and_missing_fail_closed_to_confirm() {
        assert!(needs_confirm(None));
        assert!(needs_confirm(Some("")));
        assert!(needs_confirm(Some("garbage")));
    }

    #[test]
    fn irreversible_medium_risk_affordance_is_gated() {
        // worktree_close: risk="medium" (NOT high) but approval="once". The old gate
        // keyed on risk=="high" and let it fire un-confirmed; the new gate stops it.
        let s = step("worktree_close", Some("medium"), Some("once"));
        assert!(matches!(affordance_cmd(&s), ScreenCmd::Confirm { .. }));
    }

    #[test]
    fn workflow_force_affordance_is_gated() {
        let s = step("workflow", Some("medium"), Some("once"));
        assert!(matches!(affordance_cmd(&s), ScreenCmd::Confirm { .. }));
        let s2 = step("custom", Some("high"), Some("force"));
        assert!(matches!(affordance_cmd(&s2), ScreenCmd::Confirm { .. }));
    }

    #[test]
    fn low_risk_read_affordance_enqueues_directly() {
        let s = step("index_run", Some("low"), Some("none"));
        assert!(matches!(affordance_cmd(&s), ScreenCmd::EnqueueWork { .. }));
    }

    #[test]
    fn affordance_without_approval_class_fails_closed() {
        // A daemon that omits the approval field must still gate, never bypass.
        let s = step("worktree_close", Some("medium"), None);
        assert!(matches!(affordance_cmd(&s), ScreenCmd::Confirm { .. }));
    }
}
