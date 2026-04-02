import os

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk


def show_settings_dialog(
    window, SETTINGS, REPO_PATH, AUTO_REFRESH_SECONDS, _save_settings
) -> None:
    """
    Modern tabbed settings dialog with extensive options.
    """

    dialog = Gtk.Dialog(
        title="Settings",
        transient_for=window,
        flags=0,
    )
    dialog.set_default_size(700, 550)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save", Gtk.ResponseType.OK)

    content = dialog.get_content_area()
    content.set_border_width(0)
    
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    hbox.set_hexpand(True)
    hbox.set_vexpand(True)
    content.pack_start(hbox, True, True, 0)

    stack = Gtk.Stack()
    stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    stack.set_transition_duration(300)

    sidebar = Gtk.StackSidebar()
    sidebar.set_stack(stack)
    sidebar.set_size_request(180, -1)
    
    hbox.pack_start(sidebar, False, False, 0)
    hbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
    hbox.pack_start(stack, True, True, 0)

    def create_page(name, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(18)
        
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(box)
        
        stack.add_titled(sw, name, title)
        return box

    def add_setting(container, label, widget, tooltip=""):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_bottom(6)
        lbl = Gtk.Label(label=label)
        lbl.set_xalign(0.0)
        lbl.set_width_chars(28)
        if tooltip:
            lbl.set_tooltip_text(tooltip)
            widget.set_tooltip_text(tooltip)
        row.pack_start(lbl, False, False, 0)
        row.pack_start(widget, True, True, 0)
        container.pack_start(row, False, False, 0)

    def add_header(container, text):
        lbl = Gtk.Label()
        lbl.set_markup(f"<span weight='bold' size='large'>{text}</span>")
        lbl.set_xalign(0.0)
        lbl.set_margin_top(10)
        lbl.set_margin_bottom(5)
        container.pack_start(lbl, False, False, 0)

    # --- GENERAL PAGE ---
    gen_box = create_page("general", "General")
    add_header(gen_box, "Repository")

    entry_repo = Gtk.Entry()
    entry_repo.set_text(str(SETTINGS.get("repo_path", REPO_PATH) or ""))
    btn_repo = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
    repo_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    repo_container.pack_start(entry_repo, True, True, 0)
    repo_container.pack_start(btn_repo, False, False, 0)
    def browse_repo(_b):
        chooser = Gtk.FileChooserDialog(title="Select repository", transient_for=dialog, action=Gtk.FileChooserAction.SELECT_FOLDER)
        chooser.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Select", Gtk.ResponseType.OK)
        if chooser.run() == Gtk.ResponseType.OK:
            entry_repo.set_text(chooser.get_filename() or "")
        chooser.destroy()
    btn_repo.connect("clicked", browse_repo)
    add_setting(gen_box, "Repository path", repo_container)

    entry_refresh = Gtk.SpinButton.new_with_range(10, 3600, 10)
    entry_refresh.set_value(float(SETTINGS.get("auto_refresh_seconds", 60)))
    add_setting(gen_box, "Auto refresh (s)", entry_refresh)

    add_header(gen_box, "Updates")
    cmb_mode = Gtk.ComboBoxText()
    for m in ["files-only", "full", "auto"]: cmb_mode.append_text(m)
    current_mode = str(SETTINGS.get("installer_mode", "files-only"))
    cmb_mode.set_active(["files-only", "full", "auto"].index(current_mode) if current_mode in ["files-only", "full", "auto"] else 0)
    add_setting(gen_box, "Installer mode", cmb_mode)

    cb_auto_hide = Gtk.CheckButton.new_with_label("Hide console after success")
    cb_auto_hide.set_active(bool(SETTINGS.get("auto_hide_console", True)))
    add_setting(gen_box, "Auto-hide console", cb_auto_hide)

    # --- GIT PAGE ---
    git_box = create_page("git", "Git")
    add_header(git_box, "Syncing")
    
    cb_fetch_all = Gtk.CheckButton.new_with_label("Fetch all remotes")
    cb_fetch_all.set_active(bool(SETTINGS.get("git_fetch_all", True)))
    add_setting(git_box, "Fetch all", cb_fetch_all)

    cb_prune = Gtk.CheckButton.new_with_label("Prune remote branches")
    cb_prune.set_active(bool(SETTINGS.get("git_prune", True)))
    add_setting(git_box, "Prune remotes", cb_prune)

    cb_verbose_git = Gtk.CheckButton.new_with_label("Verbose git output")
    cb_verbose_git.set_active(bool(SETTINGS.get("verbose_git", False)))
    add_setting(git_box, "Verbose output", cb_verbose_git)

    # --- CONSOLE PAGE ---
    con_box = create_page("console", "Console")
    add_header(con_box, "Terminal Settings")

    entry_term = Gtk.Entry()
    entry_term.set_placeholder_text("Default (kitty, alacritty...)")
    entry_term.set_text(str(SETTINGS.get("terminal_emulator", "")))
    add_setting(con_box, "Terminal override", entry_term, "Command for external terminal")

    spin_font = Gtk.SpinButton.new_with_range(6, 32, 1)
    spin_font.set_value(float(SETTINGS.get("console_font_size", 12)))
    add_setting(con_box, "Font size", spin_font)

    cb_pty = Gtk.CheckButton.new_with_label("Use PTY allocation")
    cb_pty.set_active(bool(SETTINGS.get("use_pty", True)))
    add_setting(con_box, "PTY Mode", cb_pty)

    cb_detached = Gtk.CheckButton.new_with_label("External window by default")
    cb_detached.set_active(bool(SETTINGS.get("detached_console", False)))
    add_setting(con_box, "Detached console", cb_detached)

    spin_log = Gtk.SpinButton.new_with_range(0, 100000, 500)
    spin_log.set_value(float(SETTINGS.get("log_max_lines", 5000)))
    add_setting(con_box, "Max log lines", spin_log)

    # --- INTERFACE PAGE ---
    int_box = create_page("interface", "Interface")
    add_header(int_box, "Window")

    adj_opacity = Gtk.Adjustment(value=float(SETTINGS.get("window_opacity", 1.0)), lower=0.1, upper=1.0, step_increment=0.05)
    scale_opacity = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj_opacity)
    add_setting(int_box, "Window Opacity", scale_opacity)

    cb_confirm_exit = Gtk.CheckButton.new_with_label("Confirm before exit")
    cb_confirm_exit.set_active(bool(SETTINGS.get("confirm_on_exit", False)))
    add_setting(int_box, "Confirm exit", cb_confirm_exit)

    add_header(int_box, "Feedback")
    cb_notify = Gtk.CheckButton.new_with_label("Show desktop notifications")
    cb_notify.set_active(bool(SETTINGS.get("send_notifications", True)))
    add_setting(int_box, "Notifications", cb_notify)

    cb_lazy = Gtk.CheckButton.new_with_label("Animate & lazy-load commits")
    cb_lazy.set_active(bool(SETTINGS.get("changes_lazy_load", True)))
    add_setting(int_box, "Lazy loading", cb_lazy)

    cb_details_btn = Gtk.CheckButton.new_with_label("Show banner 'Details…' button")
    cb_details_btn.set_active(bool(SETTINGS.get("show_details_button", True)))
    add_setting(int_box, "Details button", cb_details_btn)

    # --- ADVANCED PAGE ---
    adv_box = create_page("advanced", "Advanced")
    add_header(adv_box, "Dotfiles Safety")
    
    cb_keep_fish = Gtk.CheckButton.new_with_label("Protect Fish configuration")
    cb_keep_fish.set_active(bool(SETTINGS.get("keep_fish_config", False)))
    add_setting(adv_box, "Keep fish config", cb_keep_fish, "Backup ~/.config/fish")

    add_header(adv_box, "Custom Scripts")
    entry_pre = Gtk.Entry(); entry_pre.set_text(str(SETTINGS.get("pre_script_path", "")))
    add_setting(adv_box, "Pre-install", entry_pre)
    entry_post = Gtk.Entry(); entry_post.set_text(str(SETTINGS.get("post_script_path", "")))
    add_setting(adv_box, "Post-install", entry_post)

    dialog.show_all()
    if dialog.run() == Gtk.ResponseType.OK:
        SETTINGS.update({
            "auto_refresh_seconds": int(entry_refresh.get_value()),
            "repo_path": entry_repo.get_text().strip(),
            "installer_mode": ["files-only", "full", "auto"][cmb_mode.get_active()],
            "auto_hide_console": cb_auto_hide.get_active(),
            "git_fetch_all": cb_fetch_all.get_active(),
            "git_prune": cb_prune.get_active(),
            "verbose_git": cb_verbose_git.get_active(),
            "terminal_emulator": entry_term.get_text().strip(),
            "console_font_size": int(spin_font.get_value()),
            "use_pty": cb_pty.get_active(),
            "detached_console": cb_detached.get_active(),
            "log_max_lines": int(spin_log.get_value()),
            "window_opacity": scale_opacity.get_value(),
            "confirm_on_exit": cb_confirm_exit.get_active(),
            "send_notifications": cb_notify.get_active(),
            "changes_lazy_load": cb_lazy.get_active(),
            "show_details_button": cb_details_btn.get_active(),
            "keep_fish_config": cb_keep_fish.get_active(),
            "pre_script_path": entry_pre.get_text().strip(),
            "post_script_path": entry_post.get_text().strip(),
        })
        _save_settings(SETTINGS)
        window.set_opacity(SETTINGS["window_opacity"])
        window.refresh_status()
    dialog.destroy()
