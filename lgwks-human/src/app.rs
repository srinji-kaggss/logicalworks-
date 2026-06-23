// src/app.rs — App: owns all screens, drives the event loop (adapted from rainfrog)
// Source inspiration: https://github.com/achristmascarl/rainfrog (MIT)
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use color_eyre::{eyre::eyre, Result};
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
    flight::FlightScreen,
    runs::RunsScreen,
    queue::QueueScreen,
    wire::WireScreen,
};
use crate::tui::{Event, Tui};

pub struct App {
    pub should_quit: bool,
    active_screen:   ScreenId,
    screens:         HashMap<ScreenId, Box<dyn Screen>>,
    bridge:          Arc<DaemonBridge>,
    pub state:       Arc<RwLock<DaemonState>>,
    status_msg:      Option<String>,
    status_ttl:      u8,    // clear status_msg after N ticks
}

impl App {
    pub fn new(bridge: Arc<DaemonBridge>, state: Arc<RwLock<DaemonState>>) -> Self {
        let mut screens: HashMap<ScreenId, Box<dyn Screen>> = HashMap::new();
        screens.insert(ScreenId::Flight, Box::new(FlightScreen::new()));
        screens.insert(ScreenId::Runs,   Box::new(RunsScreen::new()));
        screens.insert(ScreenId::Queue,  Box::new(QueueScreen::new()));
        screens.insert(ScreenId::Wire,   Box::new(WireScreen::new()));

        Self {
            should_quit: false,
            active_screen: ScreenId::Flight,
            screens,
            bridge,
            state,
            status_msg: None,
            status_ttl: 0,
        }
    }

    /// Main event dispatch. Called from the run() loop below.
    pub fn handle_event(&mut self, event: Event) {
        match &event {
            // ── Global key bindings ──────────────────────────────────────────
            Event::Key(key) => {
                match key.code {
                    KeyCode::Char('q') if matches!(self.active_screen, _) => {
                        // Only quit from non-flight screens or when flight input is empty
                        self.should_quit = true;
                        return;
                    }
                    // Tab switching
                    KeyCode::Char('f') => { self.active_screen = ScreenId::Flight; return; }
                    KeyCode::Char('r') => { self.active_screen = ScreenId::Runs;   return; }
                    // 'q' handled above for quit — use Shift+Q for queue?
                    // Actually q is reserved for quit. Use ctrl+q for queue tab.
                    KeyCode::Char('w') => { self.active_screen = ScreenId::Wire;   return; }
                    _ => {}
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
            Event::Quit => { self.should_quit = true; return; }
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
            ScreenCmd::Navigate(id) => { self.active_screen = id; }
            ScreenCmd::Quit => { self.should_quit = true; }
            ScreenCmd::InjectIntent { kind, scope, payload } => {
                let session_id = self.state.read().ok()
                    .and_then(|s| s.status.pid.map(|p| format!("human-{}", p)))
                    .unwrap_or_else(|| "human-anon".to_string());
                let payload_json = serde_json::to_string(&payload).unwrap_or_default();
                if let Err(e) = self.bridge.emit_intent(&kind, &scope, &session_id, &payload_json) {
                    self.set_status(format!("emit error: {e}"), 12);
                } else {
                    self.set_status(format!("→ {kind} injected"), 8);
                }
            }
            ScreenCmd::Confirm { prompt: _, on_confirm: _ } => {
                // TODO U-09: render confirmation overlay
            }
        }
    }

    fn set_status(&mut self, msg: String, ttl: u8) {
        self.status_msg = Some(msg);
        self.status_ttl = ttl;
    }

    /// Render the full frame.
    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();
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
                format!("  {} events · q quit · f/r/q/w switch", state_guard.events.len()),
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
