use ratatui::{
    layout::{Constraint, Direction, Layout, Alignment, Rect},
    style::{Color, Modifier, Style, Stylize},
    text::{Line, Span},
    widgets::{Block, Borders, List, ListItem, Paragraph, Wrap, BorderType, Clear, ListState},
    Frame,
};
use crate::git::{RepoStatus, LogLine};
use crate::config::Config;

pub fn draw_main_menu(f: &mut Frame, status: &RepoStatus, selected_index: usize, refreshing: bool, tick_count: u64) {
    let area = f.area();
    
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(8),
            Constraint::Length(1),
        ])
        .split(area);

    let content_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),
            Constraint::Min(5),
        ])
        .split(main_chunks[1]);

    let icon_repo = "\u{f07c}"; 
    let icon_branch = "\u{e725}";
    let icon_update = "\u{f021}";
    let icon_check = "\u{f00c}";
    let icon_git = "\u{f1d3}";
    let icon_os = "\u{f311}";

    let spinner_frames = ["\u{280b}", "\u{2819}", "\u{281a}", "\u{2812}", "\u{2802}", "\u{2804}", "\u{2806}", "\u{2807}"];
    let spinner = if refreshing {
        spinner_frames[(tick_count % spinner_frames.len() as u64) as usize]
    } else {
        " "
    };

    let header_text = format!(" {} Illogical Updots \u{2022} System Sync {} ", icon_os, spinner);
    let header = Paragraph::new(header_text)
        .alignment(Alignment::Center)
        .style(Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD))
        .block(Block::default()
            .borders(Borders::BOTTOM)
            .border_type(BorderType::Double)
            .border_style(Style::default().fg(Color::Blue)));
    f.render_widget(header, main_chunks[0]);

    let mut status_lines = vec![
        Line::from(vec![
            Span::styled(format!(" {} Repository ", icon_repo), Style::default().fg(Color::Yellow)),
            Span::raw(" \u{27a1} "),
            Span::styled(&status.repo_path, Style::default().italic().fg(Color::Indexed(244))),
        ]),
    ];

    if status.ok {
        let branch = status.branch.as_deref().unwrap_or("detached");
        let upstream = status.upstream.as_deref().unwrap_or("none");
        
        status_lines.push(Line::from(vec![
            Span::styled(format!(" {} Branch     ", icon_branch), Style::default().fg(Color::Magenta)),
            Span::raw(" \u{27a1} "),
            Span::styled(branch, Style::default().bold().fg(Color::White)),
            Span::raw(" \u{f460} "),
            Span::styled(upstream, Style::default().dim().fg(Color::Blue)),
        ]));

        let (status_icon, status_color, status_msg) = if status.behind > 0 {
            ("\u{f019}", Color::LightRed, format!("Update available! You are {} commits behind", status.behind))
        } else {
            (icon_check, Color::Green, "System is up to date".to_string())
        };

        status_lines.push(Line::from(vec![
            Span::styled(format!(" {} Sync       ", status_icon), Style::default().fg(status_color)),
            Span::raw(" \u{27a1} "),
            Span::styled(status_msg, Style::default().fg(status_color)),
            Span::raw(format!(" ({} ahead)", status.ahead)).dim(),
        ]));

        if status.dirty > 0 {
            status_lines.push(Line::from(vec![
                Span::styled(format!(" \u{f044} Modified   "), Style::default().fg(Color::Red)),
                Span::raw(" \u{27a1} "),
                Span::styled(format!("{} untracked or changed files", status.dirty), Style::default().fg(Color::Red)),
            ]));
        }

        if let Some(ref fetch_err) = status.fetch_error {
            status_lines.push(Line::from(vec![
                Span::styled(format!(" \u{f00d} Fetch Err  "), Style::default().fg(Color::Red).dim()),
                Span::raw(" \u{27a1} "),
                Span::styled(fetch_err, Style::default().fg(Color::Red).dim()),
            ]));
        }
        
        if refreshing {
            status_lines.push(Line::from(vec![
                Span::styled(format!(" {} Checking... ", spinner), Style::default().fg(Color::Blue).bold()),
            ]));
        }
    } else {
        status_lines.push(Line::from(vec![
            Span::styled(" \u{f071} Error      ", Style::default().fg(Color::Red).bold()),
            Span::raw(" \u{27a1} "),
            Span::styled(status.error.as_deref().unwrap_or("Critical Repo Error"), Style::default().fg(Color::Red)),
        ]));
    }

    let status_block = Block::default()
        .title(format!(" {} System Status ", icon_git))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Indexed(240)));
    
    f.render_widget(Paragraph::new(status_lines).block(status_block), content_chunks[0]);

    let menu_items = [
        format!(" {}  Refresh Status", icon_update),
        format!(" \u{f019}  Update System"),
        format!(" \u{f0c6e}  Git History"),
        format!(" \u{f013}  Settings"),
        format!(" \u{f08b}  Exit"),
    ];

    let items: Vec<ListItem> = menu_items
        .iter()
        .enumerate()
        .map(|(i, item)| {
            let is_selected = i == selected_index;
            let content = if is_selected {
                Line::from(vec![
                    Span::styled(" \u{27a4} ", Style::default().fg(Color::Yellow).bold()),
                    Span::styled(item, Style::default().fg(Color::White).bold()),
                ])
            } else {
                Line::from(vec![
                    Span::raw("   "),
                    Span::styled(item, Style::default().fg(Color::Indexed(250))),
                ])
            };
            
            ListItem::new(content).style(if is_selected {
                Style::default().bg(Color::Indexed(236))
            } else {
                Style::default()
            })
        })
        .collect();

    let menu_block = Block::default()
        .title(" Menu ")
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Indexed(240)));
    
    f.render_widget(List::new(items).block(menu_block), content_chunks[1]);

    let footer = Paragraph::new(format!(" \u{f11c} Arrows: Navigate \u{2022} Enter: Select \u{2022} R: Refresh \u{2022} Q: Quit "))
        .alignment(Alignment::Left)
        .style(Style::default().fg(Color::Indexed(242)));
    f.render_widget(footer, main_chunks[2]);
}

pub fn draw_commits(f: &mut Frame, lines: &[LogLine], state: &mut ListState, details: &str, progress: f32) {
    let area = f.area();
    
    let items: Vec<ListItem> = lines
        .iter()
        .enumerate()
        .map(|(i, line)| {
            let is_selected = state.selected() == Some(i);
            let mut spans = Vec::new();
            
            for ch in line.graph.chars() {
                let color = match ch {
                    '*' => Color::Yellow,
                    '|' => Color::Indexed(240),
                    '/' => Color::Green,
                    '\\' => Color::Red,
                    _ => Color::Indexed(244),
                };
                let sym = match ch {
                    '*' => "\u{f192}",
                    '|' => "\u{2502}",
                    '/' => "\u{2571}",
                    '\\' => "\u{2572}",
                    _ => ch.to_string().leak(),
                };
                spans.push(Span::styled(sym, Style::default().fg(color)));
            }

            if let Some(ref c) = line.commit {
                spans.push(Span::styled(format!(" {} ", c.hash), Style::default().fg(Color::Blue)));
                
                if !c.decoration.is_empty() {
                    spans.push(Span::styled(format!("{} ", c.decoration), Style::default().fg(Color::Magenta).italic()));
                }
                
                let msg_style = if is_selected {
                    Style::default().fg(Color::White).bold()
                } else {
                    Style::default().fg(Color::Indexed(252))
                };
                spans.push(Span::styled(&c.message, msg_style));
            }
            
            ListItem::new(Line::from(spans)).style(if is_selected {
                Style::default().bg(Color::Indexed(236))
            } else {
                Style::default()
            })
        })
        .collect();

    let list_block = Block::default()
        .title(" \u{f0c6e} Git History Map ")
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded);
    
    f.render_stateful_widget(List::new(items).block(list_block), area, state);

    if progress > 0.0 {
        let width = (area.width as f32 * 0.7 * progress) as u16;
        let details_area = Rect {
            x: area.x + area.width - width,
            y: area.y,
            width,
            height: area.height,
        };
        
        f.render_widget(Clear, details_area);
        
        let mut details_lines = Vec::new();
        if let Some(i) = state.selected() {
            if let Some(line) = lines.get(i) {
                if let Some(ref c) = line.commit {
                    details_lines.push(Line::from(vec![
                        Span::styled(" \u{f007} Author: ", Style::default().fg(Color::Yellow).bold()),
                        Span::styled(&c.author, Style::default().fg(Color::White)),
                    ]));
                    details_lines.push(Line::from(vec![
                        Span::styled(" \u{f017} Date:   ", Style::default().fg(Color::Yellow).bold()),
                        Span::styled(&c.date, Style::default().fg(Color::White)),
                    ]));
                    details_lines.push(Line::from(Span::raw("")));
                }
            }
        }

        for line in details.lines() {
            let style = if line.starts_with('+') && !line.starts_with("+++") {
                Style::default().fg(Color::Green)
            } else if line.starts_with('-') && !line.starts_with("---") {
                Style::default().fg(Color::Red)
            } else if line.starts_with("@@") {
                Style::default().fg(Color::Cyan)
            } else if line.starts_with("commit") || line.starts_with("Author:") || line.starts_with("Date:") {
                Style::default().fg(Color::Yellow).bold()
            } else {
                Style::default().fg(Color::Indexed(250))
            };
            details_lines.push(Line::from(Span::styled(line, style)));
        }

        let details_block = Block::default()
            .title(" \u{f05a} Detailed View ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(Style::default().fg(Color::Cyan));
            
        f.render_widget(
            Paragraph::new(details_lines)
                .block(details_block)
                .wrap(Wrap { trim: false }),
            details_area
        );
    }
}

pub fn draw_settings(f: &mut Frame, config: &Config, selected_index: usize) {
    let area = f.area();
    let vertical = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Length(3),
            Constraint::Length(3),
            Constraint::Length(3),
            Constraint::Length(3),
            Constraint::Min(0),
        ])
        .split(area);

    let active_style = Style::default().fg(Color::Yellow).bold();
    let inactive_style = Style::default().fg(Color::Indexed(244));

    let p1 = Paragraph::new(format!(" \u{f07c}  {}", config.repo_path))
        .block(Block::default()
            .title(" [0] Repo Path ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(if selected_index == 0 { active_style } else { inactive_style }));
    f.render_widget(p1, vertical[0]);

    let p2 = Paragraph::new(format!(" \u{f017}  {}s", config.auto_refresh_seconds))
        .block(Block::default()
            .title(" [1] Refresh Rate ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(if selected_index == 1 { active_style } else { inactive_style }));
    f.render_widget(p2, vertical[1]);

    let p3 = Paragraph::new(format!(" \u{f03e}  {}", if config.show_icons { "Enabled" } else { "Disabled" }))
        .block(Block::default()
            .title(" [2] Show Icons ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(if selected_index == 2 { active_style } else { inactive_style }));
    f.render_widget(p3, vertical[2]);

    let p4 = Paragraph::new(format!(" \u{f1d3}  {}", if config.check_upstream { "Enabled" } else { "Disabled" }))
        .block(Block::default()
            .title(" [3] Auto-Fetch Upstream ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(if selected_index == 3 { active_style } else { inactive_style }));
    f.render_widget(p4, vertical[3]);

    let p5 = Paragraph::new(format!(" \u{f0f3}  {}", if config.notify_on_updates { "Enabled" } else { "Disabled" }))
        .block(Block::default()
            .title(" [4] Notifications ")
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(if selected_index == 4 { active_style } else { inactive_style }));
    f.render_widget(p5, vertical[4]);

    let help_text = vec![
        Line::from(vec![
            Span::styled(" \u{f05a} ", Style::default().fg(Color::Blue)),
            Span::raw("E: Edit/Toggle \u{2022} S: Save \u{2022} Esc: Cancel"),
        ]),
    ];
    f.render_widget(Paragraph::new(help_text), vertical[5]);
}
