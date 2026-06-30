// src/app.rs — App: owns all screens, drives the event loop (adapted from rainfrog)
// Source inspiration: https://github.com/achristmascarl/rainfrog (MIT)
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use color_eyre::Result;
use crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Tabs},
};

use crate::bridge::{DaemonBridge, DaemonState, palette::*};
use crate::screens::{Screen, ScreenCmd, ScreenId};
use crate::screens::{
    chat::ChatScreen,
    flight::FlightScreen,
    runs::RunsScreen,
    queue::QueueScreen,
    wire::WireScreen,
};
use crate::ui::command_palette::{CommandPalette, PaletteItem, PaletteOutcome};
use crate::ui::help_overlay::HelpOverlay;
use crate::tui::{Event, Tui};

pub struct App {
    pub should_quit: bool,
    active_screen:   ScreenId,
    screens:         HashMap<ScreenId, Box<dyn Screen>>,
    bridge:          Arc<DaemonBridge>,
    pub state:       Arc<RwLock<DaemonState>>,
    status_msg:      Option<String>,
    status_ttl:      u8,    // clear status_msg after N ticks
    confirm_overlay: crate::ui::confirm_overlay::ConfirmOverlay,
    palette:         CommandPalette,
    help:            HelpOverlay,
}

/// The static command-palette catalogue: every screen jump + the global actions.
/// Kept honest — each entry maps to a real outcome the app already performs.
fn palette_items() -> Vec<PaletteItem> {
    let mut items: Vec<PaletteItem> = ScreenId::all()
        .iter()
        .map(|id| PaletteItem {
            label: format!("Go: {}", id.label().split('·').last().unwrap_or(id.label())),
            hint:  "switch pane".to_string(),
            outcome: PaletteOutcome::Navigate(*id),
        })
        .collect();
    items.push(PaletteItem {
        label: "Help: Keybindings".to_string(),
        hint:  "F1 / ?".to_string(),
        outcome: PaletteOutcome::Help,
    });
    items.push(PaletteItem {
        label: "Quit".to_string(),
        hint:  "Ctrl-Q".to_string(),
        outcome: PaletteOutcome::Quit,
    });
    items
}

impl App {
    pub fn new(bridge: Arc<DaemonBridge>, state: Arc<RwLock<DaemonState>>) -> Self {
        let mut screens: HashMap<ScreenId, Box<dyn Screen>> = HashMap::new();
        screens.insert(ScreenId::Flight, Box::new(FlightScreen::new()));
        screens.insert(ScreenId::Runs,   Box::new(RunsScreen::new()));
        screens.insert(ScreenId::Queue,  Box::new(QueueScreen::new()));
        screens.insert(ScreenId::Wire,   Box::new(WireScreen::new()));
        screens.insert(ScreenId::Chat,   Box::new(ChatScreen::new()));

        Self {
            should_quit: false,
            active_screen: ScreenId::Flight,
            screens,
            bridge,
            state,
            status_msg: None,
            status_ttl: 0,
            confirm_overlay: crate::ui::confirm_overlay::ConfirmOverlay::new(),
            palette: CommandPalette::new(palette_items()),
            help: HelpOverlay::new(),
        }
    }

    /// Main event dispatch. Called from the run() loop below.
    pub fn handle_event(&mut self, event: Event) {
        if self.confirm_overlay.active {
            if let Some(cmd) = self.confirm_overlay.handle_event(&event) {
                self.execute_cmd(cmd);
            }
            return;
        }

        // Keymap overlay: modal, eats every event while open.
        if self.help.active {
            self.help.handle_event(&event);
            return;
        }

        // Command palette: modal. Resolve its outcome into an app action.
        if self.palette.active {
            if let Some(outcome) = self.palette.handle_event(&event) {
                self.apply_palette_outcome(outcome);
            }
            return;
        }

        match &event {
            // ── Global key bindings ──────────────────────────────────────────
            Event::Key(key) => {
                match key.code {
                    KeyCode::Char('q') if key.modifiers.contains(crossterm::event::KeyModifiers::CONTROL) => {
                        self.should_quit = true;
                        return;
                    }
                    // Command palette (IDE Ctrl-P / Cmd-P): fuzzy-find any action or pane.
                    KeyCode::Char('p') if key.modifiers.contains(crossterm::event::KeyModifiers::CONTROL) => {
                        self.palette.toggle();
                        return;
                    }
                    // Keymap reference (F1 — never a typed char, so it can't clash with input).
                    KeyCode::F(1) => { self.help.toggle(); return; }
                    // Tab switching
                    KeyCode::Char('f') if key.modifiers.contains(crossterm::event::KeyModifiers::CONTROL) => { self.active_screen = ScreenId::Flight; return; }
                    KeyCode::Char('r') if key.modifiers.contains(crossterm::event::KeyModifiers::CONTROL) => { self.active_screen = ScreenId::Runs;   return; }
                    KeyCode::Char('w') if key.modifiers.contains(crossterm::event::KeyModifiers::CONTROL) => { self.active_screen = ScreenId::Wire;   return; }
                    KeyCode::Char('t') if key.modifiers.contains(crossterm::event::KeyModifiers::CONTROL) => { self.active_screen = ScreenId::Chat;   return; }
                    KeyCode::Tab | KeyCode::Right => {
                        let all = ScreenId::all();
                        if let Some(pos) = all.iter().position(|id| *id == self.active_screen) {
                            self.active_screen = all[(pos + 1) % all.len()];
                        }
                        return;
                    }
                    KeyCode::BackTab | KeyCode::Left => {
                        let all = ScreenId::all();
                        if let Some(pos) = all.iter().position(|id| *id == self.active_screen) {
                            self.active_screen = all[(pos + all.len() - 1) % all.len()];
                        }
                        return;
                    }
                    // Bare digit shortcuts (1-4 → screen) removed: they collided with
                    // FLIGHT's affordance hotkeys (Alt/normal `1`-`9` pick affordance N)
                    // AND with typing digits 1-4 in the free-text input. Screen switching
                    // is fully covered by Ctrl-F/R/W and Tab/BackTab, so the digits added
                    // nothing and silently broke the affordance + input paths.
                    _ => {}
                }
            }
            // ── Global mouse bindings ────────────────────────────────────────
            Event::Mouse(m) => {
                if m.kind == crossterm::event::MouseEventKind::Down(crossterm::event::MouseButton::Left) {
                    // Check if clicked in the tab bar area (row 0)
                    if m.row == 0 {
                        let mut current_x = 0;
                        for id in ScreenId::all() {
                            let label_len = id.label().len() as u16 + 2; // " {label} "
                            if m.column >= current_x && m.column < current_x + label_len {
                                self.active_screen = *id;
                                return;
                            }
                            current_x += label_len + 3; // +3 for the " │ " divider
                        }
                    }
                }
            }
            // ── Daemon tick: propagate to active screen ──────────────────────
            Event::DaemonTick => {
                if let Ok(s) = self.state.read() {
                    if let Some(screen) = self.screens.get_mut(&self.active_screen) {
                        screen.on_daemon_tick(&s);
                    }
                }
                // Tick down status TTL
                if self.status_ttl > 0 {
                    self.status_ttl -= 1;
                    if self.status_ttl == 0 { self.status_msg = None; }
                }
                return;
            }
            // Terminal/stdin closed (emitted by the tui poll task on stream end).
            Event::Closed => { self.should_quit = true; return; }
            _ => {}
        }

        // ── Delegate to active screen ────────────────────────────────────────
        let cmd = {
            let state_guard = self.state.read().unwrap_or_else(|p| p.into_inner());
            if let Some(screen) = self.screens.get_mut(&self.active_screen) {
                screen.handle_event(&event, &state_guard)
            } else {
                ScreenCmd::None
            }
        };

        self.execute_cmd(cmd);
    }

    fn execute_cmd(&mut self, cmd: ScreenCmd) {
        match cmd {
            ScreenCmd::None => {}
            ScreenCmd::EnqueueWork { kind, payload } => {
                let session_id = self.human_session_id();
                let payload_json = serde_json::to_string(&payload).unwrap_or_default();
                match self.bridge.enqueue_work(&kind, &session_id, &payload_json) {
                    Ok(()) => self.set_status(format!("→ {kind} enqueued"), 8),
                    Err(e) => self.set_status(format!("enqueue failed: {e}"), 16),
                }
            }
            ScreenCmd::EmitEvent { kind, payload } => {
                let session_id = self.human_session_id();
                let payload_json = serde_json::to_string(&payload).unwrap_or_default();
                match self.bridge.emit_event(&kind, &session_id, &payload_json) {
                    Ok(()) => self.set_status(format!("→ {kind} sent"), 8),
                    Err(e) => self.set_status(format!("emit failed: {e}"), 16),
                }
            }
            ScreenCmd::Confirm { prompt, on_confirm } => {
                self.confirm_overlay.show(prompt, on_confirm);
            }
        }
    }

    /// Resolve a command-palette selection into a concrete app action.
    fn apply_palette_outcome(&mut self, outcome: PaletteOutcome) {
        match outcome {
            PaletteOutcome::Navigate(id) => self.active_screen = id,
            PaletteOutcome::Help => self.help.active = true,
            PaletteOutcome::Quit => self.should_quit = true,
            PaletteOutcome::None => {}
        }
    }

    fn set_status(&mut self, msg: String, ttl: u8) {
        self.status_msg = Some(msg);
        self.status_ttl = ttl;
    }

    /// Stable session id for human-originated writes, derived from the daemon pid.
    fn human_session_id(&self) -> String {
        self.state.read().ok()
            .and_then(|s| s.status.pid.map(|p| format!("human-{p}")))
            .unwrap_or_else(|| "human-anon".to_string())
    }

    /// Render the full frame.
    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();
        
        // Base dark background (Opencode aesthetic)
        let base_block = ratatui::widgets::Block::default()
            .style(Style::default().bg(crate::bridge::palette::BG_MAIN));
        frame.render_widget(base_block, area);

        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(2), // tab bar
                Constraint::Min(0),    // screen content
                Constraint::Length(1), // status bar
            ])
            .split(area);

        self.render_tabs(frame, chunks[0]);
        self.render_screen(frame, chunks[1]);
        self.render_status_bar(frame, chunks[2]);

        // Overlays paint last (top of the z-order).
        self.palette.render(frame, area);
        self.help.render(frame, area);
        self.confirm_overlay.render(frame, area);
    }

    fn render_tabs(&self, frame: &mut Frame, area: Rect) {
        let tab_labels: Vec<Line> = ScreenId::all()
            .iter()
            .map(|id| {
                let active = *id == self.active_screen;
                Line::from(vec![
                    Span::styled(
                        format!(" {} ", id.label()),
                        if active {
                            Style::default().fg(AMBER).add_modifier(Modifier::BOLD)
                        } else {
                            Style::default().fg(SLATE_DIM)
                        },
                    ),
                ])
            })
            .collect();

        let selected = ScreenId::all()
            .iter()
            .position(|id| *id == self.active_screen)
            .unwrap_or(0);

        let tabs = Tabs::new(tab_labels)
            .block(Block::default())
            .select(selected)
            .highlight_style(Style::default().fg(AMBER).add_modifier(Modifier::UNDERLINED));
        frame.render_widget(tabs, area);
    }

    fn render_screen(&self, frame: &mut Frame, area: Rect) {
        let state_guard = self.state.read().unwrap_or_else(|p| p.into_inner());
        if let Some(screen) = self.screens.get(&self.active_screen) {
            screen.render(frame, area, &state_guard);
        }
    }

    fn render_status_bar(&self, frame: &mut Frame, area: Rect) {
        let state_guard = self.state.read().unwrap_or_else(|p| p.into_inner());
        let s = &state_guard.status;

        let daemon_indicator = if s.alive {
            Span::styled("● DAEMON", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD))
        } else {
            Span::styled("○ DAEMON", Style::default().fg(RED_ERR))
        };

        let mid = if let Some(msg) = &self.status_msg {
            Span::styled(format!("  {}", msg), Style::default().fg(AMBER))
        } else {
            Span::styled(
                format!("  {} events · ^P palette · F1 help · Tab switch · ^Q quit", state_guard.events.len()),
                Style::default().fg(MUTED),
            )
        };

        let bar = Line::from(vec![
            Span::styled(" ", Style::default()),
            daemon_indicator,
            Span::styled(
                s.pid.map(|p| format!(" · pid {}", p)).unwrap_or_default(),
                Style::default().fg(SLATE_DIM),
            ),
            mid,
        ]);

        let status = ratatui::widgets::Paragraph::new(bar)
            .style(Style::default().bg(ratatui::style::Color::Indexed(235)));
        frame.render_widget(status, area);
    }
}

/// The main async run loop. Adapted from rainfrog's main event loop pattern.
pub async fn run(mut tui: Tui, mut app: App) -> Result<()> {
    tui.enter()?;

    loop {
        // Draw
        tui.draw(|frame| app.render(frame))?;

        // Wait for next event
        let Some(event) = tui.next().await else { break };

        // Let app process it
        app.handle_event(event);

        if app.should_quit { break; }
    }

    tui.exit()?;
    Ok(())
}
