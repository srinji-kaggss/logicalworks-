// src/screens/mod.rs — Screen trait + ScreenId enum
// All four screens (FLIGHT/RUNS/QUEUE/WIRE) implement this trait.
use ratatui::{Frame, layout::Rect};
use crate::{bridge::DaemonState, tui::Event};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ScreenId {
    Flight,
    Runs,
    Queue,
    Wire,
}

impl ScreenId {
    pub fn all() -> &'static [ScreenId] {
        &[ScreenId::Flight, ScreenId::Runs, ScreenId::Queue, ScreenId::Wire]
    }

    pub fn label(&self) -> &'static str {
        match self {
            ScreenId::Flight => "F·FLIGHT",
            ScreenId::Runs   => "R·RUNS",
            ScreenId::Queue  => "Q·QUEUE",
            ScreenId::Wire   => "W·WIRE",
        }
    }

    pub fn key_hint(&self) -> &'static str {
        match self {
            ScreenId::Flight => "f",
            ScreenId::Runs   => "r",
            ScreenId::Queue  => "q",
            ScreenId::Wire   => "w",
        }
    }
}

/// Commands a screen can return to the app loop.
#[derive(Debug)]
pub enum ScreenCmd {
    None,
    Navigate(ScreenId),
    InjectIntent { kind: String, scope: String, payload: serde_json::Value },
    Confirm { prompt: String, on_confirm: Box<ScreenCmd> },
    Quit,
}

pub trait Screen: Send {
    fn handle_event(&mut self, event: &Event, state: &DaemonState) -> ScreenCmd;
    fn on_daemon_tick(&mut self, state: &DaemonState);
    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState);
    fn id(&self) -> ScreenId;
}

pub mod flight;
pub mod runs;
pub mod queue;
pub mod wire;
