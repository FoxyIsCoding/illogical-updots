mod config;
mod git;
mod ui;

use std::{
    io::{self, Stdout},
    time::{Duration, Instant},
    sync::{Arc, Mutex},
};

use anyhow::Result;
use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    Terminal,
    widgets::ListState,
};

use crate::config::{Config, load_config, save_config};
use crate::git::{check_repo_status, RepoStatus, run_pull, LogLine, fetch_commits, get_commit_details};

#[derive(PartialEq)]
enum AppState {
    MainMenu,
    ViewingCommits,
    Settings,
    EditingField(usize),
}

struct App {
    config: Config,
    status: Arc<Mutex<RepoStatus>>,
    state: AppState,
    selected_index: usize,
    log_lines: Vec<LogLine>,
    commit_index: usize,
    commit_details: String,
    last_refresh: Instant,
    edit_buffer: String,
    refreshing: Arc<Mutex<bool>>,
    tick_count: u64,
    details_open: bool,
    details_progress: f32,
    history_state: ListState,
}

impl App {
    fn new(config: Config) -> Self {
        let status = Arc::new(Mutex::new(RepoStatus::default()));
        
        let app = Self {
            config,
            status,
            state: AppState::MainMenu,
            selected_index: 0,
            log_lines: Vec::new(),
            commit_index: 0,
            commit_details: String::new(),
            last_refresh: Instant::now(),
            edit_buffer: String::new(),
            refreshing: Arc::new(Mutex::new(false)),
            tick_count: 0,
            details_open: false,
            details_progress: 0.0,
            history_state: ListState::default(),
        };
        
        app.refresh_status();
        app
    }

    fn refresh_status(&self) {
        let repo_path = self.config.repo_path.clone();
        let status_arc = Arc::clone(&self.status);
        let refreshing_arc = Arc::clone(&self.refreshing);

        if repo_path.is_empty() {
            return;
        }

        tokio::spawn(async move {
            {
                let mut refreshing = refreshing_arc.lock().unwrap();
                if *refreshing { return; }
                *refreshing = true;
            }

            let new_status = check_repo_status(&repo_path);
            
            {
                let mut status = status_arc.lock().unwrap();
                *status = new_status;
            }

            {
                let mut refreshing = refreshing_arc.lock().unwrap();
                *refreshing = false;
            }
        });
    }

    fn load_commits(&mut self) {
        self.log_lines = fetch_commits(&self.config.repo_path, 100);
        self.commit_index = 0;
        self.history_state.select(Some(0));
        self.update_commit_details();
    }

    fn update_commit_details(&mut self) {
        if let Some(line) = self.log_lines.get(self.commit_index) {
            if let Some(ref c) = line.commit {
                self.commit_details = get_commit_details(&self.config.repo_path, &c.hash);
            } else {
                self.commit_details = "Graph connection node\nSelect a commit line to see details.".to_string();
            }
        } else {
            self.commit_details = "No log data found".to_string();
        }
    }

    fn run_update(&mut self) -> Result<()> {
        if self.config.repo_path.is_empty() {
            anyhow::bail!("Repository path not set");
        }
        
        println!("Pulling updates...");
        run_pull(&self.config.repo_path)?;
        
        let repo_name = std::path::Path::new(&self.config.repo_path)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        
        let installer = if repo_name == "ii-vynx" {
            "setup-ii-vynx.sh"
        } else {
            "setup"
        };
        
        let installer_path = std::path::Path::new(&self.config.repo_path).join(installer);
        
        if installer_path.exists() {
            println!("Running installer: {}...", installer);
            let mut cmd = std::process::Command::new("sh");
            cmd.arg(installer_path).current_dir(&self.config.repo_path);
            let mut child = cmd.spawn()?;
            child.wait()?;
        }
        
        self.refresh_status();
        Ok(())
    }
}

fn setup_terminal() -> Result<Terminal<CrosstermBackend<Stdout>>> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    Ok(Terminal::new(backend)?)
}

fn restore_terminal(mut terminal: Terminal<CrosstermBackend<Stdout>>) -> Result<()> {
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    let config = load_config().unwrap_or_default();
    let mut app = App::new(config);

    if app.config.repo_path.is_empty() {
        println!("Repository path not configured. Enter path: ");
        let mut input = String::new();
        io::stdin().read_line(&mut input)?;
        let path = input.trim().to_string();
        if !path.is_empty() {
            app.config.repo_path = path;
            let _ = save_config(&app.config);
            app.refresh_status();
        }
    }

    let mut terminal = setup_terminal()?;

    loop {
        app.tick_count += 1;
        
        if app.details_open && app.details_progress < 1.0 {
            app.details_progress += 0.2;
            if app.details_progress > 1.0 { app.details_progress = 1.0; }
        } else if !app.details_open && app.details_progress > 0.0 {
            app.details_progress -= 0.2;
            if app.details_progress < 0.0 { app.details_progress = 0.0; }
        }

        terminal.draw(|f| {
            let status = app.status.lock().unwrap();
            let refreshing = *app.refreshing.lock().unwrap();
            match app.state {
                AppState::MainMenu => ui::draw_main_menu(f, &status, app.selected_index, refreshing, app.tick_count),
                AppState::ViewingCommits => ui::draw_commits(f, &app.log_lines, &mut app.history_state, &app.commit_details, app.details_progress),
                AppState::Settings => ui::draw_settings(f, &app.config, app.selected_index),
                AppState::EditingField(_) => {
                    let mut temp_config = app.config.clone();
                    if let AppState::EditingField(field) = app.state {
                        match field {
                            0 => temp_config.repo_path = app.edit_buffer.clone(),
                            1 => temp_config.auto_refresh_seconds = app.edit_buffer.parse().unwrap_or(0),
                            _ => {}
                        }
                    }
                    ui::draw_settings(f, &temp_config, app.selected_index);
                }
            }
        })?;

        if event::poll(Duration::from_millis(16))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    match app.state {
                        AppState::MainMenu => match key.code {
                            KeyCode::Char('q') => break,
                            KeyCode::Up => if app.selected_index > 0 { app.selected_index -= 1 },
                            KeyCode::Down => if app.selected_index < 4 { app.selected_index += 1 },
                            KeyCode::Char('1') | KeyCode::Char('r') => app.refresh_status(),
                            KeyCode::Char('2') | KeyCode::Enter if app.selected_index == 1 => {
                                restore_terminal(terminal)?;
                                let _ = app.run_update();
                                terminal = setup_terminal()?;
                            }
                            KeyCode::Char('3') | KeyCode::Enter if app.selected_index == 2 => {
                                app.load_commits();
                                app.state = AppState::ViewingCommits;
                            }
                            KeyCode::Char('4') | KeyCode::Enter if app.selected_index == 3 => {
                                app.selected_index = 0;
                                app.state = AppState::Settings;
                            }
                            KeyCode::Enter => match app.selected_index {
                                0 => app.refresh_status(),
                                4 => break,
                                _ => {}
                            }
                            _ => {}
                        },
                        AppState::ViewingCommits => match key.code {
                            KeyCode::Esc | KeyCode::Char('q') => {
                                if app.details_open {
                                    app.details_open = false;
                                } else {
                                    app.state = AppState::MainMenu;
                                }
                            }
                            KeyCode::Enter => {
                                if let Some(line) = app.log_lines.get(app.commit_index) {
                                    if line.commit.is_some() {
                                        if !app.details_open {
                                            app.update_commit_details();
                                            app.details_open = true;
                                        } else {
                                            app.details_open = false;
                                        }
                                    }
                                }
                            }
                            KeyCode::Up => {
                                if app.commit_index > 0 {
                                    app.commit_index -= 1;
                                    app.history_state.select(Some(app.commit_index));
                                    if app.details_open {
                                        app.update_commit_details();
                                    }
                                }
                            }
                            KeyCode::Down => {
                                if app.commit_index < app.log_lines.len() - 1 {
                                    app.commit_index += 1;
                                    app.history_state.select(Some(app.commit_index));
                                    if app.details_open {
                                        app.update_commit_details();
                                    }
                                }
                            }
                            _ => {}
                        },
                        AppState::Settings => match key.code {
                            KeyCode::Esc | KeyCode::Char('q') => {
                                app.selected_index = 3;
                                app.state = AppState::MainMenu;
                            }
                            KeyCode::Up => if app.selected_index > 0 { app.selected_index -= 1 },
                            KeyCode::Down => if app.selected_index < 5 { app.selected_index += 1 },
                            KeyCode::Char('e') => {
                                app.edit_buffer = match app.selected_index {
                                    0 => app.config.repo_path.clone(),
                                    1 => app.config.auto_refresh_seconds.to_string(),
                                    _ => String::new(),
                                };
                                if app.selected_index < 2 {
                                    app.state = AppState::EditingField(app.selected_index);
                                } else {
                                    match app.selected_index {
                                        2 => app.config.show_icons = !app.config.show_icons,
                                        3 => app.config.check_upstream = !app.config.check_upstream,
                                        4 => app.config.notify_on_updates = !app.config.notify_on_updates,
                                        _ => {}
                                    }
                                }
                            }
                            KeyCode::Char('s') => {
                                let _ = save_config(&app.config);
                                app.state = AppState::MainMenu;
                            }
                            _ => {}
                        },
                        AppState::EditingField(field) => match key.code {
                            KeyCode::Esc => app.state = AppState::Settings,
                            KeyCode::Enter => {
                                if field == 0 {
                                    app.config.repo_path = app.edit_buffer.clone();
                                } else if field == 1 {
                                    app.config.auto_refresh_seconds = app.edit_buffer.parse().unwrap_or(60);
                                }
                                app.state = AppState::Settings;
                            }
                            KeyCode::Char(c) => app.edit_buffer.push(c),
                            KeyCode::Backspace => { app.edit_buffer.pop(); }
                            _ => {}
                        }
                    }
                }
            }
        }

        if app.last_refresh.elapsed() > Duration::from_secs(app.config.auto_refresh_seconds) && app.state == AppState::MainMenu {
            app.refresh_status();
            app.last_refresh = Instant::now();
        }
    }

    restore_terminal(terminal)?;
    Ok(())
}
