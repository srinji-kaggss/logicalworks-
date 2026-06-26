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
    widgets::{Block, Borders, Paragraph, ListItem, List, Gauge},
    DefaultTerminal, Frame,
};
use std::time::{Duration, Instant};
use std::process::Command;
use std::path::{Path, PathBuf};
use std::collections::HashMap;
use tui_input::Input;
use tui_input::backend::crossterm::EventHandler;
use crate::models::{DaemonEvent, WorkItem, DaemonStatus, NavModule, WorkflowDef, HarvestMetrics, ModelCatalog};
use crate::db::Db;

use clap::Parser;

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Path to the repository root
    #[arg(short, long)]
    repo: Option<PathBuf>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    Normal,
    Insert,
    Setup,
    Models,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Tab {
    Dashboard,
    Harvest,
}

struct App {
    should_quit: bool,
    last_tick: Instant,
    repo_root: Option<PathBuf>,
    script_path: Option<PathBuf>,
    status: DaemonStatus,
    events: Vec<DaemonEvent>,
    queue: Vec<WorkItem>,
    nav_modules: Vec<(String, NavModule)>,
    workflows: HashMap<String, WorkflowDef>,
    selected_workflow: Option<String>,
    workflow_list_state: ratatui::widgets::ListState,
    form_input: Input,
    repo_input: Input,
    mode: Mode,
    selected_tab: Tab,
    status_msg: Option<String>,
    thoughts: Vec<serde_json::Value>,
    harvest: Option<HarvestMetrics>,
    terminal_output: Vec<String>,
    model_catalog: Option<ModelCatalog>,
    model_list_state: ratatui::widgets::ListState,
}

impl App {
    fn new(repo_root: Option<PathBuf>) -> Self {
        let mode = if repo_root.is_some() { Mode::Normal } else { Mode::Setup };
        let script_path = repo_root.as_ref().map(|r| r.join("lgwks"));
        Self {
            should_quit: false,
            last_tick: Instant::now(),
            repo_root: repo_root.clone(),
            script_path,
            status: DaemonStatus {
                pid: None,
                status: "unknown".to_string(),
                repo_root: repo_root.as_ref().map(|r| r.to_string_lossy().to_string()).unwrap_or_default(),
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
            repo_input: Input::default().with_value(std::env::current_dir().unwrap_or_default().to_string_lossy().to_string()),
            mode,
            selected_tab: Tab::Dashboard,
            status_msg: None,
            thoughts: Vec::new(),
            harvest: None,
            terminal_output: Vec::new(),
            model_catalog: None,
            model_list_state: ratatui::widgets::ListState::default(),
        }
    }

    /// Pull the unified two-plane catalog from the Python selector (projection only).
    fn load_model_catalog(&mut self, db: &Option<Db>) {
        if let Some(db) = db {
            match db.get_model_catalog() {
                Ok(c) => {
                    if self.model_list_state.selected().is_none() && !c.local.is_empty() {
                        self.model_list_state.select(Some(0));
                    }
                    self.model_catalog = Some(c);
                }
                Err(e) => self.status_msg = Some(format!("models list failed: {}", e)),
            }
        }
    }

    /// Write the active plane back through the selector (`lgwks models locality`).
    fn set_model_locality(&mut self, db: &Option<Db>, locality: &str) {
        let (script_path, repo_root) = match (&self.script_path, &self.repo_root) {
            (Some(s), Some(r)) => (s.clone(), r.clone()),
            _ => return,
        };
        let py = self.get_python_cmd();
        let _ = Command::new(py)
            .args([script_path.to_str().unwrap_or("lgwks"), "models", "locality", locality])
            .current_dir(&repo_root)
            .output();
        self.status_msg = Some(format!("Locality → {}", locality));
        self.load_model_catalog(db);
    }

    /// Persist the highlighted local model for its role (`lgwks models use`).
    fn select_model(&mut self, db: &Option<Db>) {
        let chosen = self.model_catalog.as_ref().and_then(|c| {
            self.model_list_state.selected().and_then(|i| c.local.get(i))
        }).map(|m| (m.law_name.clone(), m.role.clone()));
        if let Some((law_name, role)) = chosen {
            let (script_path, repo_root) = match (&self.script_path, &self.repo_root) {
                (Some(s), Some(r)) => (s.clone(), r.clone()),
                _ => return,
            };
            let py = self.get_python_cmd();
            let _ = Command::new(py)
                .args([script_path.to_str().unwrap_or("lgwks"), "models", "use",
                       &law_name, "--role", &role, "--locality", "local"])
                .current_dir(&repo_root)
                .output();
            self.status_msg = Some(format!("Selected {} for role {}", law_name, role));
            self.load_model_catalog(db);
        }
    }

    fn model_cursor_move(&mut self, delta: i32) {
        let n = self.model_catalog.as_ref().map(|c| c.local.len()).unwrap_or(0);
        if n == 0 { return; }
        let cur = self.model_list_state.selected().unwrap_or(0) as i32;
        let next = (cur + delta).rem_euclid(n as i32) as usize;
        self.model_list_state.select(Some(next));
    }

    fn set_repo_root(&mut self, root: PathBuf) {
        self.repo_root = Some(root.clone());
        self.script_path = Some(root.join("lgwks"));
        self.status.repo_root = root.to_string_lossy().to_string();
        self.mode = Mode::Normal;
        self.status_msg = Some("Repository detected.".to_string());
    }

    fn get_python_cmd(&self) -> String {
        if let Some(ref root) = self.repo_root {
            let venv_python = root.join(".venv").join("bin").join("python");
            if venv_python.exists() {
                return venv_python.to_string_lossy().to_string();
            }
        }
        "python3".to_string()
    }

    fn update_data(&mut self, db: &Option<Db>) {
        if let Some(db) = db {
            if let Ok(status) = db.get_status() {
                self.status = status;
            }
            if let Ok(events) = db.get_events(50) {
                self.events = events;
            }
            if let Ok(queue) = db.get_queue(20) {
                self.queue = queue;
            }
            if let Ok(thoughts) = db.get_thoughts(20) {
                self.thoughts = thoughts;
            }
            if let Ok(harvest) = db.get_harvest_metrics() {
                self.harvest = Some(harvest);
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
    }

    fn execute_workflow(&mut self, db: &Option<Db>) {
        if let (Some(ref wf_name), Some(script_path), Some(repo_root)) = (&self.selected_workflow, &self.script_path, &self.repo_root) {
            let input_val = self.form_input.value().to_string();
            self.status_msg = Some(format!("Executing {}...", wf_name));
            self.terminal_output.clear();
            
            let mut args = vec![script_path.to_str().unwrap_or("lgwks"), "workflow", wf_name];
            if !input_val.is_empty() {
                args.push(&input_val);
            }

            if let Some(db) = db {
                let _ = db.emit_telemetry("control", "workflow_event", "human_message", &format!("Triggered workflow: {}", wf_name));
            }

            let output = Command::new(self.get_python_cmd())
                .args(&args)
                .current_dir(repo_root)
                .output();

            match output {
                Ok(out) => {
                    let stdout = String::from_utf8_lossy(&out.stdout);
                    let stderr = String::from_utf8_lossy(&out.stderr);
                    for line in stdout.lines().chain(stderr.lines()) {
                        self.terminal_output.push(line.to_string());
                    }
                    if out.status.success() {
                        self.status_msg = Some(format!("Workflow {} completed.", wf_name));
                    } else {
                        self.status_msg = Some(format!("Error: Process exited with code {}", out.status));
                    }
                }
                Err(e) => {
                    self.status_msg = Some(format!("Error: Failed to execute: {}", e));
                    self.terminal_output.push(format!("Internal Error: {}", e));
                }
            }
            self.mode = Mode::Normal;
        }
    }

    fn start_daemon(&mut self, db: &Option<Db>) {
        if let (Some(script_path), Some(repo_root)) = (&self.script_path, &self.repo_root) {
            self.status_msg = Some("Starting daemon...".to_string());
            if let Some(db) = db {
                let _ = db.emit_telemetry("control", "human_message", "daemon_start", "Starting daemon via TUI");
            }
            
            let output = Command::new(self.get_python_cmd())
                .args([script_path.to_str().unwrap_or("lgwks"), "daemon", "start"])
                .current_dir(repo_root)
                .output();

            match output {
                Ok(out) => {
                    if out.status.success() {
                        self.status_msg = Some("Daemon started successfully.".to_string());
                    } else {
                        let stderr = String::from_utf8_lossy(&out.stderr);
                        self.status_msg = Some(format!("Error starting daemon."));
                        self.terminal_output.push(stderr.to_string());
                    }
                }
                Err(e) => {
                    self.status_msg = Some(format!("Error: Failed to execute: {}", e));
                }
            }
        }
    }

    fn stop_daemon(&mut self, db: &Option<Db>) {
        if let (Some(script_path), Some(repo_root)) = (&self.script_path, &self.repo_root) {
            self.status_msg = Some("Stopping daemon...".to_string());
            if let Some(db) = db {
                let _ = db.emit_telemetry("control", "human_message", "daemon_stop", "Stopping daemon via TUI");
            }
            
            let output = Command::new(self.get_python_cmd())
                .args([script_path.to_str().unwrap_or("lgwks"), "daemon", "stop"])
                .current_dir(repo_root)
                .output();

            match output {
                Ok(out) => {
                    if out.status.success() {
                        self.status_msg = Some("Stop command issued.".to_string());
                    } else {
                        self.status_msg = Some("Error stopping daemon.".to_string());
                    }
                }
                Err(e) => self.status_msg = Some(format!("Error: {}", e)),
            }
        }
    }
}

fn find_repo_root() -> Option<PathBuf> {
    let mut curr = std::env::current_dir().ok()?;
    loop {
        if curr.join("lgwks").exists() && curr.join(".git").exists() {
            return Some(curr);
        }
        if let Some(parent) = curr.parent() {
            curr = parent.to_path_buf();
        } else {
            return None;
        }
    }
}

fn main() -> Result<()> {
    color_eyre::install()?;
    let args = Args::parse();
    
    let repo_root = args.repo.or_else(find_repo_root);
    let mut db = repo_root.as_ref().map(|r| Db::new(r.as_path()));
    
    execute!(std::io::stdout(), EnableMouseCapture)?;
    let mut terminal = ratatui::init();
    
    let app = App::new(repo_root);
    let result = run_app(&mut terminal, app, &mut db);
    
    ratatui::restore();
    execute!(std::io::stdout(), DisableMouseCapture)?;
    result
}

fn run_app(terminal: &mut DefaultTerminal, mut app: App, db: &mut Option<Db>) -> Result<()> {
    let tick_rate = Duration::from_millis(250);
    loop {
        app.update_data(db);
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
                                KeyCode::Tab => {
                                    app.selected_tab = match app.selected_tab {
                                        Tab::Dashboard => Tab::Harvest,
                                        Tab::Harvest => Tab::Dashboard,
                                    };
                                }
                                KeyCode::Char('j') | KeyCode::Down => {
                                    if !app.workflows.is_empty() {
                                        let i = match app.workflow_list_state.selected() {
                                            Some(i) => {
                                                if i >= app.workflows.len().saturating_sub(1) { 0 } else { i + 1 }
                                            }
                                            None => 0,
                                        };
                                        app.workflow_list_state.select(Some(i));
                                        let mut names: Vec<_> = app.workflows.keys().cloned().collect();
                                        names.sort();
                                        app.selected_workflow = Some(names[i].clone());
                                    }
                                }
                                KeyCode::Char('k') | KeyCode::Up => {
                                    if !app.workflows.is_empty() {
                                        let i = match app.workflow_list_state.selected() {
                                            Some(i) => {
                                                if i == 0 { app.workflows.len().saturating_sub(1) } else { i - 1 }
                                            }
                                            None => 0,
                                        };
                                        app.workflow_list_state.select(Some(i));
                                        let mut names: Vec<_> = app.workflows.keys().cloned().collect();
                                        names.sort();
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
                                        app.execute_workflow(db);
                                    }
                                }
                                KeyCode::Char('s') => app.start_daemon(db),
                                KeyCode::Char('x') => app.stop_daemon(db),
                                KeyCode::Char('r') => app.mode = Mode::Setup,
                                KeyCode::Char('m') => {
                                    app.mode = Mode::Models;
                                    app.load_model_catalog(db);
                                }
                                _ => {}
                            },
                            Mode::Models => match key.code {
                                KeyCode::Esc | KeyCode::Char('q') => app.mode = Mode::Normal,
                                KeyCode::Char('j') | KeyCode::Down => app.model_cursor_move(1),
                                KeyCode::Char('k') | KeyCode::Up => app.model_cursor_move(-1),
                                KeyCode::Char('l') => app.set_model_locality(db, "local"),
                                KeyCode::Char('c') => app.set_model_locality(db, "cloud"),
                                KeyCode::Enter => app.select_model(db),
                                _ => {}
                            },
                            Mode::Insert => match key.code {
                                KeyCode::Esc => app.mode = Mode::Normal,
                                KeyCode::Enter => app.execute_workflow(db),
                                _ => {
                                    app.form_input.handle_event(&Event::Key(key));
                                }
                            },
                            Mode::Setup => match key.code {
                                KeyCode::Esc => {
                                    if app.repo_root.is_some() { app.mode = Mode::Normal; }
                                    else { app.should_quit = true; }
                                }
                                KeyCode::Enter => {
                                    let path = PathBuf::from(app.repo_input.value());
                                    if path.exists() && path.join("lgwks").exists() {
                                        *db = Some(Db::new(&path));
                                        app.set_repo_root(path);
                                    } else {
                                        app.status_msg = Some("Error: Not a valid Logical Works repo root.".to_string());
                                    }
                                }
                                _ => {
                                    app.repo_input.handle_event(&Event::Key(key));
                                }
                            }
                        }
                    }
                }
                Event::Mouse(mouse) => {
                    if mouse.kind == MouseEventKind::Down(MouseButton::Left) {
                        // Mouse interaction handling
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
            Constraint::Min(0),    // Main Content
            Constraint::Length(1), // Footer
        ])
        .split(f.area());

    render_header(f, chunks[0], app);
    
    match app.selected_tab {
        Tab::Dashboard => {
            let main_chunks = Layout::default()
                .direction(Direction::Horizontal)
                .constraints([
                    Constraint::Percentage(20), // Left: Workflows
                    Constraint::Percentage(40), // Center: Active View
                    Constraint::Percentage(20), // Center-Right: Thoughts
                    Constraint::Percentage(20), // Right: Events
                ])
                .split(chunks[1]);

            render_workflow_sidebar(f, main_chunks[0], app);
            render_main_area(f, main_chunks[1], app);
            render_thought_sidebar(f, main_chunks[2], app);
            render_event_sidebar(f, main_chunks[3], app);
        }
        Tab::Harvest => {
            render_harvest_monitor(f, chunks[1], app);
        }
    }
    
    render_footer(f, chunks[2], app);
}

fn render_header(f: &mut Frame, area: Rect, app: &App) {
    let header_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(35), // Logo + Repo
            Constraint::Min(0),    // Tabs
            Constraint::Length(40), // Daemon Status
        ])
        .split(area);

    let repo_name = app.repo_root.as_ref()
        .map(|r| r.file_name().unwrap_or_default().to_string_lossy().to_string())
        .unwrap_or_else(|| "NO REPO".to_string());

    let logo = Paragraph::new(Line::from(vec![
        Span::styled("◇◈◆✦ ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("LGWKS ", Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
        Span::styled(format!("({})", repo_name), Style::default().fg(SLATE_DIM)),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(logo, header_chunks[0]);

    let dash_style = if app.selected_tab == Tab::Dashboard { Style::default().fg(EMERALD).add_modifier(Modifier::BOLD) } else { Style::default().fg(SLATE_DIM) };
    let harv_style = if app.selected_tab == Tab::Harvest { Style::default().fg(EMERALD).add_modifier(Modifier::BOLD) } else { Style::default().fg(SLATE_DIM) };

    let tabs = Paragraph::new(Line::from(vec![
        Span::styled("  [1] DASHBOARD  ", dash_style),
        Span::styled("  [2] HARVEST MONITOR  ", harv_style),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(tabs, header_chunks[1]);

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

fn render_models_screen(f: &mut Frame, area: Rect, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(3), Constraint::Length(9)])
        .margin(1)
        .split(area);

    let (active, default_loc) = app.model_catalog.as_ref()
        .map(|c| (c.active_locality.clone(), c.default_locality.clone()))
        .unwrap_or_else(|| ("?".into(), "local".into()));
    let active_color = if active == "cloud" { AMBER } else { EMERALD };
    let header = Paragraph::new(Line::from(vec![
        Span::styled("◆ MODEL SELECTOR   ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled(format!("active: {}   ", active), Style::default().fg(active_color).add_modifier(Modifier::BOLD)),
        Span::styled(format!("(default: {})", default_loc), Style::default().fg(MUTED)),
    ])).block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(header, chunks[0]);

    // LOCAL plane — the selectable Model Mesh (privacy-first default)
    let items: Vec<ListItem> = app.model_catalog.as_ref().map(|c| {
        c.local.iter().map(|m| {
            let tier = m.trust_class.clone().unwrap_or_default();
            ListItem::new(Line::from(vec![
                Span::styled(format!("{:<10}", m.role), Style::default().fg(EMERALD_DIM)),
                Span::styled(m.law_name.clone(), Style::default().fg(CREAM)),
                Span::styled(format!("  → {}", m.runtime_id), Style::default().fg(MUTED)),
                Span::styled(if tier.is_empty() { String::new() } else { format!("  [{}]", tier) },
                             Style::default().fg(SLATE)),
            ]))
        }).collect()
    }).unwrap_or_default();
    let list = List::new(items)
        .block(Block::default()
            .title(" LOCAL · Model Mesh (default, private) ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(EMERALD_DIM))
            .title_style(Style::default().fg(EMERALD)))
        .highlight_style(Style::default().bg(SLATE_DIM).fg(CREAM).add_modifier(Modifier::BOLD))
        .highlight_symbol(">> ");
    let mut st = app.model_list_state.clone();
    f.render_stateful_widget(list, chunks[1], &mut st);

    // CLOUD plane — models.dev, explicitly opt-in, offline-safe
    let mut cloud_lines: Vec<Line> = Vec::new();
    if let Some(c) = app.model_catalog.as_ref() {
        let suffix = if c.cloud.degraded { "  (offline — cached/unavailable)" } else { "" };
        let gate = if c.cloud.opt_in { "opt-in" } else { "enabled" };
        cloud_lines.push(Line::from(Span::styled(
            format!("{} · {} providers{}", gate, c.cloud.providers.len(), suffix),
            Style::default().fg(AMBER).add_modifier(Modifier::BOLD))));
        for p in c.cloud.providers.iter().take(5) {
            cloud_lines.push(Line::from(Span::styled(
                format!("  {}  ({} models)", p.id, p.models), Style::default().fg(CREAM_DIM))));
        }
        cloud_lines.push(Line::from(Span::styled(
            "  [c] switch to cloud   [l] back to local   [Enter] pick local model   [Esc] back",
            Style::default().fg(MUTED))));
    }
    let cloud = Paragraph::new(cloud_lines)
        .block(Block::default()
            .title(" CLOUD · models.dev (opt-in) ")
            .borders(Borders::ALL)
            .border_style(Style::default().fg(AMBER))
            .title_style(Style::default().fg(AMBER)));
    f.render_widget(cloud, chunks[2]);
}

fn render_main_area(f: &mut Frame, area: Rect, app: &App) {
    if app.mode == Mode::Models {
        render_models_screen(f, area, app);
        return;
    }
    if app.mode == Mode::Setup {
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(3), // Title
                Constraint::Length(3), // Input
                Constraint::Min(0),    // Instructions
            ])
            .margin(2)
            .split(area);

        let title = Paragraph::new(Line::from(vec![
            Span::styled("◆ CONFIGURE REPOSITORY ROOT", Style::default().fg(AMBER).add_modifier(Modifier::BOLD)),
        ]));
        f.render_widget(title, chunks[0]);

        let input = Paragraph::new(app.repo_input.value())
            .block(Block::default().borders(Borders::ALL).title(" Path to Logical Works repo ").border_style(Style::default().fg(AMBER)))
            .style(Style::default().fg(CREAM));
        f.render_widget(input, chunks[1]);

        f.set_cursor_position((
            chunks[1].x + app.repo_input.visual_cursor() as u16 + 1,
            chunks[1].y + 1,
        ));

        let help = Paragraph::new("\n  Type the absolute path to your Logical Works folder.\n  It must contain both '.git/' and the 'lgwks' script.\n\n  [ENTER] Confirm and Load\n  [ESC]   Cancel / Quit")
            .style(Style::default().fg(CREAM_DIM));
        f.render_widget(help, chunks[2]);
        return;
    }

    if app.repo_root.is_none() {
        let error = Paragraph::new("\n\n  ❌ NO REPOSITORY DETECTED\n\n  Press 'R' to configure manually.")
            .block(Block::default().title(" ERROR ").borders(Borders::ALL).border_style(Style::default().fg(AMBER)))
            .style(Style::default().fg(CREAM_DIM));
        f.render_widget(error, area);
        return;
    }

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4), // Header/Selected Workflow
            Constraint::Length(3), // Input
            Constraint::Min(0),    // Output/Details
        ])
        .split(area);

    if let Some(ref wf_name) = app.selected_workflow {
        if let Some(wf) = app.workflows.get(wf_name) {
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

            if !app.terminal_output.is_empty() {
                let items: Vec<ListItem> = app.terminal_output.iter().map(|line| {
                    ListItem::new(Line::from(vec![
                        Span::styled(line, Style::default().fg(CREAM_DIM)),
                    ]))
                }).collect();
                let output = List::new(items)
                    .block(Block::default().title(" PROCESS OUTPUT ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
                    .style(Style::default().fg(SLATE_DIM));
                f.render_widget(output, chunks[2]);
            } else {
                let verbs: Vec<ListItem> = wf.verbs.iter().map(|v| ListItem::new(format!("  • {}", v))).collect();
                let details = List::new(verbs)
                    .block(Block::default().title(" VERB CHAIN ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
                    .style(Style::default().fg(SLATE_DIM));
                f.render_widget(details, chunks[2]);
            }
        }
    } else {
        let welcome = Paragraph::new("\n\n  Select a workflow from the left sidebar\n  to begin research or system operations.\n\n  Press 'S' to start daemon\n  Press 'X' to stop daemon\n  Press 'R' to switch repository")
            .block(Block::default().title(" DASHBOARD ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
            .style(Style::default().fg(CREAM_DIM));
        f.render_widget(welcome, area);
    }
}

fn render_harvest_monitor(f: &mut Frame, area: Rect, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(10), // Progress Gauges
            Constraint::Min(0),     // Stream Status
        ])
        .margin(2)
        .split(area);

    if let Some(ref h) = app.harvest {
        let progress = (h.turns_collected as f64 / h.goal as f64).min(1.0);
        let gauge = Gauge::default()
            .block(Block::default().title(" TOTAL TRAJECTORY HARVEST (1M TURN GOAL) ").borders(Borders::ALL).border_style(Style::default().fg(EMERALD)))
            .gauge_style(Style::default().fg(EMERALD).bg(SLATE_DIM).add_modifier(Modifier::BOLD))
            .percent((progress * 100.0) as u16)
            .label(format!("{}/{}", h.turns_collected, h.goal));
        f.render_widget(gauge, chunks[0]);

        let inner_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Percentage(33),
                Constraint::Percentage(33),
                Constraint::Percentage(34),
            ])
            .split(Rect::new(chunks[0].x, chunks[0].y + 4, chunks[0].width, 4));

        let c_gauge = Gauge::default()
            .block(Block::default().title(" COVERAGE (C) ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
            .gauge_style(Style::default().fg(CREAM).bg(SLATE_DIM))
            .percent((h.coverage * 100.0) as u16);
        f.render_widget(c_gauge, inner_chunks[0]);

        let g_gauge = Gauge::default()
            .block(Block::default().title(" GAP (G) ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
            .gauge_style(Style::default().fg(AMBER).bg(SLATE_DIM))
            .percent((h.gap * 100.0) as u16);
        f.render_widget(g_gauge, inner_chunks[1]);

        let p_gauge = Gauge::default()
            .block(Block::default().title(" CONFIDENCE (P) ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)))
            .gauge_style(Style::default().fg(EMERALD).bg(SLATE_DIM))
            .percent((h.confidence * 100.0) as u16);
        f.render_widget(p_gauge, inner_chunks[2]);

        let items: Vec<ListItem> = h.streams.iter().map(|s| {
            ListItem::new(Line::from(vec![
                Span::styled(" ● ", Style::default().fg(EMERALD)),
                Span::styled(s, Style::default().fg(CREAM)),
                Span::styled(" [TAILING]", Style::default().fg(SLATE_DIM)),
            ]))
        }).collect();

        let list = List::new(items)
            .block(Block::default().title(" VITAL STREAMS ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)));
        f.render_widget(list, chunks[1]);
    } else {
        let loading = Paragraph::new("\n\n  Waiting for Subconscious Engine metrics...")
            .style(Style::default().fg(SLATE_DIM));
        f.render_widget(loading, area);
    }
}

fn render_thought_sidebar(f: &mut Frame, area: Rect, app: &App) {
    let items: Vec<ListItem> = app.thoughts.iter().map(|t| {
        let kind = t.get("kind").and_then(|v| v.as_str()).unwrap_or("thought");
        let color = match kind {
            "thought" => CREAM_DIM,
            "intent_commit" => EMERALD,
            "promotion" => EMERALD_DIM,
            _ => SLATE_DIM,
        };
        let data = t.get("data").cloned().unwrap_or(serde_json::json!({}));
        let summary = match kind {
            "thought" => data.get("chamber").and_then(|v| v.as_str()).unwrap_or("think"),
            "intent_commit" => "COMMIT",
            "promotion" => "ANCHOR",
            _ => kind,
        };
        
        ListItem::new(vec![
            Line::from(vec![
                Span::styled(format!("{} ", summary.to_uppercase()), Style::default().fg(color).add_modifier(Modifier::BOLD)),
                Span::styled(format!("{}", data), Style::default().fg(MUTED)),
            ]),
        ])
    }).collect();

    let list = List::new(items)
        .block(Block::default().title(" AETHERIUS THOUGHTS ").borders(Borders::ALL).border_style(Style::default().fg(SLATE_DIM)).title_style(Style::default().fg(EMERALD_DIM)));
    f.render_widget(list, area);
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
        Mode::Setup => " SETUP ",
        Mode::Models => " MODELS ",
    };
    let mode_color = match app.mode {
        Mode::Normal => SLATE,
        Mode::Insert => EMERALD,
        Mode::Setup => AMBER,
        Mode::Models => EMERALD,
    };

    let msg = app.status_msg.as_deref().unwrap_or("Ready.");

    let footer_text = Line::from(vec![
        Span::styled(mode_str, Style::default().bg(mode_color).fg(Color::Black).add_modifier(Modifier::BOLD)),
        Span::styled(format!("  {}  ", msg), Style::default().fg(CREAM)),
        Span::styled(" Q ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("quit  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" TAB ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("switch tab  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" J/K ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("nav  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" I ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("input  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" ENTER ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("run  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" M ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("models  ", Style::default().fg(CREAM_DIM)),
    ]);
    f.render_widget(Paragraph::new(footer_text).style(Style::default().bg(SLATE_DIM).fg(CREAM)), area);
}
