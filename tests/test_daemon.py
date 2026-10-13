from __future__ import annotations

import pytest

from streamdock_n3 import daemon
from streamdock_n3.daemon import wants_evdev_grab


def test_structured_shell_action_runs_command(monkeypatch):
    calls = []
    monkeypatch.setattr(
        daemon,
        "run_command",
        lambda command, *, dry_run: calls.append((command, dry_run)),
    )

    daemon.run_actions({"type": "shell", "command": "echo hello"}, dry_run=True)

    assert calls == [("echo hello", True)]


def test_shell_action_uses_working_directory(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        daemon.subprocess,
        "Popen",
        lambda argv, **kwargs: calls.append((argv, kwargs)),
    )

    daemon.run_actions(
        {"type": "shell", "command": "git pull", "cwd": str(tmp_path)},
        dry_run=False,
    )

    assert calls[0][1]["cwd"] == str(tmp_path)


def test_shell_action_uses_selected_terminal_for_output(monkeypatch):
    calls = []
    monkeypatch.setattr(daemon, "run_terminal_command", lambda command, **kwargs: calls.append((command, kwargs)))

    daemon.run_command(
        "git pull",
        dry_run=False,
        cwd="/repo",
        show_output=True,
        title="Git pull",
        terminal_id="konsole",
    )

    assert calls == [
        (
            "git pull",
            {
                "terminal_id": "konsole",
                "dry_run": False,
                "cwd": "/repo",
                "title": "Git pull",
                "env": daemon.os.environ.copy(),
            },
        )
    ]


def test_terminal_action_uses_saved_terminal_selection(monkeypatch):
    calls = []
    monkeypatch.setattr(daemon, "run_terminal_command", lambda command, **kwargs: calls.append((command, kwargs)))

    daemon.run_actions(
        {"type": "terminal", "command": "git status"},
        dry_run=True,
        terminal_id="konsole",
    )

    assert calls == [("git status", {"terminal_id": "konsole", "dry_run": True, "cwd": None, "title": None})]


def test_reference_runs_saved_user_action(monkeypatch, tmp_path):
    calls = []
    daemon.configmod.save_user_action(
        "git-pull",
        {
            "type": "shell",
            "command": "git pull",
            "cwd": str(tmp_path),
            "show_output": True,
            "name": "Git pull",
        },
        tmp_path,
    )
    monkeypatch.setattr(daemon.configmod.paths, "action_dir", lambda: tmp_path)
    monkeypatch.setattr(
        daemon,
        "run_command",
        lambda command, *, dry_run, cwd=None, show_output=False, title=None, terminal_id=None: calls.append(
            (command, cwd, show_output, title, terminal_id)
        ),
    )

    daemon.run_actions({"type": "reference", "id": "git-pull"}, dry_run=True)

    assert calls == [("git pull", str(tmp_path), True, "Git pull", None)]


@pytest.mark.parametrize(
    ("action", "expected_argv"),
    [
        ({"type": "launch", "argv": ["code", "--reuse-window"]}, ["code", "--reuse-window"]),
        ({"type": "open_url", "url": "https://example.com"}, ["xdg-open", "https://example.com"]),
    ],
)
def test_non_shell_actions_use_argv(monkeypatch, action, expected_argv):
    calls = []
    monkeypatch.setattr(
        daemon.subprocess,
        "Popen",
        lambda argv, **kwargs: calls.append((argv, kwargs)),
    )

    daemon.run_actions(action, dry_run=False)

    assert calls[0][0] == expected_argv
    assert calls[0][1]["shell"] is False


def test_sequence_schedules_steps_in_order_without_blocking(monkeypatch):
    calls = []
    scheduled = []

    class FakeTimer:
        def __init__(self, interval, function, args):
            self.interval = interval
            self.function = function
            self.args = args
            self.daemon = False

        def start(self):
            scheduled.append(self)

        def fire(self):
            self.function(*self.args)

    monkeypatch.setattr(daemon, "run_command", lambda command, *, dry_run: calls.append(command))
    monkeypatch.setattr(daemon.threading, "Timer", FakeTimer)

    daemon.run_actions(
        {
            "type": "sequence",
            "delay_ms": 250,
            "steps": [
                {"type": "shell", "command": "first"},
                {"type": "shell", "command": "second"},
                {"type": "shell", "command": "third"},
            ],
        },
        dry_run=False,
    )

    assert calls == ["first"]
    assert len(scheduled) == 1
    assert scheduled[0].interval == 0.25
    assert scheduled[0].daemon is True

    scheduled.pop(0).fire()
    assert calls == ["first", "second"]
    assert len(scheduled) == 1
    scheduled.pop(0).fire()
    assert calls == ["first", "second", "third"]
    assert scheduled == []


@pytest.mark.parametrize(
    "action",
    [
        {"type": "unknown"},
        {"type": "shell", "command": ""},
        {"type": "shell", "command": "git pull", "cwd": 42},
        {"type": "shell", "command": "git pull", "show_output": "yes"},
        {"type": "launch", "argv": []},
        {"type": "launch", "argv": ["code", 1]},
        {"type": "open_url", "url": ""},
        {"type": "sequence", "delay_ms": -1, "steps": []},
        {"type": "sequence", "delay_ms": 0, "steps": [42]},
    ],
)
def test_invalid_structured_action_fails_before_execution(action):
    with pytest.raises(ValueError):
        daemon.run_actions(action, dry_run=True)


def test_invalid_sequence_step_does_not_run_earlier_steps(monkeypatch):
    calls = []
    monkeypatch.setattr(daemon, "run_command", lambda command, *, dry_run: calls.append(command))

    with pytest.raises(ValueError):
        daemon.run_actions(
            {
                "type": "sequence",
                "delay_ms": 250,
                "steps": [{"type": "shell", "command": "first"}, 42],
            },
            dry_run=False,
        )

    assert calls == []


def test_grab_when_evdev_actions_present():
    assert wants_evdev_grab({"evdev.KEY_MUTE.press": "x"}, {}) is True


def test_no_grab_without_evdev_actions():
    assert wants_evdev_grab({"button.1.press": "x"}, {}) is False
    assert wants_evdev_grab({}, {}) is False


def test_grab_opt_out_via_config():
    actions = {"evdev.KEY_MUTE.press": "x"}
    assert wants_evdev_grab(actions, {"grab_evdev": False}) is False
    assert wants_evdev_grab(actions, {"grab_evdev": True}) is True
