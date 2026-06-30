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
    Chat,
}

impl ScreenId {
    pub fn all() -> &'static [ScreenId] {
        &[ScreenId::Flight, ScreenId::Runs, ScreenId::Queue, ScreenId::Wire, ScreenId::Chat]
    }

    pub fn label(&self) -> &'static str {
        match self {
            ScreenId::Flight => "F·FLIGHT",
            ScreenId::Runs   => "R·RUNS",
            ScreenId::Queue  => "Q·QUEUE",
            ScreenId::Wire   => "W·WIRE",
            ScreenId::Chat   => "C·CHAT",
        }
    }
}

/// Commands a screen can return to the app loop.
/// Screen switching and quit are handled globally (Tab / Ctrl-F/R/W/T / Ctrl-Q in
/// app.rs), so screens never request navigation or quit — they only act on the bus.
#[derive(Debug, Clone)]
pub enum ScreenCmd {
    None,
    /// Affordance picked: enqueue a daemon WORK item (kind ∈ WORK_KINDS).
    EnqueueWork { kind: String, payload: serde_json::Value },
    /// Free-text human intent: emit a human event (kind ∈ event KINDS, e.g. human_message).
    EmitEvent { kind: String, payload: serde_json::Value },
    Confirm { prompt: String, on_confirm: Box<ScreenCmd> },
}

pub trait Screen: Send {
    fn handle_event(&mut self, event: &Event, state: &DaemonState) -> ScreenCmd;
    fn on_daemon_tick(&mut self, state: &DaemonState);
    fn render(&self, frame: &mut Frame, area: Rect, state: &DaemonState);
}

pub mod flight;
pub mod runs;
pub mod queue;
pub mod wire;
pub mod chat;
