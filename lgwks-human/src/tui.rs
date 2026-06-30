// src/tui.rs — verbatim from rainfrog (MIT), adapted for lgwks-human
// Source: https://github.com/achristmascarl/rainfrog (MIT License)
use std::{
    ops::{Deref, DerefMut},
    time::Duration,
};

use color_eyre::eyre::Result;
use crossterm::{
    cursor,
    event::{
        DisableBracketedPaste, DisableMouseCapture, EnableBracketedPaste, EnableMouseCapture,
        Event as CrosstermEvent, KeyEvent, KeyEventKind, MouseEvent,
    },
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, SetTitle},
};
use futures::{FutureExt, StreamExt};
use ratatui::backend::CrosstermBackend as Backend;
use tokio::{
    sync::mpsc::{self, UnboundedReceiver, UnboundedSender},
    task::JoinHandle,
};
use tokio_util::sync::CancellationToken;

pub type IO = std::io::Stdout;
pub fn io() -> IO {
    std::io::stdout()
}

/// All events flowing through the TUI event loop.
/// Tick = daemon poll cadence; Render = redraw; DaemonTick = fresh data from bridge.
#[derive(Clone, Debug)]
pub enum Event {
    Init,
    Error,
    /// The input stream ended (terminal/stdin closed) — the app must quit.
    Closed,
    Tick,
    Render,
    FocusGained,
    FocusLost,
    Paste(String),
    Key(KeyEvent),
    Mouse(MouseEvent),
    /// Terminal was resized. Carries no payload: ratatui re-queries the backend
    /// size on every `draw`, so the redraw at the top of the run loop is the fix.
    Resize,
    /// Fired every 250ms from the bridge poll task — carries new daemon events
    DaemonTick,
}

pub struct Tui {
    pub terminal: ratatui::Terminal<Backend<IO>>,
    pub task: JoinHandle<()>,
    pub cancellation_token: CancellationToken,
    pub event_rx: UnboundedReceiver<Event>,
    pub event_tx: UnboundedSender<Event>,
    pub frame_rate: f64,
    pub tick_rate: f64,
    pub mouse: bool,
    pub paste: bool,
    pub title: Option<String>,
}

impl Tui {
    pub fn new() -> Result<Self> {
        let tick_rate = 4.0;   // 4 ticks/s for daemon poll
        let frame_rate = 15.0; // 15 fps render
        let terminal = ratatui::Terminal::new(Backend::new(io()))?;
        let (event_tx, event_rx) = mpsc::unbounded_channel();
        let cancellation_token = CancellationToken::new();
        let task = tokio::spawn(async {});
        Ok(Self {
            terminal,
            task,
            cancellation_token,
            event_rx,
            event_tx,
            frame_rate,
            tick_rate,
            mouse: true,
            paste: true,
            title: None,
        })
    }

    pub fn tick_rate(mut self, tick_rate: Option<f64>) -> Self {
        if let Some(r) = tick_rate { self.tick_rate = r; }
        self
    }

    pub fn frame_rate(mut self, frame_rate: Option<f64>) -> Self {
        if let Some(r) = frame_rate { self.frame_rate = r; }
        self
    }

    pub fn title(mut self, title: Option<String>) -> Self {
        self.title = title;
        self
    }

    pub fn start(&mut self) {
        let tick_delay = Duration::from_secs_f64(1.0 / self.tick_rate);
        let render_delay = Duration::from_secs_f64(1.0 / self.frame_rate);
        self.cancel();
        self.cancellation_token = CancellationToken::new();
        let _ct = self.cancellation_token.clone();
        let _tx = self.event_tx.clone();
        self.task = tokio::spawn(async move {
            let mut reader = crossterm::event::EventStream::new();
            let mut tick_interval = tokio::time::interval(tick_delay);
            let mut render_interval = tokio::time::interval(render_delay);
            let mut last_mouse: Option<MouseEvent> = None;
            _tx.send(Event::Init).unwrap();
            loop {
                let tick_delay = tick_interval.tick();
                let render_delay = render_interval.tick();
                let crossterm_event = reader.next().fuse();
                tokio::select! {
                    _ = _ct.cancelled() => { break; }
                    maybe_event = crossterm_event => {
                        match maybe_event {
                            Some(Ok(evt)) => match evt {
                                CrosstermEvent::Key(key) => {
                                    if key.kind == KeyEventKind::Press {
                                        // Ignore send failure: on shutdown the receiver
                                        // (owned by `run`'s `tui.next()`) drops first, so
                                        // the next send would panic the poll task. Same
                                        // class as the Drop unwrap we removed.
                                        let _ = _tx.send(Event::Key(key));
                                    }
                                }
                                CrosstermEvent::Mouse(m) => { last_mouse = Some(m); }
                                CrosstermEvent::Resize(_, _) => { let _ = _tx.send(Event::Resize); }
                                CrosstermEvent::FocusLost => { let _ = _tx.send(Event::FocusLost); }
                                CrosstermEvent::FocusGained => { let _ = _tx.send(Event::FocusGained); }
                                CrosstermEvent::Paste(s) => { let _ = _tx.send(Event::Paste(s)); }
                            }
                            Some(Err(_)) => { let _ = _tx.send(Event::Error); }
                            // Input stream ended (terminal/stdin closed). Without this
                            // the run loop would spin forever on ticks, never exiting on
                            // disconnect. Signal Closed so the app quits cleanly.
                            None => { let _ = _tx.send(Event::Closed); break; }
                        }
                    }
                    _ = tick_delay => { let _ = _tx.send(Event::Tick); }
                    _ = render_delay => {
                        let _ = _tx.send(Event::Render);
                        if let Some(m) = last_mouse.take() {
                            let _ = _tx.send(Event::Mouse(m));
                        }
                    }
                }
            }
        });
    }

    pub fn stop(&self) -> Result<()> {
        self.cancel();
        let mut counter = 0;
        while !self.task.is_finished() {
            std::thread::sleep(Duration::from_millis(1));
            counter += 1;
            if counter > 50 { self.task.abort(); }
            if counter > 100 { break; }
        }
        Ok(())
    }

    pub fn enter(&mut self) -> Result<()> {
        crossterm::terminal::enable_raw_mode()?;
        if let Some(t) = &self.title {
            crossterm::execute!(io(), SetTitle(t))?;
        }
        crossterm::execute!(io(), EnterAlternateScreen, cursor::Hide)?;
        if self.mouse {
            crossterm::execute!(io(), EnableMouseCapture)?;
        }
        if self.paste {
            crossterm::execute!(io(), EnableBracketedPaste)?;
        }
        self.start();
        Ok(())
    }

    pub fn exit(&mut self) -> Result<()> {
        self.stop()?;
        if crossterm::terminal::is_raw_mode_enabled()? {
            self.flush()?;
            crossterm::execute!(io(), DisableBracketedPaste)?;
            crossterm::execute!(io(), DisableMouseCapture)?;
            crossterm::execute!(io(), LeaveAlternateScreen, cursor::Show)?;
            crossterm::terminal::disable_raw_mode()?;
        }
        Ok(())
    }

    pub fn cancel(&self) { self.cancellation_token.cancel(); }

    pub async fn next(&mut self) -> Option<Event> {
        self.event_rx.recv().await
    }
}

impl Deref for Tui {
    type Target = ratatui::Terminal<Backend<IO>>;
    fn deref(&self) -> &Self::Target { &self.terminal }
}

impl DerefMut for Tui {
    fn deref_mut(&mut self) -> &mut Self::Target { &mut self.terminal }
}

impl Drop for Tui {
    // Never unwrap in Drop: if exit() errors during a panic unwind, unwrapping would
    // double-panic and abort, leaving the terminal in raw mode. Best-effort restore.
    fn drop(&mut self) { let _ = self.exit(); }
}
