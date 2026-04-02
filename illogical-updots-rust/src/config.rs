use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Config {
    pub repo_path: String,
    pub auto_refresh_seconds: u64,
    pub detached_console: bool,
    pub installer_mode: String,
    pub use_pty: bool,
    pub force_color_env: bool,
    pub send_notifications: bool,
    pub log_max_lines: usize,
    pub changes_lazy_load: bool,
    pub pre_script_path: String,
    pub post_script_path: String,
    pub show_details_button: bool,
    pub keep_fish_config: bool,
    pub onboarding_shown: bool,
    pub git_fetch_all: bool,
    pub git_prune: bool,
    pub window_opacity: f32,
    pub console_font_size: u32,
    pub confirm_on_exit: bool,
    pub terminal_emulator: String,
    pub auto_hide_console: bool,
    pub verbose_git: bool,
    pub show_icons: bool,
    pub check_upstream: bool,
    pub notify_on_updates: bool,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            repo_path: String::new(),
            auto_refresh_seconds: 60,
            detached_console: false,
            installer_mode: "auto".to_string(),
            use_pty: true,
            force_color_env: true,
            send_notifications: true,
            log_max_lines: 5000,
            changes_lazy_load: true,
            pre_script_path: String::new(),
            post_script_path: String::new(),
            show_details_button: true,
            keep_fish_config: false,
            onboarding_shown: false,
            git_fetch_all: true,
            git_prune: true,
            window_opacity: 1.0,
            console_font_size: 12,
            confirm_on_exit: false,
            terminal_emulator: String::new(),
            auto_hide_console: true,
            verbose_git: false,
            show_icons: true,
            check_upstream: true,
            notify_on_updates: true,
        }
    }
}

pub fn get_config_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("illogical-updots")
        .join("settings.json")
}

pub fn load_config() -> Result<Config> {
    let path = get_config_path();
    if !path.exists() {
        return Ok(Config::default());
    }
    let content = std::fs::read_to_string(path)?;
    let config: Config = serde_json::from_str(&content).unwrap_or_default();
    Ok(config)
}

pub fn save_config(config: &Config) -> Result<()> {
    let path = get_config_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let content = serde_json::to_string_pretty(config)?;
    std::fs::write(path, content)?;
    Ok(())
}
