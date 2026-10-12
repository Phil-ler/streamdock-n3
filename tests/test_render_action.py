from __future__ import annotations

import pytest

from tests.gui_source import load_gui_function

render_action = load_gui_function("render_action")


def test_plain_string_is_unchanged():
    assert render_action("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle") == (
        "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
    )


def test_list_joins_with_semicolon_not_and():
    # "&&" would make the second command depend on the first succeeding;
    # run_actions launches them independently.
    assert render_action(["cmd a", "cmd b"]) == "cmd a; cmd b"


def test_dict_uses_command_field():
    assert render_action({"command": "obs"}) == "obs"
    assert render_action({"nothing": "here"}) == ""
    assert render_action({"type": "terminal"}) == "Open selected terminal"


def test_structured_actions_render_for_the_entry():
    assert render_action({"type": "launch", "argv": ["code", "--reuse-window"]}) == (
        "code --reuse-window"
    )
    assert render_action({"type": "open_url", "url": "https://example.com"}) == (
        "https://example.com"
    )
    assert render_action({"type": "sequence", "steps": ["one", "two"]}) == (
        "Sequence (2 steps)"
    )
    assert render_action({"type": "reference", "id": "git-pull"}) == (
        "Action: git-pull"
    )


def test_build_action_creates_structured_values():
    build_action = load_gui_function("build_action")
    assert build_action("terminal", "") == {"type": "terminal"}
    assert build_action("launch", 'code "a project"') == {
        "type": "launch",
        "argv": ["code", "a project"],
    }
    assert build_action("open_url", "https://example.com") == {
        "type": "open_url",
        "url": "https://example.com",
    }
    assert build_action("shell", "  echo hello  ") == "echo hello"
    assert build_action("shell", "git pull", "/home/user/project") == {
        "type": "shell",
        "command": "git pull",
        "cwd": "/home/user/project",
    }
    assert build_action("shell", "git pull", "/home/user/project", True) == {
        "type": "shell",
        "command": "git pull",
        "cwd": "/home/user/project",
        "show_output": True,
    }


def test_build_action_rejects_invalid_launch_input():
    build_action = load_gui_function("build_action")
    with pytest.raises(ValueError):
        build_action("launch", 'code "unfinished')


def test_action_id_from_name_creates_a_safe_slug():
    action_id_from_name = load_gui_function("action_id_from_name")
    assert action_id_from_name("Git Pull: Project One") == "git-pull-project-one"
    assert action_id_from_name(" !!! ") == "action"


def test_list_of_dicts_does_not_raise():
    # This shape is legal for run_actions; " && ".join used to raise TypeError
    # here, which happened during window construction and blocked GUI startup.
    assert render_action([{"command": "x"}, "y"]) == "x; y"


def test_missing_and_odd_values_degrade():
    assert render_action("") == ""
    assert render_action(None) == ""
    assert render_action(42) == "42"
