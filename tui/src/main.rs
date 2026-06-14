mod models;
mod db;

use color_eyre::Result;
use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Tabs, Wrap, ListItem, Table, Row, List},
    DefaultTerminal, Frame,
};
use std::time::{Duration, Instant};
use crate::models::{DaemonEvent, WorkItem, DaemonStatus, NavModule};
use crate::db::Db;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Tab {
    Dashboard,
    NavMap,
    Events,
    Queue,
    Logs,
}

impl Tab {
    fn all() -> &'static [Tab] {
        &[Tab::Dashboard, Tab::NavMap, Tab::Events, Tab::Queue, Tab::Logs]
    }

    fn to_index(self) -> usize {
        match self {
            Tab::Dashboard => 0,
            Tab::NavMap => 1,
            Tab::Events => 2,
            Tab::Queue => 3,
            Tab::Logs => 4,
        }
    }

    fn from_index(index: usize) -> Self {
        match index % 5 {
            0 => Tab::Dashboard,
            1 => Tab::NavMap,
            2 => Tab::Events,
            3 => Tab::Queue,
            4 => Tab::Logs,
            _ => unreachable!(),
        }
    }

    fn title(self) -> &'static str {
        match self {
            Tab::Dashboard => "◈ DASHBOARD",
            Tab::NavMap => "🧭 NAVMAP",
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
            self.active_tab = Tab::from_index(3);
        } else {
            self.active_tab = Tab::from_index(index - 1);
        }
    }
}

fn main() -> Result<()> {
    color_eyre::install()?;
    
    // Auto-detect repo root
    let repo_root = std::env::current_dir()?;
    // If we are in a worktree, we might need to go up or find the main repo.
    // For now, assume the cwd is where the store should be or it's a valid repo.
    
    let db = Db::new(&repo_root);
    let mut terminal = ratatui::init();
    let app = App::new();
    let result = run_app(&mut terminal, app, db);
    ratatui::restore();
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
                    match key.code {
                        KeyCode::Char('q') | KeyCode::Esc => app.should_quit = true,
                        KeyCode::Tab | KeyCode::Right => app.next_tab(),
                        KeyCode::Left => app.prev_tab(),
                        KeyCode::Char('1') => app.active_tab = Tab::Dashboard,
                        KeyCode::Char('2') => app.active_tab = Tab::NavMap,
                        KeyCode::Char('3') => app.active_tab = Tab::Events,
                        KeyCode::Char('4') => app.active_tab = Tab::Queue,
                        KeyCode::Char('5') => app.active_tab = Tab::Logs,
                        _ => {}
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
        Tab::Events => render_events(f, area, app),
        Tab::Queue => render_queue(f, area, app),
        Tab::Logs => render_logs(f, area),
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
