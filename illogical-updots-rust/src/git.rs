use std::process::Command;
use anyhow::Result;

#[derive(Debug, Clone, Default)]
#[allow(dead_code)]
pub struct RepoStatus {
    pub ok: bool,
    pub repo_path: String,
    pub branch: Option<String>,
    pub upstream: Option<String>,
    pub behind: i32,
    pub ahead: i32,
    pub dirty: i32,
    pub fetch_error: Option<String>,
    pub error: Option<String>,
}

fn run_git(args: &[&str], cwd: &str) -> Result<(i32, String, String)> {
    let output = Command::new("git")
        .args(args)
        .current_dir(cwd)
        .output()?;
    
    let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
    let code = output.status.code().unwrap_or(1);
    
    Ok((code, stdout, stderr))
}

pub fn get_branch(cwd: &str) -> Option<String> {
    match run_git(&["rev-parse", "--abbrev-ref", "HEAD"], cwd) {
        Ok((0, out, _)) => Some(out),
        _ => None,
    }
}

pub fn get_upstream(cwd: &str, branch: Option<&str>) -> Option<String> {
    match run_git(&["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd) {
        Ok((0, out, _)) => Some(out),
        _ => {
            if let Some(b) = branch {
                Some(format!("origin/{}", b))
            } else {
                None
            }
        }
    }
}

pub fn get_dirty_count(cwd: &str) -> i32 {
    match run_git(&["status", "--porcelain"], cwd) {
        Ok((0, out, _)) => {
            out.lines().filter(|l| !l.trim().is_empty()).count() as i32
        }
        _ => 0,
    }
}

pub fn check_repo_status(repo_path: &str) -> RepoStatus {
    let mut status = RepoStatus {
        repo_path: repo_path.to_string(),
        ..Default::default()
    };

    let path = std::path::Path::new(repo_path);
    if !path.is_dir() {
        status.error = Some("Repository path not found".to_string());
        return status;
    }
    if !path.join(".git").is_dir() {
        status.error = Some("Not a git repository".to_string());
        return status;
    }

    let mut fetch_error = None;
    match run_git(&["fetch", "--all", "--prune"], repo_path) {
        Ok((0, _, _)) => {}
        Ok((_, _, err)) => {
            fetch_error = Some(if err.is_empty() { "fetch failed".to_string() } else { err });
        }
        Err(e) => {
            fetch_error = Some(e.to_string());
        }
    }

    let branch = get_branch(repo_path);
    let upstream = get_upstream(repo_path, branch.as_deref());

    let mut behind = 0;
    let mut ahead = 0;

    if let Some(ref u) = upstream {
        if let Ok((0, out_b, _)) = run_git(&["rev-list", "--count", &format!("HEAD..{}", u)], repo_path) {
            behind = out_b.parse().unwrap_or(0);
        }
        if let Ok((0, out_a, _)) = run_git(&["rev-list", "--count", &format!("{}..HEAD", u)], repo_path) {
            ahead = out_a.parse().unwrap_or(0);
        }
    }

    let dirty = get_dirty_count(repo_path);

    RepoStatus {
        ok: true,
        repo_path: repo_path.to_string(),
        branch,
        upstream,
        behind,
        ahead,
        dirty,
        fetch_error,
        error: None,
    }
}

#[derive(Debug, Clone)]
pub struct CommitInfo {
    pub hash: String,
    pub author: String,
    pub date: String,
    pub message: String,
    pub decoration: String,
}

#[derive(Debug, Clone)]
pub struct LogLine {
    pub graph: String,
    pub commit: Option<CommitInfo>,
}

pub fn fetch_commits(repo_path: &str, count: usize) -> Vec<LogLine> {
    let output = Command::new("git")
        .args([
            "log",
            &format!("-n {}", count),
            "--graph",
            "--pretty=format:SEP%h|%an|%ar|%s|%d",
            "--color=never",
        ])
        .current_dir(repo_path)
        .output();

    match output {
        Ok(out) if out.status.success() => {
            String::from_utf8_lossy(&out.stdout)
                .lines()
                .map(|line| {
                    if let Some(idx) = line.find("SEP") {
                        let graph = line[..idx].to_string();
                        let rest = &line[idx + 3..];
                        let parts: Vec<&str> = rest.split('|').collect();
                        
                        LogLine {
                            graph,
                            commit: Some(CommitInfo {
                                hash: parts.get(0).unwrap_or(&"").to_string(),
                                author: parts.get(1).unwrap_or(&"").to_string(),
                                date: parts.get(2).unwrap_or(&"").to_string(),
                                message: parts.get(3).unwrap_or(&"").to_string(),
                                decoration: parts.get(4).unwrap_or(&"").to_string(),
                            }),
                        }
                    } else {
                        LogLine {
                            graph: line.to_string(),
                            commit: None,
                        }
                    }
                })
                .collect()
        }
        _ => Vec::new(),
    }
}

pub fn get_commit_details(repo_path: &str, hash: &str) -> String {
    if hash.is_empty() { return String::new(); }
    let output = Command::new("git")
        .args(["show", "--stat", "--patch", "--color=always", hash])
        .current_dir(repo_path)
        .output();

    match output {
        Ok(out) => String::from_utf8_lossy(&out.stdout).to_string(),
        Err(e) => format!("Error: {}", e),
    }
}

pub fn run_pull(repo_path: &str) -> Result<()> {
    let mut child = Command::new("git")
        .args(["pull", "--rebase", "--autostash"])
        .current_dir(repo_path)
        .spawn()?;
    
    let status = child.wait()?;
    if status.success() {
        Ok(())
    } else {
        anyhow::bail!("git pull failed")
    }
}
