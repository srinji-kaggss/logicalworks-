mod models;
mod db;

use color_eyre::{Result, eyre::WrapErr, eyre::eyre};
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, EnableMouseCapture, DisableMouseCapture, MouseEventKind, MouseButton},
    execute,
};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, ListItem, List},
    DefaultTerminal, Frame,
};
use std::time::{Duration, Instant};
use std::process::Command;
use std::path::{PathBuf};
use std::collections::HashMap;
use tui_input::Input;
use tui_input::backend::crossterm::EventHandler;
use crate::models::{DaemonEvent, WorkItem, DaemonStatus, NavModule, WorkflowDef};
use crate::db::Db;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    Normal,
    Insert,
}

struct App {
    should_quit: bool,
    last_tick: Instant,
    repo_root: PathBuf,
    script_path: PathBuf,
    status: DaemonStatus,
    events: Vec<DaemonEvent>,
    queue: Vec<WorkItem>,
    nav_modules: Vec<(String, NavModule)>,
    workflows: HashMap<String, WorkflowDef>,
    selected_workflow: Option<String>,
    workflow_list_state: ratatui::widgets::ListState,
    form_input: Input,
    mode: Mode,
    status_msg: Option<String>,
}

impl App {
    fn new(repo_root: PathBuf) -> Self {
        let script_path = repo_root.join("lgwks");
        Self {
            should_quit: false,
            last_tick: Instant::now(),
            repo_root: repo_root.clone(),
            script_path,
            status: DaemonStatus {
                pid: None,
                status: "stopped".to_string(),
                repo_root: repo_root.to_string_lossy().to_string(),
                heartbeat_at: "".to_string(),
                alive: false,
                lock_present: false,
            },
            events: Vec::new(),
            queue: Vec::new(),
            nav_modules: Vec::new(),
            workflows: HashMap::new(),
            selected_workflow: None,
            workflow_list_state: ratatui::widgets::ListState::default(),
            form_input: Input::default(),
            mode: Mode::Normal,
            status_msg: None,
        }
    }

    fn update_data(&mut self, db: &Db) {
        if let Ok(status) = db.get_status() {
            self.status = status;
        }
        if let Ok(events) = db.get_events(50) {
            self.events = events;
        }
        if let Ok(queue) = db.get_queue(20) {
            self.queue = queue;
        }
        if self.workflows.is_empty() {
            if let Ok(workflows) = db.get_workflows() {
                self.workflows = workflows;
            }
        }
        if self.nav_modules.is_empty() {
            if let Ok(navmap) = db.get_navmap() {
                let mut modules: Vec<_> = navmap.modules.into_iter().collect();
                modules.sort_by(|a, b| a.0.cmp(&b.0));
                self.nav_modules = modules;
            }
        }
    }

    fn execute_workflow(&mut self, db: &Db) {
        if let Some(ref wf_name) = self.selected_workflow {
            let input_val = self.form_input.value().to_string();
            self.status_msg = Some(format!("Executing {}...", wf_name));
            
            // Secure Execution using absolute paths and vector args
            let mut args = vec![self.script_path.to_str().unwrap_or("lgwks"), "workflow", wf_name];
            if !input_val.is_empty() {
                args.push(&input_val);
            }

            let _ = db.emit_telemetry("control", "workflow_event", "human_message", &format!("Triggered workflow: {}", wf_name));

            let status = Command::new("python3")
                .args(&args)
                .current_dir(&self.repo_root)
                .status();

            match status {
                Ok(s) if s.success() => {
                    self.status_msg = Some(format!("Workflow {} completed.", wf_name));
                }
                Ok(s) => {
                    self.status_msg = Some(format!("Error: Process exited with code {}", s));
                }
                Err(e) => {
                    self.status_msg = Some(format!("Error: Failed to execute: {}", e));
                }
            }
            self.mode = Mode::Normal;
        }
    }

    fn start_daemon(&mut self, db: &Db) {
        self.status_msg = Some("Starting daemon...".to_string());
        let _ = db.emit_telemetry("control", "human_message", "daemon_start", "Starting daemon via TUI");
        
        let status = Command::new("python3")
            .args([self.script_path.to_str().unwrap_or("lgwks"), "daemon", "start"])
            .current_dir(&self.repo_root)
            .status();

        match status {
            Ok(s) if s.success() => {
                self.status_msg = Some("Daemon started successfully.".to_string());
            }
            Ok(s) => {
                self.status_msg = Some(format!("Error: Process exited with code {}", s));
            }
            Err(e) => {
                self.status_msg = Some(format!("Error: Failed to execute: {}", e));
            }
        }
    }

    fn stop_daemon(&mut self, db: &Db) {
        self.status_msg = Some("Stopping daemon...".to_string());
        let _ = db.emit_telemetry("control", "human_message", "daemon_stop", "Stopping daemon via TUI");
        
        let status = Command::new("python3")
            .args([self.script_path.to_str().unwrap_or("lgwks"), "daemon", "stop"])
            .current_dir(&self.repo_root)
            .status();

        match status {
            Ok(_) => self.status_msg = Some("Stop command issued.".to_string()),
            Err(e) => self.status_msg = Some(format!("Error: {}", e)),
        }
    }
}

fn find_repo_root() -> Result<PathBuf> {
    let mut curr = std::env::current_dir()?;
    loop {
        if curr.join("lgwks").exists() && curr.join(".git").exists() {
            return Ok(curr);
        }
        if let Some(parent) = curr.parent() {
            curr = parent.to_path_buf();
        } else {
            return Err(eyre!("Could not find lgwks root. Are you in the repo?"));
        }
    }
}

fn main() -> Result<()> {
    color_eyre::install()?;
    
    let repo_root = find_repo_root().wrap_err("TUI must be started within or below the logicalworks- repository.")?;
    let db = Db::new(&repo_root);
    
    execute!(std::io::stdout(), EnableMouseCapture)?;
    let mut terminal = ratatui::init();
    
    let app = App::new(repo_root);
    let result = run_app(&mut terminal, app, db);
    
    ratatui::restore();
    execute!(std::io::stdout(), DisableMouseCapture)?;
    result
}

fn run_app(terminal: &mut DefaultTerminal, mut app: App, db: Db) -> Result<()> {
    let tick_rate = Duration::from_millis(250);
    loop {
        app.update_data(&db);
        terminal.draw(|f| ui(f, &app))?;

        let timeout = tick_rate
            .checked_sub(app.last_tick.elapsed())
            .unwrap_or_else(|| Duration::from_secs(0));

        if event::poll(timeout)? {
            let event = event::read()?;
            match event {
                Event::Key(key) => {
                    if key.kind == KeyEventKind::Press {
                        match app.mode {
                            Mode::Normal => match key.code {
                                KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
                                KeyCode::Char('j') | KeyCode::Down => {
                                    let i = match app.workflow_list_state.selected() {
                                        Some(i) => {
                                            if i >= app.workflows.len().saturating_sub(1) { 0 } else { i + 1 }
                                        }
                                        None => 0,
                                    };
                                    app.workflow_list_state.select(Some(i));
                                    let mut names: Vec<_> = app.workflows.keys().cloned().collect();
                                    names.sort();
                                    if !names.is_empty() {
                                        app.selected_workflow = Some(names[i].clone());
                                    }
                                }
                                KeyCode::Char('k') | KeyCode::Up => {
                                    let i = match app.workflow_list_state.selected() {
                                        Some(i) => {
                                            if i == 0 { app.workflows.len().saturating_sub(1) } else { i - 1 }
                                        }
                                        None => 0,
                                    };
                                    app.workflow_list_state.select(Some(i));
                                    let mut names: Vec<_> = app.workflows.keys().cloned().collect();
                                    names.sort();
                                    if !names.is_empty() {
                                        app.selected_workflow = Some(names[i].clone());
                                    }
                                }
                                KeyCode::Char('i') => {
                                    if app.selected_workflow.is_some() {
                                        app.mode = Mode::Insert;
                                    }
                                }
                                KeyCode::Enter => {
                                    if app.selected_workflow.is_some() {
                                        app.execute_workflow(&db);
                                    }
                                }
                                KeyCode::Char('s') => app.start_daemon(&db),
                                KeyCode::Char('x') => app.stop_daemon(&db),
                                _ => {}
                            },
                            Mode::Insert => match key.code {
                                KeyCode::Esc => app.mode = Mode::Normal,
                                KeyCode::Enter => app.execute_workflow(&db),
                                _ => {
                                    app.form_input.handle_event(&Event::Key(key));
                                }
                            }
                        }
                    }
                }
                Event::Mouse(mouse) => {
                    if mouse.kind == MouseEventKind::Down(MouseButton::Left) {
                        // Mouse interaction handling
                        if mouse.row <= 3 {
                            // Header interactions
                        }
                    }
                }
                _ => {}
            }
        }

        if app.last_tick.elapsed() >= tick_rate {
            app.last_tick = Instant::now();
        }

        if app.should_quit {
            break;
        }
    }
    Ok(())
}

// ── Palette matching lgwks_ui.py ───────────────────────────────────────────
const SLATE: Color = Color::Indexed(67);
const SLATE_DIM: Color = Color::Indexed(60);
const CREAM: Color = Color::Indexed(230);
const CREAM_DIM: Color = Color::Indexed(187);
const EMERALD: Color = Color::Indexed(78);
const EMERALD_DIM: Color = Color::Indexed(36);
const AMBER: Color = Color::Indexed(179);
const MUTED: Color = Color::Indexed(245);

fn ui(f: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Header
            Constraint::Min(0),    // Main Content (3 cols)
            Constraint::Length(1), // Footer
        ])
        .split(f.area());

    render_header(f, chunks[0], app);
    
    let main_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(20), // Left: Workflows
            Constraint::Percentage(50), // Center: Active View
            Constraint::Percentage(30), // Right: Events
        ])
        .split(chunks[1]);

    render_workflow_sidebar(f, main_chunks[0], app);
    render_main_area(f, main_chunks[1], app);
    render_event_sidebar(f, main_chunks[2], app);
    
    render_footer(f, chunks[2], app);
}

fn render_header(f: &mut Frame, area: Rect, app: &App) {
    let header_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(30), // Logo + Repo
            Constraint::Min(0),    // Stats
            Constraint::Length(40), // Daemon Status
        ])
        .split(area);

    let logo = Paragraph::new(Line::from(vec![
        Span::styled("◇◈◆✦ ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("LGWKS ", Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
        Span::styled(format!("({})", app.repo_root.file_name().unwrap_or_default().to_string_lossy()), Style::default().fg(SLATE_DIM)),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(logo, header_chunks[0]);

    let stats = Paragraph::new(Line::from(vec![
        Span::styled(" MEM: ", Style::default().fg(SLATE_DIM)),
        Span::styled("142MB", Style::default().fg(CREAM_DIM)),
        Span::styled("  QUEUE: ", Style::default().fg(SLATE_DIM)),
        Span::styled(format!("{}", app.queue.len()), Style::default().fg(EMERALD)),
        Span::styled("  MODULES: ", Style::default().fg(SLATE_DIM)),
        Span::styled(format!("{}", app.nav_modules.len()), Style::default().fg(CREAM_DIM)),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(stats, header_chunks[1]);

    let status_color = if app.status.alive { EMERALD } else { AMBER };
    let pid_str = app.status.pid.map(|p| p.to_string()).unwrap_or_else(|| "---".to_string());
    
    let daemon_status = Paragraph::new(Line::from(vec![
        Span::styled("DAEMON: ", Style::default().fg(SLATE_DIM)),
        Span::styled(app.status.status.to_uppercase(), Style::default().fg(status_color)),
        Span::styled("  PID: ", Style::default().fg(SLATE_DIM)),
        Span::styled(pid_str, Style::default().fg(CREAM_DIM)),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(daemon_status, header_chunks[2]);
}

fn render_workflow_sidebar(f: &mut Frame, area: Rect, app: &App) {
    let mut names: Vec<_> = app.workflows.keys().cloned().collect();
    names.sort();
    
    let items: Vec<ListItem> = names.iter().map(|name| {
        ListItem::new(Line::from(vec![
            Span::styled(" ▸ ", Style::default().fg(SLATE_DIM)),
            Span::styled(name, Style::default().fg(CREAM)),
        ]))
    }).collect();

    let list = List::new(items)
        .block(Block::default().title(" WORKFLOWS ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)).title_style(Style::default().fg(EMERALD_DIM)))
        .highlight_style(Style::default().bg(SLATE_DIM).fg(CREAM).add_modifier(Modifier::BOLD))
        .highlight_symbol(">> ");
    
    let mut state = app.workflow_list_state.clone();
    f.render_stateful_widget(list, area, &mut state);
}

fn render_main_area(f: &mut Frame, area: Rect, app: &App) {
    if let Some(ref wf_name) = app.selected_workflow {
        if let Some(wf) = app.workflows.get(wf_name) {
            let chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(4), // Description
                    Constraint::Length(3), // Input
                    Constraint::Min(0),    // Verbs/Details
                ])
                .split(area);

            let desc = Paragraph::new(format!("\n  {}\n  Budget: {}", wf.description, wf.tokens))
                .block(Block::default().title(format!(" {} ", wf_name.to_uppercase())).borders(Borders::ALL).border_style(Style::default().fg(EMERALD)))
                .style(Style::default().fg(CREAM_DIM));
            f.render_widget(desc, chunks[0]);

            let input_style = if app.mode == Mode::Insert { Style::default().fg(EMERALD) } else { Style::default().fg(CREAM_DIM) };
            let input = Paragraph::new(app.form_input.value())
                .block(Block::default().borders(Borders::ALL).title(" Arguments / Query ").border_style(input_style))
                .style(Style::default().fg(CREAM));
            f.render_widget(input, chunks[1]);

            if app.mode == Mode::Insert {
                f.set_cursor_position((
                    chunks[1].x + app.form_input.visual_cursor() as u16 + 1,
                    chunks[1].y + 1,
                ));
            }

            let verbs: Vec<ListItem> = wf.verbs.iter().map(|v| ListItem::new(format!("  • {}", v))).collect();
            let details = List::new(verbs)
                .block(Block::default().title(" VERB CHAIN ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
                .style(Style::default().fg(SLATE_DIM));
            f.render_widget(details, chunks[2]);
        }
    } else {
        let welcome = Paragraph::new("\n\n  Select a workflow from the left sidebar\n  to begin research or system operations.\n\n  Press 's' to start daemon\n  Press 'x' to stop daemon")
            .block(Block::default().title(" DASHBOARD ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
            .style(Style::default().fg(CREAM_DIM));
        f.render_widget(welcome, area);
    }
}

fn render_event_sidebar(f: &mut Frame, area: Rect, app: &App) {
    let items: Vec<ListItem> = app.events.iter().take(20).map(|e| {
        let color = match e.lane.as_str() {
            "ingress" => CREAM,
            "workflow" => EMERALD,
            "control" => AMBER,
            _ => SLATE_DIM,
        };
        ListItem::new(vec![
            Line::from(vec![
                Span::styled(format!("{} ", e.ts.chars().skip(11).take(8).collect::<String>()), Style::default().fg(SLATE_DIM)),
                Span::styled(&e.kind, Style::default().fg(color)),
            ]),
            Line::from(vec![
                Span::styled(format!("  {}", e.payload), Style::default().fg(MUTED)),
            ]),
        ])
    }).collect();

    let list = List::new(items)
        .block(Block::default().title(" LIVE EVENTS ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)).title_style(Style::default().fg(EMERALD_DIM)));
    f.render_widget(list, area);
}

fn render_footer(f: &mut Frame, area: Rect, app: &App) {
    let mode_str = match app.mode {
        Mode::Normal => " NORMAL ",
        Mode::Insert => " INSERT ",
    };
    let mode_color = match app.mode {
        Mode::Normal => SLATE,
        Mode::Insert => EMERALD,
    };

    let msg = app.status_msg.as_deref().unwrap_or("Ready.");

    let footer_text = Line::from(vec![
        Span::styled(mode_str, Style::default().bg(mode_color).fg(Color::Black).add_modifier(Modifier::BOLD)),
        Span::styled(format!("  {}  ", msg), Style::default().fg(CREAM)),
        Span::styled(" Q ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("quit  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" J/K ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("nav  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" I ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("input  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" ENTER ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("run  ", Style::default().fg(CREAM_DIM)),
    ]);
    f.render_widget(Paragraph::new(footer_text).style(Style::default().bg(SLATE_DIM).fg(CREAM)), area);
}
