import os
import shutil
import subprocess
import threading
from typing import Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from core.app_meta import save_settings
from ui.console_panel import ConsolePanel
from utils.process import spawn_setup_install


class OnboardingDialog(Gtk.Dialog):
    def __init__(self, parent: Optional[Gtk.Window], settings: dict):
        super().__init__(title="Welcome to Illogical Updots", transient_for=parent, flags=0)
        self.set_default_size(700, 500)
        self.settings = settings
        self.repo_path = ""
        self.selected_flavor = "ii"

        content = self.get_content_area()
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(400)
        content.add(self.stack)

        self._init_welcome_page()
        self._init_settings_page()
        self._init_install_page()

        self.show_all()

    def _init_welcome_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_border_width(30)
        box.set_valign(Gtk.Align.CENTER)

        label = Gtk.Label()
        label.set_markup("<span size='xx-large' weight='bold'>Welcome to Illogical Updots</span>")
        box.pack_start(label, False, False, 0)

        desc = Gtk.Label(label="This tool helps you manage and update your Hyprland dotfiles effortlessly.\nTo get started, please select your dotfiles flavor.")
        desc.set_line_wrap(True)
        desc.set_justify(Gtk.Justification.CENTER)
        box.pack_start(desc, False, False, 0)

        flavors = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        flavors.set_halign(Gtk.Align.CENTER)
        box.pack_start(flavors, False, False, 0)

        # ii column
        ii_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ii_btn = Gtk.Button(label="ii (Standard)")
        ii_btn.get_style_context().add_class("suggested-action")
        ii_btn.set_size_request(200, 100)
        ii_btn.connect("clicked", self._on_ii_selected)
        ii_col.pack_start(ii_btn, False, False, 0)
        ii_desc = Gtk.Label(label="Standard 'ii' dotfiles\nfor dots-hyprland.")
        ii_desc.set_justify(Gtk.Justification.CENTER)
        ii_col.pack_start(ii_desc, False, False, 0)
        flavors.pack_start(ii_col, False, False, 0)

        # ii-vynx column
        vynx_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vynx_btn = Gtk.Button(label="ii-vynx (Vaguesyntax)")
        vynx_btn.set_size_request(200, 100)
        vynx_btn.connect("clicked", self._on_vynx_selected)
        vynx_col.pack_start(vynx_btn, False, False, 0)
        vynx_desc = Gtk.Label(label="Advanced Vynx flavor\nwith extra QOL.")
        vynx_desc.set_justify(Gtk.Justification.CENTER)
        vynx_col.pack_start(vynx_desc, False, False, 0)
        flavors.pack_start(vynx_col, False, False, 0)

        self.stack.add_named(box, "welcome")

    def _init_settings_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        box.set_border_width(30)
        box.set_valign(Gtk.Align.CENTER)

        label = Gtk.Label()
        label.set_markup("<span size='large' weight='bold'>Quick Settings</span>")
        box.pack_start(label, False, False, 0)

        self.cb_notify = Gtk.CheckButton.new_with_label("Enable Desktop Notifications")
        self.cb_notify.set_active(True)
        box.pack_start(self.cb_notify, False, False, 0)

        self.cb_fish = Gtk.CheckButton.new_with_label("Keep Fish Config (Backup/Restore ~/.config/fish)")
        self.cb_fish.set_active(False)
        self.cb_fish.set_tooltip_text("Recommended if you have custom fish configurations.")
        box.pack_start(self.cb_fish, False, False, 0)

        self.cb_pty = Gtk.CheckButton.new_with_label("Use PTY for better terminal output")
        self.cb_pty.set_active(True)
        box.pack_start(self.cb_pty, False, False, 0)

        refresh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        refresh_box.pack_start(Gtk.Label(label="Auto-refresh (seconds):"), False, False, 0)
        self.refresh_spin = Gtk.SpinButton.new_with_range(10, 3600, 10)
        self.refresh_spin.set_value(60)
        refresh_box.pack_start(self.refresh_spin, False, False, 0)
        box.pack_start(refresh_box, False, False, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.pack_end(btn_box, False, False, 0)

        back_btn = Gtk.Button(label="Back")
        back_btn.connect("clicked", lambda _b: self.stack.set_visible_child_name("welcome"))
        btn_box.pack_start(back_btn, False, False, 0)

        next_btn = Gtk.Button(label="Start Installation")
        next_btn.get_style_context().add_class("suggested-action")
        next_btn.connect("clicked", self._on_settings_next)
        btn_box.pack_end(next_btn, True, True, 0)

        self.stack.add_named(box, "settings")

    def _init_install_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(20)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.install_label = Gtk.Label()
        self.install_label.set_markup("<span weight='bold'>Installation Progress</span>")
        header.pack_start(self.install_label, False, False, 0)

        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner, False, False, 0)

        self.progress_label = Gtk.Label(label="Initializing...")
        self.progress_label.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_end(self.progress_label, True, True, 0)
        
        box.pack_start(header, False, False, 0)

        # Embedded Console
        self.console = ConsolePanel(settings=self.settings)
        # We don't need the revealer to be toggleable here, just show it
        self.console.revealer.set_reveal_child(True)
        box.pack_start(self.console.revealer, True, True, 0)

        self.finish_btn = Gtk.Button(label="Finish")
        self.finish_btn.get_style_context().add_class("suggested-action")
        self.finish_btn.set_sensitive(False)
        self.finish_btn.connect("clicked", lambda _b: self._finish_onboarding())
        box.pack_end(self.finish_btn, False, False, 0)

        self.stack.add_named(box, "install")

    def _on_settings_next(self, _btn):
        self.settings["send_notifications"] = self.cb_notify.get_active()
        self.settings["keep_fish_config"] = self.cb_fish.get_active()
        self.settings["use_pty"] = self.cb_pty.get_active()
        self.settings["auto_refresh_seconds"] = int(self.refresh_spin.get_value())
        
        if self.selected_flavor == "ii":
            dotfiles_path = os.path.expanduser("~/.cache/dots-hyprland")
            if os.path.isdir(dotfiles_path):
                self.repo_path = dotfiles_path
                self._finish_onboarding()
                return

        self._start_install(self.selected_flavor)

    def _on_ii_selected(self, _btn):
        self.selected_flavor = "ii"
        self.stack.set_visible_child_name("settings")

    def _on_vynx_selected(self, _btn):
        self.selected_flavor = "ii-vynx"
        self.stack.set_visible_child_name("settings")

    def _start_install(self, flavor):
        self.stack.set_visible_child_name("install")
        self.spinner.start()
        threading.Thread(target=self._install_worker, args=(flavor,), daemon=True).start()

    def _install_worker(self, flavor):
        try:
            if flavor == "ii":
                GLib.idle_add(self.progress_label.set_text, "Running ii installation...")
                cmd = ["bash", "-c", "bash <(curl -s https://ii.clsty.link/get)"]
                self.repo_path = os.path.expanduser("~/.cache/dots-hyprland")
                GLib.idle_add(lambda: self.console.run_command(cmd, cwd=os.path.expanduser("~"), on_finished=self._on_vte_finished))
            
            elif flavor == "ii-vynx":
                GLib.idle_add(self.progress_label.set_text, "Installing ii-vynx...")
                repo_dir = os.path.expanduser("~/ii-vynx")
                self.repo_path = repo_dir
                
                script = f"bash <(curl -s https://ii.clsty.link/get) && if [ ! -d {repo_dir} ]; then git clone https://github.com/vaguesyntax/ii-vynx.git {repo_dir} --recurse-submodules; fi && cd {repo_dir} && ./setup-ii-vynx.sh"
                cmd = ["bash", "-c", script]
                
                self.settings["installer_mode"] = "full"
                GLib.idle_add(lambda: self.console.run_command(cmd, cwd=os.path.expanduser("~"), on_finished=self._on_vte_finished))

        except Exception as e:
            GLib.idle_add(self._show_error, str(e))

    def _on_vte_finished(self, status):
        if status == 0 and os.path.isdir(self.repo_path):
            GLib.idle_add(self._on_install_complete)
        else:
            GLib.idle_add(self._show_error, f"Installation finished with status {status}. Please check the console output above.")

    def _on_install_complete(self):
        self.spinner.stop()
        self.progress_label.set_text("Installation complete!")
        self.finish_btn.set_sensitive(True)

    def _show_error(self, message):
        self.spinner.stop()
        self.progress_label.set_text(f"Error: {message}")
        btn = Gtk.Button(label="Go Back")
        btn.connect("clicked", lambda _b: self.stack.set_visible_child_name("welcome"))
        self.get_content_area().pack_end(btn, False, False, 0)
        btn.show()

    def _finish_onboarding(self):
        if self.repo_path and os.path.isdir(self.repo_path):
            self.settings["repo_path"] = self.repo_path
        self.settings["onboarding_shown"] = True
        save_settings(self.settings)
        self.response(Gtk.ResponseType.OK)


def show_onboarding_dialog(parent, settings):
    dialog = OnboardingDialog(parent, settings)
    resp = dialog.run()
    dialog.destroy()
    return resp == Gtk.ResponseType.OK
