// src/ui/help_overlay.rs — keymap reference overlay (the IDE "Keyboard Shortcuts" pane).
// Mirrors the confirm_overlay pattern: a modal toggled on top of the cockpit that lists
// every global keybinding plus the per-pane affordance model, so the surface is
// discoverable without leaving it. Dismissed by Esc / ? / F1 / Enter.
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect, Alignment},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, BorderType, Padding, Clear, Paragraph},
};
use crossterm::event::KeyCode;
use crate::tui::Event;
use crate::bridge::palette::*;

pub struct HelpOverlay {
    pub active: bool,
}

impl HelpOverlay {
    pub fn new() -> Self {
        Self { active: false }
    }

    pub fn toggle(&mut self) {
        self.active = !self.active;
    }

    /// Returns true if the event was consumed (overlay was open and handled it).
    pub fn handle_event(&mut self, event: &Event) -> bool {
        if !self.active { return false; }
        if let Event::Key(key) = event {
            match key.code {
                KeyCode::Esc | KeyCode::Enter | KeyCode::F(1) | KeyCode::Char('?') => {
                    self.active = false;
                }
                _ => {}
            }
        }
        // Eat every event while open so it never leaks to a screen's text input.
        true
    }

    pub fn render(&self, frame: &mut Frame, area: Rect) {
        if !self.active { return; }

        fn row(key: &'static str, desc: &'static str) -> Line<'static> {
            Line::from(vec![
                Span::styled(format!("  {key:<14}"), Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
                Span::styled(desc, Style::default().fg(CREAM)),
            ])
        }
        fn section(title: &'static str) -> Line<'static> {
            Line::from(Span::styled(title, Style::default().fg(AMBER).add_modifier(Modifier::BOLD)))
        }

        let lines = vec![
            section("GLOBAL"),
            row("Ctrl-P", "command palette — fuzzy find any action / screen"),
            row("F1  /  ?", "this keymap"),
            row("Tab / ⇧Tab", "next / previous pane"),
            row("Ctrl-Q", "quit"),
            Line::from(""),
            section("PANES"),
            row("Ctrl-F", "FLIGHT — cognition stream + affordances + intent"),
            row("Ctrl-R", "RUNS — research/work runs"),
            row("Ctrl-W", "WIRE — raw daemon event wire + live cap%"),
            row("Ctrl-T", "CHAT — compose + send through the daemon bus"),
            Line::from(""),
            section("FLIGHT (normal mode)"),
            row("1 - 9", "pick affordance N"),
            row("i / Esc", "enter / leave free-text intent"),
            row("y / n", "confirm / cancel a gated action"),
            Line::from(""),
            Line::from(Span::styled("  Esc · ? · F1 · Enter to close", Style::default().fg(MUTED))),
        ];

        let block = Block::default()
            .title(" Keybindings ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(EMERALD))
            .padding(Padding::symmetric(2, 1))
            .style(Style::default().bg(ratatui::style::Color::Indexed(235)));

        let para = Paragraph::new(lines)
            .block(block)
            .alignment(Alignment::Left);

        let area = centered_rect(64, 72, area);
        frame.render_widget(Clear, area);
        frame.render_widget(para, area);
    }
}

/// Helper to center a rect.
fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}
