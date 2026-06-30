use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, BorderType, Padding, Clear, Paragraph, List, ListItem, ListState},
};
use crossterm::event::{KeyCode, KeyModifiers};
use crate::tui::Event;
use crate::bridge::palette::*;
use crate::screens::ScreenId;

#[derive(Clone)]
pub struct PaletteItem {
    pub label: String,
    pub hint: String,
    pub outcome: PaletteOutcome,
}

#[derive(Clone)]
pub enum PaletteOutcome {
    Navigate(ScreenId),
    Help,
    Quit,
    None,
}

pub struct CommandPalette {
    pub active: bool,
    query: String,
    items: Vec<PaletteItem>,
    filtered: Vec<usize>,
    selected: usize,
    list_state: ListState,
}

impl CommandPalette {
    pub fn new(items: Vec<PaletteItem>) -> Self {
        let filtered = (0..items.len()).collect();
        let mut list_state = ListState::default();
        list_state.select(Some(0));
        
        Self {
            active: false,
            query: String::new(),
            items,
            filtered,
            selected: 0,
            list_state,
        }
    }

    pub fn toggle(&mut self) {
        self.active = !self.active;
        if self.active {
            self.query.clear();
            self.filtered = (0..self.items.len()).collect();
            self.selected = 0;
            self.list_state.select(Some(0));
        }
    }

    pub fn handle_event(&mut self, event: &Event) -> Option<PaletteOutcome> {
        if !self.active { return None; }
        
        if let Event::Key(key) = event {
            match key.code {
                KeyCode::Esc => {
                    self.active = false;
                    return Some(PaletteOutcome::None);
                }
                KeyCode::Enter => {
                    self.active = false;
                    if let Some(&idx) = self.filtered.get(self.selected) {
                        return Some(self.items[idx].outcome.clone());
                    }
                    return Some(PaletteOutcome::None);
                }
                KeyCode::Up | KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if self.selected > 0 {
                        self.selected -= 1;
                        self.list_state.select(Some(self.selected));
                    }
                    return Some(PaletteOutcome::None);
                }
                KeyCode::Down | KeyCode::Char('n') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                    if self.selected < self.filtered.len().saturating_sub(1) {
                        self.selected += 1;
                        self.list_state.select(Some(self.selected));
                    }
                    return Some(PaletteOutcome::None);
                }
                KeyCode::Char(c) => {
                    self.query.push(c);
                    self.update_filter();
                    return Some(PaletteOutcome::None);
                }
                KeyCode::Backspace => {
                    self.query.pop();
                    self.update_filter();
                    return Some(PaletteOutcome::None);
                }
                _ => {}
            }
        }
        // Eat the event when active so it doesn't propagate
        Some(PaletteOutcome::None)
    }

    fn update_filter(&mut self) {
        if self.query.is_empty() {
            self.filtered = (0..self.items.len()).collect();
        } else {
            self.filtered = self.items.iter()
                .enumerate()
                .filter(|(_, item)| {
                    item.label.to_lowercase().contains(&self.query.to_lowercase()) ||
                    item.hint.to_lowercase().contains(&self.query.to_lowercase())
                })
                .map(|(i, _)| i)
                .collect();
        }
        self.selected = 0;
        self.list_state.select(Some(0));
    }

    pub fn render(&self, frame: &mut Frame, area: Rect) {
        if !self.active { return; }

        let block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(AMBER))
            .padding(Padding::symmetric(2, 1))
            .style(Style::default().bg(SLATE_DIM));

        // Input line
        let input_line = Line::from(vec![
            Span::styled("> ", Style::default().fg(EMERALD)),
            Span::styled(&self.query, Style::default().fg(CREAM)),
        ]);

        // Filtered items
        let items: Vec<ListItem> = self.filtered.iter()
            .map(|&i| {
                let item = &self.items[i];
                let line = if i == self.filtered[self.selected] {
                    Line::from(vec![
                        Span::styled(&item.label, Style::default().fg(AMBER).add_modifier(Modifier::BOLD)),
                        Span::styled(" ", Style::default()),
                        Span::styled(&item.hint, Style::default().fg(MUTED)),
                    ])
                } else {
                    Line::from(vec![
                        Span::styled(&item.label, Style::default().fg(CREAM)),
                        Span::styled(" ", Style::default()),
                        Span::styled(&item.hint, Style::default().fg(MUTED)),
                    ])
                };
                ListItem::new(line)
            })
            .collect();

        let list = List::new(items)
            .block(Block::default())
            .highlight_style(Style::default().bg(SLATE_DIM).add_modifier(Modifier::BOLD));

        let area = centered_rect(60, 60, area);
        frame.render_widget(Clear, area);
        // Compute content area from the block (honours borders + padding), then draw the block.
        let inner_area = block.inner(area);
        frame.render_widget(block, area);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1),
                Constraint::Min(1),
            ])
            .split(inner_area);

        frame.render_widget(Paragraph::new(input_line), chunks[0]);
        frame.render_stateful_widget(list, chunks[1], &mut self.list_state.clone());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::KeyEvent;

    fn key(code: KeyCode, mods: KeyModifiers) -> Event {
        Event::Key(KeyEvent::new(code, mods))
    }
    fn typ(c: char) -> Event { key(KeyCode::Char(c), KeyModifiers::NONE) }

    fn palette() -> CommandPalette {
        CommandPalette::new(vec![
            PaletteItem { label: "Go: FLIGHT".into(), hint: "switch pane".into(), outcome: PaletteOutcome::Navigate(ScreenId::Flight) },
            PaletteItem { label: "Go: RUNS".into(),   hint: "switch pane".into(), outcome: PaletteOutcome::Navigate(ScreenId::Runs) },
            PaletteItem { label: "Quit".into(),       hint: "Ctrl-Q".into(),      outcome: PaletteOutcome::Quit },
        ])
    }

    #[test]
    fn inactive_palette_ignores_events() {
        let mut p = palette();
        assert!(p.handle_event(&typ('x')).is_none());
    }

    #[test]
    fn typing_filters_then_enter_returns_match() {
        let mut p = palette();
        p.toggle();
        for c in "runs".chars() { p.handle_event(&typ(c)); }
        // Only "Go: RUNS" survives the filter; it is selected at index 0.
        let out = p.handle_event(&key(KeyCode::Enter, KeyModifiers::NONE)).unwrap();
        assert!(matches!(out, PaletteOutcome::Navigate(ScreenId::Runs)));
        assert!(!p.active, "Enter closes the palette");
    }

    #[test]
    fn esc_closes_and_returns_none() {
        let mut p = palette();
        p.toggle();
        let out = p.handle_event(&key(KeyCode::Esc, KeyModifiers::NONE)).unwrap();
        assert!(matches!(out, PaletteOutcome::None));
        assert!(!p.active);
    }

    #[test]
    fn ctrl_n_advances_selection() {
        let mut p = palette();
        p.toggle(); // all 3 items, selected = 0 (FLIGHT)
        p.handle_event(&key(KeyCode::Char('n'), KeyModifiers::CONTROL)); // -> RUNS
        let out = p.handle_event(&key(KeyCode::Enter, KeyModifiers::NONE)).unwrap();
        assert!(matches!(out, PaletteOutcome::Navigate(ScreenId::Runs)));
    }

    #[test]
    fn backspace_widens_filter_again() {
        let mut p = palette();
        p.toggle();
        for c in "quit".chars() { p.handle_event(&typ(c)); }   // filters to "Quit"
        for _ in 0..4 { p.handle_event(&key(KeyCode::Backspace, KeyModifiers::NONE)); }
        // Back to empty query → all items; selection reset to first (FLIGHT).
        let out = p.handle_event(&key(KeyCode::Enter, KeyModifiers::NONE)).unwrap();
        assert!(matches!(out, PaletteOutcome::Navigate(ScreenId::Flight)));
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