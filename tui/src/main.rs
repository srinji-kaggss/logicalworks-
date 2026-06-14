mod models;
mod db;

use color_eyre::Result;
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, EnableMouseCapture, DisableMouseCapture, MouseEventKind, MouseButton},
    execute,
};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Tabs, Wrap, ListItem, Table, Row, List, Clear},
    DefaultTerminal, Frame,
};
use std::time::{Duration, Instant};
use std::process::Command;
use tui_input::Input;
use tui_input::backend::crossterm::EventHandler;
use crate::models::{DaemonEvent, WorkItem, DaemonStatus, NavModule};
use crate::db::Db;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Tab {
    Dashboard,
    NavMap,
    Initialize,
    Events,
    Queue,
    Logs,
}

impl Tab {
    fn all() -> &'static [Tab] {
        &[Tab::Dashboard, Tab::NavMap, Tab::Initialize, Tab::Events, Tab::Queue, Tab::Logs]
    }

    fn to_index(self) -> usize {
        match self {
            Tab::Dashboard => 0,
            Tab::NavMap => 1,
            Tab::Initialize => 2,
            Tab::Events => 3,
            Tab::Queue => 4,
            Tab::Logs => 5,
        }
    }

    fn from_index(index: usize) -> Self {
        match index % 6 {
            0 => Tab::Dashboard,
            1 => Tab::NavMap,
            2 => Tab::Initialize,
            3 => Tab::Events,
            4 => Tab::Queue,
            5 => Tab::Logs,
            _ => unreachable!(),
        }
    }

    fn title(self) -> &'static str {
        match self {
            Tab::Dashboard => "◈ DASHBOARD",
            Tab::NavMap => "🧭 NAVMAP",
            Tab::Initialize => "⚙ INITIALIZE",
            Tab::Events => "◆ EVENTS",
            Tab::Queue => "✦ QUEUE",
            Tab::Logs => "◇ LOGS",
        }
    }
}

struct App {
    active_tab: Tab,
    should_quit: bool,
    last_tick: Instant,
    status: DaemonStatus,
    events: Vec<DaemonEvent>,
    queue: Vec<WorkItem>,
    nav_modules: Vec<(String, NavModule)>,
    init_input: Input,
    init_error: Option<String>,
}

impl App {
    fn new() -> Self {
        Self {
            active_tab: Tab::Dashboard,
            should_quit: false,
            last_tick: Instant::now(),
            status: DaemonStatus {
                pid: None,
                status: "stopped".to_string(),
                repo_root: "".to_string(),
                heartbeat_at: "".to_string(),
            },
            events: Vec::new(),
            queue: Vec::new(),
            nav_modules: Vec::new(),
            init_input: Input::default().with_value(".".to_string()),
            init_error: None,
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
        if self.nav_modules.is_empty() {
            if let Ok(navmap) = db.get_navmap() {
                let mut modules: Vec<_> = navmap.modules.into_iter().collect();
                modules.sort_by(|a, b| a.0.cmp(&b.0));
                self.nav_modules = modules;
            }
        }
    }

    fn next_tab(&mut self) {
        self.active_tab = Tab::from_index(self.active_tab.to_index() + 1);
    }

    fn prev_tab(&mut self) {
        let index = self.active_tab.to_index();
        if index == 0 {
            self.active_tab = Tab::from_index(5);
        } else {
            self.active_tab = Tab::from_index(index - 1);
        }
    }

    fn start_daemon(&mut self, db: &Db) {
        let target_dir = self.init_input.value().trim();
        // Layer 1: Entry/UI Validation
        if target_dir.is_empty() {
            self.init_error = Some("Error: Target directory cannot be empty.".to_string());
            let _ = db.emit_telemetry("terminal_output", "human_message", "validation_failed", &format!("Start daemon failed: empty target_dir"));
            return;
        }

        // Layer 2: Business Logic Validation
        if self.status.status == "running" && self.status.pid.is_some() {
            self.init_error = Some("Error: Daemon is already running.".to_string());
            let _ = db.emit_telemetry("terminal_output", "human_message", "validation_failed", "Start daemon failed: already running");
            return;
        }

        // Layer 3: Environment Guards
        let target_path = std::path::Path::new(target_dir);
        if !target_path.exists() || !target_path.join(".git").exists() {
            self.init_error = Some("Error: Target directory must be a valid git repository.".to_string());
            let _ = db.emit_telemetry("terminal_output", "human_message", "validation_failed", &format!("Start daemon failed: {} is not a git repo", target_dir));
            return;
        }

        // Layer 4: Execution & Auditing
        self.init_error = None;
        let _ = db.emit_telemetry("control", "human_message", "daemon_start", &format!("Starting daemon in {}", target_dir));
        
        let status = Command::new("python3")
            .args(["lgwks", "daemon", "start", "--repo", target_dir])
            .current_dir(target_dir)
            .status();

        match status {
            Ok(s) if s.success() => {
                self.init_error = Some("Daemon started successfully.".to_string());
            }
            Ok(s) => {
                self.init_error = Some(format!("Error: Process exited with code {}", s));
            }
            Err(e) => {
                self.init_error = Some(format!("Error: Failed to execute python3: {}", e));
            }
        }
    }
}

fn main() -> Result<()> {
    color_eyre::install()?;
    
    let repo_root = std::env::current_dir()?;
    let db = Db::new(&repo_root);
    
    execute!(std::io::stdout(), EnableMouseCapture)?;
    let mut terminal = ratatui::init();
    
    let app = App::new();
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
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    if app.active_tab == Tab::Initialize {
                        match key.code {
                            KeyCode::Esc => app.should_quit = true,
                            KeyCode::Tab => app.next_tab(),
                            KeyCode::BackTab => app.prev_tab(),
                            KeyCode::Enter => {
                                app.start_daemon(&db);
                            }
                            _ => {
                                app.init_input.handle_event(&Event::Key(key));
                            }
                        }
                    } else {
                        match key.code {
                            KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
                            KeyCode::Tab | KeyCode::Right => app.next_tab(),
                            KeyCode::Left => app.prev_tab(),
                            KeyCode::Char('1') => app.active_tab = Tab::Dashboard,
                            KeyCode::Char('2') => app.active_tab = Tab::NavMap,
                            KeyCode::Char('3') => app.active_tab = Tab::Initialize,
                            KeyCode::Char('4') => app.active_tab = Tab::Events,
                            KeyCode::Char('5') => app.active_tab = Tab::Queue,
                            KeyCode::Char('6') => app.active_tab = Tab::Logs,
                            _ => {}
                        }
                    }
                }
            } else if let Event::Mouse(mouse) = event::read()? {
                if mouse.kind == MouseEventKind::Down(MouseButton::Left) {
                    // Simple hit testing for tabs (top 3 lines)
                    if mouse.row <= 3 {
                        let tab_width = 15; // rough estimate
                        let clicked_tab = (mouse.column / tab_width) as usize;
                        if clicked_tab < 6 {
                            app.active_tab = Tab::from_index(clicked_tab);
                        }
                    }
                }
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
const RUST: Color = Color::Indexed(167);
const MUTED: Color = Color::Indexed(245);

fn ui(f: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Header
            Constraint::Min(0),    // Content
            Constraint::Length(1), // Footer
        ])
        .split(f.area());

    render_header(f, chunks[0], app);
    render_content(f, chunks[1], app);
    render_footer(f, chunks[2]);
}

fn render_header(f: &mut Frame, area: Rect, app: &App) {
    let titles = Tab::all().iter().map(|t| t.title()).collect::<Vec<_>>();
    let tabs = Tabs::new(titles)
        .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)))
        .select(app.active_tab.to_index())
        .style(Style::default().fg(CREAM_DIM))
        .highlight_style(Style::default().fg(EMERALD).add_modifier(Modifier::BOLD));
    
    let header_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(20), // Logo
            Constraint::Min(0),    // Tabs
            Constraint::Length(40), // Daemon Status
        ])
        .split(area);

    let logo = Paragraph::new(Line::from(vec![
        Span::styled("◇◈◆✦ ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("LGWKS", Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    
    f.render_widget(logo, header_chunks[0]);
    f.render_widget(tabs, header_chunks[1]);

    let status_color = if app.status.status == "running" { EMERALD } else { AMBER };
    let pid_str = app.status.pid.map(|p| p.to_string()).unwrap_or_else(|| "---".to_string());
    
    let daemon_status = Paragraph::new(Line::from(vec![
        Span::styled("DAEMON: ", Style::default().fg(SLATE_DIM)),
        Span::styled(app.status.status.to_uppercase(), Style::default().fg(status_color)),
        Span::styled("  ·  ", Style::default().fg(SLATE_DIM)),
        Span::styled(format!("PID: {}", pid_str), Style::default().fg(CREAM_DIM)),
        Span::styled("  ·  ", Style::default().fg(SLATE_DIM)),
        Span::styled(app.status.heartbeat_at.chars().take(19).collect::<String>(), Style::default().fg(SLATE_DIM)),
    ]))
    .block(Block::default().borders(Borders::BOTTOM).border_style(Style::default().fg(SLATE_DIM)));
    f.render_widget(daemon_status, header_chunks[2]);
}

fn render_content(f: &mut Frame, area: Rect, app: &App) {
    match app.active_tab {
        Tab::Dashboard => render_dashboard(f, area, app),
        Tab::NavMap => render_navmap(f, area, app),
        Tab::Initialize => render_initialize(f, area, app),
        Tab::Events => render_events(f, area, app),
        Tab::Queue => render_queue(f, area, app),
        Tab::Logs => render_logs(f, area),
    }
}

fn render_initialize(f: &mut Frame, area: Rect, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Title
            Constraint::Length(3), // Input box
            Constraint::Length(3), // Action Button
            Constraint::Min(0),    // Error/Status message
        ])
        .margin(2)
        .split(area);

    let title = Paragraph::new(Line::from(vec![
        Span::styled("◆ INITIALIZE DAEMON", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
    ]));
    f.render_widget(title, chunks[0]);

    let input = Paragraph::new(app.init_input.value())
        .block(Block::default().borders(Borders::ALL).title(" Target Repository Path ").border_style(Style::default().fg(CREAM_DIM)))
        .style(Style::default().fg(CREAM));
    f.render_widget(input, chunks[1]);
    
    // Make cursor visible for input
    f.set_cursor_position((
        chunks[1].x + app.init_input.visual_cursor() as u16 + 1,
        chunks[1].y + 1,
    ));

    let btn_style = if app.status.status == "running" {
        Style::default().fg(MUTED)
    } else {
        Style::default().bg(EMERALD).fg(Color::Black)
    };
    
    let btn_text = if app.status.status == "running" {
        "  DAEMON IS ALREADY RUNNING  "
    } else {
        "  [ENTER] START DAEMON  "
    };

    let btn = Paragraph::new(btn_text)
        .style(btn_style)
        .alignment(ratatui::layout::Alignment::Center);
    
    let btn_area = Layout::default().direction(Direction::Horizontal).constraints([Constraint::Percentage(30), Constraint::Percentage(40), Constraint::Percentage(30)]).split(chunks[2])[1];
    f.render_widget(btn, btn_area);

    if let Some(ref err) = app.init_error {
        let err_color = if err.starts_with("Error") { RUST } else { EMERALD };
        let msg = Paragraph::new(err.as_str())
            .style(Style::default().fg(err_color));
        f.render_widget(msg, chunks[3]);
    }
}

fn render_navmap(f: &mut Frame, area: Rect, app: &App) {
    let block = Block::default()
        .title(" NAVMAP — MODULE ATLAS ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));

    let header = Row::new(vec!["MODULE", "SUBSYSTEM", "LOC", "STALE", "PURPOSE"])
        .style(Style::default().fg(EMERALD).add_modifier(Modifier::BOLD));

    let rows: Vec<Row> = app.nav_modules.iter().map(|(name, module)| {
        let stale_color = match module.staleness.as_str() {
            "active" => EMERALD,
            "staling" => AMBER,
            "orphan" => RUST,
            _ => MUTED,
        };
        Row::new(vec![
            name.clone(),
            module.subsystem.clone(),
            module.loc.to_string(),
            module.staleness.clone(),
            module.purpose.clone(),
        ]).style(Style::default().fg(CREAM_DIM)).style(Style::default().fg(stale_color))
    }).collect();

    let table = Table::new(rows, [
        Constraint::Length(25),
        Constraint::Length(20),
        Constraint::Length(6),
        Constraint::Length(10),
        Constraint::Min(0),
    ])
    .header(header)
    .block(block);

    f.render_widget(table, area);
}

fn render_dashboard(f: &mut Frame, area: Rect, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(60), // Left: Actors & Current Task
            Constraint::Percentage(40), // Right: Capabilities & Dials
        ])
        .split(area);

    let left_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(10), // Actors
            Constraint::Min(0),     // Current Task
        ])
        .split(chunks[0]);

    let actors_block = Block::default()
        .title(" THE TWO ACTORS ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    
    let actors_text = vec![
        Line::from(""),
        Line::from(vec![
            Span::styled("  ◆ THE MACHINE", Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
            Span::styled("  intent · desire · goal", Style::default().fg(CREAM_DIM)),
            Span::styled("  ⟷  ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
            Span::styled("✦ THE CURIOUS AI", Style::default().fg(CREAM).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::styled("    not ai · discriminative · learning", Style::default().fg(SLATE_DIM)),
            Span::styled("        ", Style::default()),
            Span::styled("free · harnessed · insight-or-silence", Style::default().fg(SLATE_DIM)),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::styled("           │ ", Style::default().fg(SLATE)),
            Span::styled("refines your intent", Style::default().fg(CREAM_DIM)),
            Span::styled("                │ ", Style::default().fg(SLATE)),
            Span::styled("distills into the machine", Style::default().fg(CREAM_DIM)),
        ]),
        Line::from(vec![
            Span::styled("           ▾", Style::default().fg(EMERALD)),
            Span::styled("                                ▾", Style::default().fg(EMERALD)),
        ]),
    ];
    f.render_widget(Paragraph::new(actors_text).block(actors_block), left_chunks[0]);

    let task_block = Block::default()
        .title(" ACTIVE TASK ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    
    let task_text = if let Some(latest_event) = app.events.iter().find(|e| e.lane == "ingress" || e.lane == "workflow") {
        format!("Last Activity: {}\nKind: {}\nActor: {}", latest_event.ts, latest_event.kind, latest_event.actor)
    } else {
        "No active task. Use the CLI or type an intent to begin research.".to_string()
    };
    f.render_widget(Paragraph::new(task_text).block(task_block).wrap(Wrap { trim: true }), left_chunks[1]);

    let right_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),  // Capabilities
            Constraint::Length(10), // Dials
            Constraint::Min(0),     // Recent Runs
        ])
        .split(chunks[1]);

    let caps_block = Block::default()
        .title(" CAPABILITIES ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    f.render_widget(Paragraph::new("▸ eyes  search (floor)   read playwright\n        fetch standard   browser webkit").block(caps_block), right_chunks[0]);

    let dials_block = Block::default()
        .title(" STEERING ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    f.render_widget(Paragraph::new("frontierness [██████░░░░░] 0.60\nlens         [───◆───] +0.00\ndepth        [███░░░░░░░] 0.30").block(dials_block), right_chunks[1]);

    let runs_block = Block::default()
        .title(" RECENT RUNS ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    f.render_widget(Paragraph::new("▸ scans local substrate\n  awaiting first research run").block(runs_block), right_chunks[2]);
}

fn render_events(f: &mut Frame, area: Rect, app: &App) {
    let block = Block::default()
        .title(" DAEMON EVENT LOG ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    
    let items: Vec<ListItem> = app.events.iter().map(|e| {
        let color = match e.lane.as_str() {
            "ingress" => CREAM,
            "telemetry" => SLATE_DIM,
            "workflow" => EMERALD,
            "control" => AMBER,
            _ => MUTED,
        };
        let content = Line::from(vec![
            Span::styled(format!("{} ", e.ts.chars().skip(11).take(8).collect::<String>()), Style::default().fg(SLATE_DIM)),
            Span::styled(format!("{:<10} ", e.lane), Style::default().fg(color)),
            Span::styled(format!("{:<15} ", e.kind), Style::default().fg(CREAM)),
            Span::styled(format!("{}", e.payload), Style::default().fg(CREAM_DIM)),
        ]);
        ListItem::new(content)
    }).collect();

    let list = List::new(items).block(block);
    f.render_widget(list, area);
}

fn render_queue(f: &mut Frame, area: Rect, app: &App) {
    let block = Block::default()
        .title(" WORK QUEUE ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    
    let header = Row::new(vec!["ID", "KIND", "PRIO", "STATUS", "ENQUEUED"])
        .style(Style::default().fg(EMERALD).add_modifier(Modifier::BOLD));
    
    let rows: Vec<Row> = app.queue.iter().map(|item| {
        let status_color = match item.status.as_str() {
            "queued" => MUTED,
            "running" => EMERALD,
            "done" => CREAM_DIM,
            "failed" => RUST,
            _ => SLATE_DIM,
        };
        Row::new(vec![
            item.item_id.chars().take(8).collect::<String>(),
            item.kind.clone(),
            item.priority.to_string(),
            item.status.clone(),
            item.enqueued_at.chars().skip(11).take(8).collect::<String>(),
        ]).style(Style::default().fg(CREAM_DIM)).style(Style::default().fg(status_color))
    }).collect();

    let table = Table::new(rows, [
        Constraint::Length(10),
        Constraint::Length(15),
        Constraint::Length(6),
        Constraint::Length(10),
        Constraint::Min(0),
    ])
    .header(header)
    .block(block);
    
    f.render_widget(table, area);
}

fn render_logs(f: &mut Frame, area: Rect) {
    let block = Block::default()
        .title(" SYSTEM LOGS ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(SLATE_DIM))
        .title_style(Style::default().fg(EMERALD_DIM));
    f.render_widget(Paragraph::new("Initializing...").block(block), area);
}

fn render_footer(f: &mut Frame, area: Rect) {
    let footer_text = Line::from(vec![
        Span::styled(" Q ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("quit  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" TAB ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("next tab  ", Style::default().fg(CREAM_DIM)),
        Span::styled(" 1-5 ", Style::default().fg(EMERALD).add_modifier(Modifier::BOLD)),
        Span::styled("jump  ", Style::default().fg(CREAM_DIM)),
    ]);
    f.render_widget(Paragraph::new(footer_text).style(Style::default().bg(SLATE_DIM).fg(CREAM)), area);
}
