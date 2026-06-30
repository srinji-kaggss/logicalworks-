// src/screens/chat.rs — CHAT/STEER screen: cowork conversation log with compose+send
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Paragraph, Wrap},
};
use tui_input::{Input, backend::crossterm::EventHandler};

use crate::bridge::{DaemonEvent, DaemonState, palette::*};
use crate::tui::Event;
use super::{Screen, ScreenCmd};

/// Kinds surfaced in the CHAT pane — cowork conversation events.
const CHAT_KINDS: &[&str] = &["human_message", "agent_message", "transcript_turn"];

pub struct ChatScreen {
    scroll_offset: usize,
    auto_scroll: bool,
    input: Input,
    input_active: bool,
}

impl ChatScreen {
    pub fn new() -> Self {
        Self {
            scroll_offset: 0,
            auto_scroll: true,
            input: Input::default(),
            input_active: false,
        }
    }

    /// Collect chat events in chronological order (newest at bottom).
    fn chat_events<'a>(&self, state: &'a DaemonState) -> Vec<&'a DaemonEvent> {
        state.events.iter()
            .filter(|e| e.kind.as_deref().map(|k| CHAT_KINDS.contains(&k)).unwrap_or(false))
            .collect()
    }
}

/// Render one daemon event as a chat row. Mirrors the badge+lane pattern from
/// flight.rs and runs.rs — same style, same colour rules, same char-safety.
fn chat_event_row(e: &DaemonEvent) -> ListItem<'static> {
    let ts = e.ts.as_deref().unwrap_or("").get(11..19).unwrap_or("").to_string();
    let kind = e.kind.as_deref().unwrap_or("?").to_string();
    let lane = e.lane.as_deref().unwrap_or("").to_string();
    let preview = e.payload.as_ref()
        .map(|p| crate::util::head_ellipsis(&p.to_string(), 80))
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

impl Screen for ChatScreen {
    fn on_daemon_tick(&mut self, state: &DaemonState) {
        if self.auto_scroll {
            let events = self.chat_events(state);
            self.scroll_offset = events.len().saturating_sub(1);
        }
    }

    fn handle_event(&mut self, event: &Event, state: &DaemonState) -> ScreenCmd {
        let events = self.chat_events(state);
        let max_idx = events.len().saturating_sub(1);

        match event {
            Event::Key(key) => {
                if self.input_active {
                    match key.code {
                        KeyCode::Enter => {
                            let text = self.input.value().trim().to_string();
                            if text.is_empty() {
                                return ScreenCmd::None;
                            }
                            self.input = Input::default();
                            return ScreenCmd::EmitEvent {
                                kind: "human_message".to_string(),
                                payload: serde_json::json!({ "message": text }),
                            };
                        }
                        KeyCode::Esc => {
                            self.input_active = false;
                            return ScreenCmd::None;
                        }
                        _ => {
                            self.input.handle_event(&crossterm::event::Event::Key(*key));
                            return ScreenCmd::None;
                        }
                    }
                }

                match key.code {
                    KeyCode::Char('i') | KeyCode::Char('/') => {
                        self.input_active = true;
                        return ScreenCmd::None;
                    }
                    KeyCode::Char('j') | KeyCode::Down => {
                        self.auto_scroll = false;
                        self.scroll_offset = (self.scroll_offset + 1).min(max_idx);
                    }
                    KeyCode::Char('k') | KeyCode::Up => {
                        self.auto_scroll = false;
                        self.scroll_offset = self.scroll_offset.saturating_sub(1);
                    }
                    KeyCode::Char('g') => {
                        self.auto_scroll = false;
                        self.scroll_offset = 0;
                    }
                    KeyCode::Char('G') => {
                        self.auto_scroll = true;
                        self.scroll_offset = max_idx;
                    }
                    KeyCode::Esc => {
                        self.auto_scroll = true;
                        self.scroll_offset = max_idx;
                    }
                    _ => {}
                }
            }
            // Bracketed paste: only meaningful while composing — drop the clipboard
            // text straight into the input so multi-line/long pastes work like an IDE.
            Event::Paste(s) if self.input_active => {
                self.input.handle_event(&crossterm::event::Event::Paste(s.clone()));
            }
            Event::Mouse(m) if !self.input_active => {
                match m.kind {
                    crossterm::event::MouseEventKind::ScrollDown => {
                        self.auto_scroll = false;
                        self.scroll_offset = (self.scroll_offset + 1).min(max_idx);
                    }
                    crossterm::event::MouseEventKind::ScrollUp => {
                        self.auto_scroll = false;
                        self.scroll_offset = self.scroll_offset.saturating_sub(1);
                    }
                    _ => {}
                }
            }
            _ => {}
        }
        ScreenCmd::None
    }

    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState) {
        let events = self.chat_events(state);
        let total = events.len();

        // ── Split area: scrollback on top, input box at bottom ────────────────
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(0), Constraint::Length(3)])
            .split(area);
        let scroll_area = chunks[0];
        let input_area = chunks[1];

        // ── Build chat items ──────────────────────────────────────────────────
        let items: Vec<ListItem> = if events.is_empty() {
            vec![ListItem::new(Line::from(vec![
                Span::styled(
                    "  awaiting human_message / agent_message / transcript_turn …",
                    Style::default().fg(MUTED),
                ),
            ]))]
        } else {
            events.iter().map(|e| chat_event_row(e)).collect()
        };

        // ── Determine visible range based on scroll_offset ────────────────────
        // We want to show a window ending at scroll_offset (newest at bottom).
        let visible_count = (scroll_area.height as usize).saturating_sub(2); // account for borders
        let start = if total > visible_count {
            if self.auto_scroll || self.scroll_offset >= total.saturating_sub(1) {
                total.saturating_sub(visible_count)
            } else if self.scroll_offset < visible_count {
                0
            } else {
                self.scroll_offset.saturating_sub(visible_count).saturating_add(1)
            }
        } else {
            0
        };

        let visible_items: Vec<ListItem> = if start < items.len() {
            items[start..].to_vec()
        } else {
            vec![]
        };

        // ── Title with scroll indicator ───────────────────────────────────────
        let title = if total == 0 {
            " CHAT/STEER · Director<->Opus<->Codex (post via Claude Code / cowork.sh) ".to_string()
        } else if self.auto_scroll {
            format!(
                " CHAT/STEER · Director<->Opus<->Codex (post via Claude Code / cowork.sh) — {} events (auto-scroll) ",
                total
            )
        } else {
            format!(
                " CHAT/STEER · Director<->Opus<->Codex (post via Claude Code / cowork.sh) — {} events (at {}) ",
                total,
                self.scroll_offset.saturating_add(1)
            )
        };

        let list = List::new(visible_items)
            .block(Block::default().borders(Borders::ALL)
                .border_style(Style::default().fg(SLATE_DIM))
                .title(Span::styled(title, Style::default().fg(EMERALD).add_modifier(Modifier::BOLD))))
            .highlight_style(Style::default().fg(AMBER).add_modifier(Modifier::BOLD));

        frame.render_widget(list, scroll_area);

        // ── Input / compose box ───────────────────────────────────────────────
        let border_color = if self.input_active { EMERALD } else { SLATE_DIM };
        let input_text = self.input.value();
        let input_paragraph = if input_text.is_empty() {
            Paragraph::new(Line::from(vec![
                Span::styled("press i to type · Enter to send", Style::default().fg(MUTED)),
            ]))
        } else {
            Paragraph::new(Line::from(vec![
                Span::styled(input_text.to_string(), Style::default().fg(CREAM)),
            ]))
        };

        let input_block = Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(border_color))
            .title(Span::styled(" message ", Style::default().fg(border_color)));

        frame.render_widget(input_paragraph.wrap(Wrap { trim: false }).block(input_block), input_area);
    }
}
