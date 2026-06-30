use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect, Alignment},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, BorderType, Padding, Clear, Paragraph, Wrap},
};
use crossterm::event::KeyCode;
use crate::tui::Event;
use crate::bridge::palette::*;
use crate::screens::ScreenCmd;

pub struct ConfirmOverlay {
    pub active: bool,
    prompt: String,
    on_confirm: Option<Box<ScreenCmd>>,
}

impl ConfirmOverlay {
    pub fn new() -> Self {
        Self {
            active: false,
            prompt: String::new(),
            on_confirm: None,
        }
    }

    pub fn show(&mut self, prompt: String, cmd: Box<ScreenCmd>) {
        self.prompt = prompt;
        self.on_confirm = Some(cmd);
        self.active = true;
    }

    pub fn handle_event(&mut self, event: &Event) -> Option<ScreenCmd> {
        if !self.active { return None; }
        
        if let Event::Key(key) = event {
            match key.code {
                KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => {
                    self.active = false;
                    let cmd = self.on_confirm.take().unwrap_or(Box::new(ScreenCmd::None));
                    return Some(*cmd);
                }
                KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => {
                    self.active = false;
                    self.on_confirm = None;
                    return Some(ScreenCmd::None);
                }
                _ => {}
            }
        }
        // Eat the event when active so it doesn't propagate
        Some(ScreenCmd::None)
    }

    pub fn render(&self, frame: &mut Frame, area: Rect) {
        if !self.active { return; }

        let text = vec![
            Line::from(vec![
                Span::styled("⚠ WARNING", Style::default().fg(RED_ERR).add_modifier(Modifier::BOLD)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled(&self.prompt, Style::default().fg(CREAM)),
            ]),
            Line::from(""),
            Line::from(vec![
                Span::styled(" [Y] Confirm    [N/Esc] Cancel ", Style::default().fg(AMBER)),
            ]),
        ];

        let block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(RED_ERR))
            .padding(Padding::symmetric(2, 1))
            .style(Style::default().bg(ratatui::style::Color::Indexed(235)));
            
        let paragraph = Paragraph::new(text)
            .block(block)
            .alignment(Alignment::Center)
            .wrap(Wrap { trim: true });

        let area = centered_rect(60, 30, area);
        frame.render_widget(Clear, area);
        frame.render_widget(paragraph, area);
    }
}

/// Helper to center a rect
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
