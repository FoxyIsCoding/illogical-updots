#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.prompt import Prompt, Confirm

from core.app_meta import SETTINGS, REPO_PATH, save_settings
from core.git_utils import check_repo_status, run_git
from utils.process import installer_entry, spawn_setup_install

console = Console()

def clear():
    os.system('cls' if os.name == 'nt' else 'clear')

def get_status_display(st):
    if not st.ok:
        return Text("Repository Error", style="bold red")
    
    if st.behind > 0:
        return Text(f"Updates Available ({st.behind} new commits)", style="bold yellow")
    
    return Text("Up to Date", style="bold green")

def show_header():
    console.print(Panel.fit(
        "[bold cyan]Illogical Updots[/bold cyan] - TUI Mode",
        border_style="blue"
    ))

def main_menu():
    global REPO_PATH
    while True:
        clear()
        show_header()
        
        if not REPO_PATH or not os.path.isdir(REPO_PATH):
            console.print("[bold red]Error:[/bold red] Repository path not configured or invalid.")
            REPO_PATH = Prompt.ask("Enter repository path (or 'q' to quit)")
            if REPO_PATH.lower() == 'q':
                sys.exit(0)
            SETTINGS['repo_path'] = REPO_PATH
            save_settings(SETTINGS)
            continue

        st = check_repo_status(REPO_PATH)
        status_text = get_status_display(st)
        
        console.print(f"Repo: [dim]{REPO_PATH}[/dim]")
        console.print(f"Status: {status_text}")
        console.print()
        
        table = Table(show_header=False, box=None)
        table.add_row("[1] Refresh Status")
        table.add_row("[2] Update / Re-install")
        table.add_row("[3] View Commits")
        table.add_row("[4] Settings (Minimal)")
        table.add_row("[q] Quit")
        console.print(table)
        
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "q"], default="1")
        
        if choice == "1":
            continue
        elif choice == "2":
            run_update(REPO_PATH)
        elif choice == "3":
            view_commits(REPO_PATH)
        elif choice == "4":
            minimal_settings()
        elif choice == "q":
            break

def run_update(repo_path):
    if not Confirm.ask("Run update now?"):
        return
    
    console.print("[bold blue]Updating repository...[/bold blue]")
    subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=repo_path)
    
    installer = installer_entry(repo_path)
    console.print(f"[bold blue]Running installer: {installer}[/bold blue]")
    
    extra_args = ["install-files"] if not installer.endswith(".sh") else []
    
    p = subprocess.Popen(
        [installer] + extra_args,
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    if p.stdout:
        for line in iter(p.stdout.readline, ""):
            console.print(line.strip())
    
    p.wait()
    console.print("\n[bold green]Update finished![/bold green]")
    Prompt.ask("Press Enter to continue")

def view_commits(repo_path):
    rc, out, err = run_git(["log", "-n", "10", "--oneline", "--graph", "--decorate"], repo_path)
    if rc == 0:
        console.print(Panel(out, title="Recent Commits", border_style="dim"))
    else:
        console.print(f"[bold red]Error:[/bold red] {err}")
    Prompt.ask("Press Enter to continue")

def minimal_settings():
    console.print("\n[bold]Minimal Settings[/bold]")
    new_refresh = Prompt.ask("Auto refresh seconds", default=str(SETTINGS.get('auto_refresh_seconds', 60)))
    try:
        SETTINGS['auto_refresh_seconds'] = int(new_refresh)
    except ValueError:
        pass
    
    save_settings(SETTINGS)
    console.print("[green]Settings saved.[/green]")
    time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting...[/yellow]")
