from __future__ import annotations

from streamdock_n3 import terminals


def test_choose_default_terminal_uses_user_and_desktop_preferences():
    available = ["konsole", "alacritty", "xterm"]
    assert terminals.choose_default_terminal(
        available,
        terminal_env="/usr/bin/alacritty",
        desktop="KDE",
        kde_preference="konsole",
    ) == "alacritty"
    assert terminals.choose_default_terminal(
        available,
        desktop="KDE",
        kde_preference="konsole",
    ) == "konsole"


def test_choose_default_terminal_falls_back_to_detected_choices():
    assert terminals.choose_default_terminal(["konsole", "xterm"]) == "konsole"
    assert terminals.choose_default_terminal([]) is None


def test_terminal_desktop_service_id_is_recognized():
    assert terminals.terminal_id_for_command("org.kde.konsole.desktop") == "konsole"


def test_detect_default_terminal_uses_terminal_environment(monkeypatch):
    monkeypatch.setattr(
        terminals,
        "available_terminals",
        lambda _path: [terminals.Terminal("konsole", "Konsole", "konsole", "konsole")],
    )
    monkeypatch.setattr(terminals, "_read_kde_preference", lambda: None)

    assert terminals.detect_default_terminal(
        environ={"TERMINAL": "konsole", "XDG_CURRENT_DESKTOP": "KDE"}
    ) == "konsole"


def test_terminal_argv_runs_shell_in_detected_terminal(monkeypatch):
    monkeypatch.setattr(
        terminals,
        "available_terminals",
        lambda _path: [terminals.Terminal("konsole", "Konsole", "konsole", "konsole")],
    )
    monkeypatch.setattr(terminals.shutil, "which", lambda _app, path=None: "/usr/bin/konsole")

    argv = terminals.terminal_argv(
        "konsole",
        "git pull",
        cwd="/home/user/my project",
        title="Git pull",
    )

    assert argv[:3] == ["/usr/bin/konsole", "--title", "Git pull"]
    assert argv[3:6] == ["-e", "/bin/bash", "-lc"]
    assert "cd -- '/home/user/my project'" in argv[-1]
    assert "git pull" in argv[-1]
    assert "Press Enter to close this terminal" in argv[-1]


def test_legacy_terminal_commands_migrate_to_configured_terminal_actions():
    assert terminals.migrate_legacy_terminal_command("alacritty") == {
        "type": "terminal"
    }
    migrated = terminals.migrate_legacy_terminal_command(
        "alacritty -e bash -c 'git pull; read'"
    )
    assert migrated == {
        "type": "shell",
        "command": "git pull",
        "show_output": True,
    }
    assert terminals.migrate_legacy_terminal_command("git pull") is None
