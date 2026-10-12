from __future__ import annotations

import json

from streamdock_n3 import config as configmod


def test_action_map_returns_dict():
    assert configmod.action_map({"actions": {"a": "b"}}) == {"a": "b"}
    assert configmod.action_map({}) == {}
    assert configmod.action_map({"actions": "nonsense"}) == {}


def test_normalize_migrates_hardcoded_terminal_commands():
    normalized = configmod.normalize(
        {
            "actions": {
                "button.1.press": "alacritty",
                "button.2.press": "alacritty -e bash -c 'git pull; read'",
                "button.3.press": "git status",
            },
            "pages": [
                {
                    "actions": {
                        "button.4.press": "alacritty -e btop",
                    }
                }
            ],
        }
    )

    assert normalized["terminal"] == "auto"
    assert normalized["actions"]["button.1.press"] == {"type": "terminal"}
    assert normalized["actions"]["button.2.press"] == {
        "type": "shell",
        "command": "git pull",
        "show_output": True,
    }
    assert normalized["actions"]["button.3.press"] == "git status"
    assert normalized["pages"][0]["actions"]["button.4.press"] == {
        "type": "shell",
        "command": "btop",
        "show_output": True,
    }


def test_load_normalized_migrates_and_persists_action_summary(tmp_path):
    target = tmp_path / "config.json"
    configmod.save(
        {
            "terminal": "konsole",
            "pages": [{"actions": {"button.1.press": "Action: git-pull"}}],
        },
        target,
    )

    normalized = configmod.load_normalized(target)

    reference = {"type": "reference", "id": "git-pull"}
    assert normalized["pages"][0]["actions"]["button.1.press"] == reference
    persisted = json.loads(target.read_text())
    assert persisted["pages"][0]["actions"]["button.1.press"] == reference


def test_ensure_terminal_setting_persists_detected_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(configmod.terminals, "detect_default_terminal", lambda: "konsole")
    config = {"terminal": "auto", "actions": {}}

    assert configmod.ensure_terminal_setting(config, tmp_path / "config.json") == "konsole"
    assert configmod.load(tmp_path / "config.json")["terminal"] == "konsole"


def test_action_templates_can_be_copied_to_user_directory(tmp_path):
    templates = configmod.list_action_templates()
    assert any(template["id"] == "git-pull" for template in templates)

    action_id = configmod.copy_action_template("git-pull", action_dir=tmp_path)

    assert action_id == "git-pull"
    action = configmod.load_user_action(action_id, tmp_path)
    assert action["type"] == "shell"
    assert action["command"] == "git pull"
    assert action["cwd"] == ""
    assert action["show_output"] is True
    assert action["name"] == "Git pull"
    copied_icon = tmp_path / "assets/git-pull.png"
    assert action["icon"] == str(copied_icon)
    assert copied_icon.read_bytes() == (
        configmod.resources.files("streamdock_n3").joinpath("img/git_pull.png").read_bytes()
    )


def test_action_reference_resolves_user_action_and_nested_steps(tmp_path):
    configmod.save_user_action(
        "git-pull",
        {"name": "Git pull", "type": "shell", "command": "git pull"},
        tmp_path,
    )

    resolved = configmod.resolve_action_references(
        {
            "type": "sequence",
            "steps": [{"type": "reference", "id": "git-pull"}],
        },
        tmp_path,
    )

    assert resolved["steps"] == [
        {"name": "Git pull", "type": "shell", "command": "git pull"}
    ]


def test_action_reference_rejects_traversal_and_cycles(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="invalid action ID"):
        configmod.resolve_action_references({"type": "reference", "id": "../secret"}, tmp_path)

    configmod.save_user_action("first", {"type": "reference", "id": "second"}, tmp_path)
    configmod.save_user_action("second", {"type": "reference", "id": "first"}, tmp_path)
    with pytest.raises(ValueError, match="cyclic action reference"):
        configmod.resolve_action_references({"type": "reference", "id": "first"}, tmp_path)


def test_ensure_config_creates_default(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr("streamdock_n3.paths.config_file", lambda: cfg_path)
    configmod.ensure_config()
    assert cfg_path.is_file()
    data = json.loads(cfg_path.read_text())
    assert "brightness" in data
    assert "keys" in data
    assert "actions" in data


def test_load_then_save_roundtrip(tmp_path):
    cfg = {"brightness": 42, "keys": {"1": {"label": "A"}}, "actions": {"button.1.press": "echo"}}
    target = tmp_path / "x.json"
    configmod.save(cfg, target)
    assert configmod.load(target) == cfg


def test_load_rejects_non_object(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text("[]")
    import pytest
    with pytest.raises(ValueError):
        configmod.load(target)


def test_normalize_replaces_missing_keys_object():
    cfg = configmod.normalize({})
    assert cfg["keys"] == {}
    assert cfg["actions"] == {}


def test_normalize_coerces_non_dict_entries():
    cfg = configmod.normalize({"keys": {"1": "Term", "2": {"label": "Web"}}})
    assert cfg["keys"] == {"1": {}, "2": {"label": "Web"}}


def test_normalize_coerces_non_dict_containers():
    cfg = configmod.normalize({"keys": "nonsense", "actions": []})
    assert cfg["keys"] == {}
    assert cfg["actions"] == {}


def test_normalize_stringifies_integer_key_ids():
    cfg = configmod.normalize({"keys": {1: {"label": "A"}}})
    assert cfg["keys"] == {"1": {"label": "A"}}


def test_normalize_preserves_valid_config():
    original = {
        "brightness": 42,
        "terminal": "auto",
        "keys": {"1": {"label": "A"}},
        "actions": {"x": "y"},
    }
    assert configmod.normalize(dict(original)) == original


def test_shipped_default_is_readable_and_valid():
    """ensure_config's primary path: the packaged default must parse."""
    text = configmod._shipped_default_text()
    assert text is not None
    data = json.loads(text)
    assert set(data) >= {"brightness", "keys", "actions"}
    assert set(data["keys"]) == {"1", "2", "3", "4", "5", "6"}


def test_ensure_config_seeds_from_shipped_default(tmp_path):
    target = tmp_path / "config.json"
    configmod.ensure_config(target)
    assert json.loads(target.read_text()) == json.loads(configmod._shipped_default_text())
    assert not list(tmp_path.glob("*.tmp")), "atomic write left a temp file behind"


def test_ensure_config_falls_back_when_shipped_default_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(configmod, "_shipped_default_text", lambda: None)
    target = tmp_path / "config.json"
    configmod.ensure_config(target)
    assert json.loads(target.read_text()) == configmod.DEFAULT_CONFIG


def test_ensure_config_does_not_clobber_existing(tmp_path):
    target = tmp_path / "config.json"
    target.write_text('{"brightness": 5}')
    configmod.ensure_config(target)
    assert json.loads(target.read_text()) == {"brightness": 5}
