#!/usr/bin/env python3
"""
Refactored MainWindow implementation using modular helpers.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
import time
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

# App metadata and settings
from core.app_meta import (
    APP_ID,
    APP_TITLE,
    AUTO_REFRESH_SECONDS,
    REPO_PATH,
    SETTINGS,
)
from core.app_meta import (
    save_settings as _save_settings,
)

# Git utilities
from core.git_utils import (
    RepoStatus,
    check_repo_status,
    get_branch,
    get_upstream,
    run_git,
)

# Dialogs
from dialogs.about import show_about_dialog
from dialogs.changes import on_view_changes_quick
from dialogs.details import show_repo_info_dialog
from dialogs.logs import show_logs_dialog
from dialogs.pull_requests import show_pull_requests_dialog
from dialogs.settings import show_settings_dialog

# Reusable console panel
from ui.console_panel import ConsolePanel

# Process helpers
from utils.process import (
    spawn_setup_install as _spawn_setup_install,
    installer_entry as _installer_entry,
    installer_exists as _installer_exists,
    resolve_installer_basename as _resolve_installer_basename,
)

# Optional external console widget
from widgets.console import SetupConsole


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title=APP_TITLE)
        self.set_default_size(520, 280)
        self.set_border_width(0)

        self.set_opacity(float(SETTINGS.get("window_opacity", 1.0)))
        self._init_icons()

        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.props.title = APP_TITLE
        self.header_bar = hb
        self.header_bar.props.subtitle = self._get_current_repo_path()
        self.set_titlebar(hb)

        self.refresh_btn = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        self.refresh_btn.connect("clicked", self.on_refresh_clicked)
        hb.pack_start(self.refresh_btn)

        self.update_btn = Gtk.Button(label="Update")
        self.update_btn.connect("clicked", self.on_update_clicked)

        self.view_btn = Gtk.Button(label="View changes")
        self.view_btn.connect("clicked", lambda _btn: on_view_changes_quick(self, run_git))

        menu = Gtk.Menu()
        for label, callback in [
            ("Settings", self.on_settings_clicked),
            ("Git Logs", self.on_logs_clicked),
            ("Pull Requests", self.on_pull_requests_clicked),
            ("About", self.on_about_clicked),
        ]:
            mi = Gtk.MenuItem(label=label)
            mi.connect("activate", callback)
            menu.append(mi)
        menu.show_all()

        menu_btn = Gtk.MenuButton()
        menu_btn.set_popup(menu)
        menu_btn.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))

        hb.pack_end(menu_btn)
        hb.pack_end(self.view_btn)
        hb.pack_end(self.update_btn)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(16)
        outer.pack_start(content, True, True, 0)

        banner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        banner_box.set_hexpand(True)
        banner_box.set_vexpand(True)
        
        self.primary_label = Gtk.Label()
        self.primary_label.set_use_markup(True)
        self.primary_label.get_style_context().add_class("status-banner")
        self.primary_label.set_line_wrap(True)
        self.primary_label.set_markup("<span size='xx-large' weight='bold'>Checking repository status…</span>")

        eb = Gtk.EventBox()
        eb.add(self.primary_label)
        eb.connect("button-press-event", self._on_banner_clicked)
        banner_box.pack_start(eb, True, True, 0)

        self.small_info_btn = Gtk.Button(label="")
        self.small_info_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.small_info_btn.set_halign(Gtk.Align.CENTER)
        self.small_info_btn.connect("clicked", lambda _b: self._show_repo_info_dialog())
        self.small_info_btn.hide()
        banner_box.pack_start(self.small_info_btn, False, False, 0)

        self.force_update_btn = Gtk.Button(label="Force Re-install")
        self.force_update_btn.set_halign(Gtk.Align.CENTER)
        self.force_update_btn.connect("clicked", lambda _b: self.on_update_clicked(None))
        self.force_update_btn.hide()
        banner_box.pack_start(self.force_update_btn, False, False, 0)

        content.pack_start(banner_box, True, True, 0)

        spin_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.spinner = Gtk.Spinner()
        spin_box.pack_start(self.spinner, False, False, 0)
        self.status_hint = Gtk.Label(label="")
        spin_box.pack_start(self.status_hint, False, False, 0)
        content.pack_start(spin_box, False, False, 0)

        self.console = ConsolePanel(settings=SETTINGS)
        outer.pack_start(self.console.revealer, False, False, 0)

        self.error_revealer = Gtk.Revealer()
        error_frame = Gtk.Frame()
        error_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        error_box.set_border_width(8)
        self.error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic", Gtk.IconSize.MENU)
        self.error_label = Gtk.Label(xalign=0.0)
        self.error_label.set_line_wrap(True)
        error_box.pack_start(self.error_icon, False, False, 0)
        error_box.pack_start(self.error_label, True, True, 0)
        error_frame.add(error_box)
        self.error_revealer.add(error_frame)
        outer.pack_end(self.error_revealer, False, False, 0)

        self.show_all()
        self.connect("key-press-event", self._on_key_press)
        self.connect("delete-event", self._on_delete_event)

        self._status = None
        self._update_logs = []
        self._tray_icon = None
        self._auto_mode_choice = None

        self.refresh_status()
        GLib.timeout_add_seconds(AUTO_REFRESH_SECONDS, self._auto_refresh)

    def _on_delete_event(self, _win, _event):
        if bool(SETTINGS.get("confirm_on_exit", False)):
            dlg = Gtk.MessageDialog(transient_for=self, flags=Gtk.DialogFlags.MODAL, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text="Confirm Exit")
            dlg.format_secondary_text("Are you sure you want to close illogical-updots?")
            resp = dlg.run()
            dlg.destroy()
            return resp != Gtk.ResponseType.YES
        return False

    def _get_current_repo_path(self) -> str:
        return str(SETTINGS.get("repo_path", REPO_PATH) or REPO_PATH)

    def _init_icons(self) -> None:
        try:
            self.set_icon_name("illogical-updots")
        except Exception: pass

    def _busy(self, is_busy: bool, hint: str) -> None:
        self.refresh_btn.set_sensitive(not is_busy)
        can_update = not is_busy and self._status is not None and self._status.has_updates
        self.update_btn.set_sensitive(can_update or self._status is not None)
        self.view_btn.set_sensitive(can_update)
        if is_busy: self.spinner.start()
        else: self.spinner.stop()
        self.status_hint.set_text(hint or "")

    def _apply_update_button_style(self) -> None:
        ctx = self.update_btn.get_style_context()
        if self._status and self._status.has_updates:
            if not ctx.has_class("suggested-action"): ctx.add_class("suggested-action")
            self.update_btn.set_label("Update")
        else:
            if ctx.has_class("suggested-action"): ctx.remove_class("suggested-action")
            self.update_btn.set_label("Up to date")

    def _set_labels_for_status(self, st: RepoStatus) -> None:
        if not st.ok:
            self.primary_label.set_markup("<span size='xx-large' weight='bold' foreground='red'>Repository error</span>")
            return
        if st.fetch_error:
            self.error_label.set_text(f"Fetch warning: {st.fetch_error}")
            self.error_revealer.set_reveal_child(True)
        else:
            self.error_revealer.set_reveal_child(False)

        if st.behind > 0:
            self.primary_label.set_markup(f"<span size='xx-large' weight='bold'>Updates available</span>\n<span size='large'>{st.behind} new commit(s)</span>")
            self.force_update_btn.hide()
        else:
            self.primary_label.set_markup("<span size='xx-large' weight='bold'>Up to date</span>")
            self.force_update_btn.show()

    def on_refresh_clicked(self, _btn) -> None: self.refresh_status()
    def on_logs_clicked(self, _btn) -> None: show_logs_dialog(self)
    def on_settings_clicked(self, _btn) -> None:
        show_settings_dialog(self, SETTINGS, REPO_PATH, AUTO_REFRESH_SECONDS, _save_settings)
        self.header_bar.props.subtitle = self._get_current_repo_path()
    def on_about_clicked(self, _item) -> None: show_about_dialog(self, APP_TITLE, self._get_current_repo_path(), SETTINGS)
    def on_pull_requests_clicked(self, _item) -> None: show_pull_requests_dialog(self, run_git)
    def _show_repo_info_dialog(self) -> None: show_repo_info_dialog(self, run_git)
    def _on_banner_clicked(self, _widget, _event) -> bool:
        if self._status and self._status.has_updates: on_view_changes_quick(self, run_git)
        else: self._show_repo_info_dialog()
        return True

    def _on_key_press(self, _widget, event) -> bool:
        if event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (Gdk.KEY_i, Gdk.KEY_I):
            self._run_update_without_pull()
            return True
        return False

    def refresh_status(self) -> None:
        def work():
            st = check_repo_status(self._get_current_repo_path())
            GLib.idle_add(self._finish_refresh, st)
        self._busy(True, "Refreshing...")
        threading.Thread(target=work, daemon=True).start()

    def _finish_refresh(self, st: RepoStatus) -> None:
        self._status = st
        self._set_labels_for_status(st)
        self._apply_update_button_style()
        self._busy(False, "")

    def _auto_refresh(self) -> bool:
        self.refresh_status()
        return True

    def on_update_clicked(self, _btn) -> None:
        if not self._status: return
        repo_path = self._status.repo_path
        dlg = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text="Run update now?")
        if dlg.run() != Gtk.ResponseType.YES:
            dlg.destroy()
            return
        dlg.destroy()

        self.console.ensure_open()
        self._busy(True, "Updating...")

        def update_work():
            subprocess.run(["git", "pull", "--rebase", "--autostash"], cwd=repo_path)
            installer = _installer_entry(repo_path)
            extra_args = ["install-files"] if not installer.endswith(".sh") else []
            
            p = _spawn_setup_install(repo_path, lambda m: self.console.append(str(m)), extra_args=extra_args)
            if p and p.stdout:
                for line in iter(p.stdout.readline, ""):
                    self.console.append(line)
                p.wait()
            GLib.idle_add(self._finish_update, True, "Update done", "")

        threading.Thread(target=update_work, daemon=True).start()

    def _finish_update(self, success, stdout, stderr):
        self._busy(False, "")
        if success and bool(SETTINGS.get("auto_hide_console", True)):
            self.console.revealer.set_reveal_child(False)
        self.refresh_status()

    def _run_update_without_pull(self):
        repo_path = self._get_current_repo_path()
        installer = _installer_entry(repo_path)
        extra_args = ["install-files"] if not installer.endswith(".sh") else []
        self.console.run_command([installer] + extra_args, cwd=repo_path, on_finished=lambda status: self.refresh_status())


__all__ = ["MainWindow", "APP_ID", "APP_TITLE", "SETTINGS", "REPO_PATH", "_save_settings"]
 self.console.append(str(m)), extra_args=["install-files"])
            if p and p.stdout:
                for line in iter(p.stdout.readline, ""): self.console.append(line)
                p.wait()
            GLib.idle_add(self.refresh_status)
        threading.Thread(target=work, daemon=True).start()


__all__ = ["MainWindow", "APP_ID", "APP_TITLE", "SETTINGS", "REPO_PATH", "_save_settings"]
