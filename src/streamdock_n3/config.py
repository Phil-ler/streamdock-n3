"""Config IO: load/save the user's runtime config from XDG_CONFIG_HOME."""

from __future__ import annotations

import copy
import json
import os
import re
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any

from streamdock_n3 import paths, terminals

_ACTION_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")

DEFAULT_CONFIG: dict[str, Any] = {
    "brightness": 80,
    "grab_evdev": True,
    "theme": "system",
    "terminal": "auto",
    "pages": [
        {
            "name": "Apps",
            "keys": {
                "1": {"label": "Terminal", "color": "#1c63b8"},
                "2": {"label": "Browser",  "color": "#188452"},
                "3": {"label": "Files",    "color": "#b55324"},
                "4": {"label": "Music",    "color": "#8444a8"},
                "5": {"label": "Chat",     "color": "#327a8a"},
                "6": {"label": "Steam",    "color": "#ae365c"},
            },
            "actions": {
                "button.1.press": {"type": "terminal"},
                "button.2.press": "xdg-open https://",
                "button.3.press": "xdg-open \"$HOME\"",
                "button.4.press": "strawberry",
                "button.5.press": "telegram-desktop",
                "button.6.press": "/usr/bin/steam",
            },
        },
        {
            "name": "Dev",
            "keys": {
                "1": {"label": "VSCode",   "color": "#007acc"},
                "2": {"label": "Terminal", "color": "#1c63b8"},
                "3": {"label": "Browser",  "color": "#188452"},
                "4": {"label": "git pull", "color": "#e06c75"},
                "5": {"label": "git push", "color": "#56b6c2"},
                "6": {"label": "git log",  "color": "#d19a66"},
            },
            "actions": {
                "button.1.press": "code",
                "button.2.press": {"type": "terminal"},
                "button.3.press": "xdg-open https://",
                "button.4.press": {
                    "type": "shell",
                    "command": "git pull",
                    "show_output": True,
                },
                "button.5.press": {
                    "type": "shell",
                    "command": "git push",
                    "show_output": True,
                },
                "button.6.press": {
                    "type": "shell",
                    "command": "git log --oneline -20",
                    "show_output": True,
                },
            },
        },
        {
            "name": "System",
            "keys": {
                "1": {"label": "Screenshot", "color": "#e5c07b"},
                "2": {"label": "Recorder",   "color": "#e06c75"},
                "3": {"label": "OBS",        "color": "#8444a8"},
                "4": {"label": "Monitor",    "color": "#56b6c2"},
                "5": {"label": "Reboot",     "color": "#be5046"},
                "6": {"label": "Shutdown",   "color": "#ff0000"},
            },
            "actions": {
                "button.1.press": "flameshot gui",
                "button.2.press": "simplescreenrecorder",
                "button.3.press": "obs",
                "button.4.press": {
                    "type": "shell",
                    "command": "btop",
                    "show_output": True,
                },
                "button.5.press": "systemctl reboot",
                "button.6.press": "systemctl poweroff",
            },
        },
    ],
    "actions": {
        "button.7.press": "__page:next__",
        "button.8.press": "__page:first__",
        "button.9.press": "__page:prev__",
        "knob.1.left":  "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
        "knob.1.right": "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
        "knob.1.press": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
        "knob.2.left":  "playerctl previous",
        "knob.2.right": "playerctl next",
        "knob.2.press": "playerctl play-pause",
        "knob.3.left":  "wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 5%-",
        "knob.3.right": "wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 5%+",
        "knob.3.press": "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle",
        "evdev.KEY_VOLUMEDOWN.press":  "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-",
        "evdev.KEY_VOLUMEUP.press":    "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+",
        "evdev.KEY_MUTE.press":        "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
        "evdev.KEY_PREVIOUSSONG.press": "playerctl previous",
        "evdev.KEY_NEXTSONG.press":    "playerctl next",
        "evdev.KEY_PLAYPAUSE.press":   "playerctl play-pause",
    },
}


def _shipped_default_text() -> str | None:
    """Return the packaged default config, or None if it cannot be read.

    Reads through the Traversable rather than resources.as_file: as_file may
    extract to a temp file that is unlinked when its context exits, so a path
    returned from inside that context is already gone by the time a caller
    opens it.
    """
    try:
        ref = resources.files("streamdock_n3").joinpath("_data/config.default.json")
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


def _write_atomic(text: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, target)


def ensure_config(path: Path | None = None) -> Path:
    """Create the config file with sane defaults if missing. Returns the path."""
    target = path or paths.config_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    shipped = _shipped_default_text()
    if shipped is not None:
        _write_atomic(shipped, target)
        return target
    save(DEFAULT_CONFIG, target)
    return target


def load(path: Path | None = None) -> dict[str, Any]:
    target = path or paths.config_file()
    if not target.exists():
        ensure_config(target)
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    return data


def save(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or paths.config_file()
    _write_atomic(json.dumps(data, indent=2, ensure_ascii=False) + "\n", target)

def ensure_terminal_setting(config: dict[str, Any], path: Path | None = None) -> str:
    """Resolve and persist the detected system terminal on first startup."""
    if config.get("terminal") == "auto":
        detected = terminals.detect_default_terminal()
        if detected:
            config["terminal"] = detected
            save(config, path)
    return str(config.get("terminal", "auto"))


def _validate_action_id(action_id: str) -> str:
    if not isinstance(action_id, str) or not _ACTION_ID_PATTERN.fullmatch(action_id):
        raise ValueError(f"invalid action ID: {action_id!r}")
    return action_id


def list_action_templates() -> list[dict[str, Any]]:
    template_dir = resources.files("streamdock_n3").joinpath("_data/action_templates")
    templates = []
    for resource in sorted(template_dir.iterdir(), key=lambda item: item.name):
        if not resource.is_file() or not resource.name.endswith(".json"):
            continue
        template = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(template, dict) or not isinstance(template.get("action"), dict):
            raise ValueError(f"invalid action template: {resource.name}")
        template_id = resource.name[:-5]
        _validate_action_id(template_id)
        templates.append({"id": template_id, **template})
    return templates


def _load_action_template(template_id: str) -> dict[str, Any]:
    template_id = _validate_action_id(template_id)
    resource = (
        resources.files("streamdock_n3")
        .joinpath("_data/action_templates")
        .joinpath(f"{template_id}.json")
    )
    try:
        template = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"unknown action template: {template_id}") from exc
    if not isinstance(template, dict) or not isinstance(template.get("action"), dict):
        raise ValueError(f"invalid action template: {template_id}")
    return template


def load_user_action(action_id: str, action_dir: Path | None = None) -> dict[str, Any]:
    action_id = _validate_action_id(action_id)
    target = (action_dir or paths.action_dir()) / f"{action_id}.json"
    with target.open("r", encoding="utf-8") as handle:
        action = json.load(handle)
    if not isinstance(action, dict):
        raise ValueError(f"action {action_id!r} must be a JSON object")
    return action


def save_user_action(
    action_id: str,
    action: dict[str, Any],
    action_dir: Path | None = None,
) -> Path:
    action_id = _validate_action_id(action_id)
    if not isinstance(action, dict):
        raise ValueError("user action must be a JSON object")
    target = (action_dir or paths.action_dir()) / f"{action_id}.json"
    _write_atomic(json.dumps(action, indent=2, ensure_ascii=False) + "\n", target)
    return target


def copy_action_template(
    template_id: str,
    action_id: str | None = None,
    action_dir: Path | None = None,
) -> str:
    template = _load_action_template(template_id)
    action_id = _validate_action_id(action_id or template_id)
    target_dir = action_dir or paths.action_dir()
    target = target_dir / f"{action_id}.json"
    if target.exists():
        raise FileExistsError(target)
    action = dict(template["action"])
    action["name"] = str(template.get("name", action_id))
    icon_resource = template.get("icon")
    if icon_resource is not None:
        if not isinstance(icon_resource, str):
            raise ValueError(f"invalid icon resource in template: {template_id}")
        relative_icon = PurePosixPath(icon_resource)
        if relative_icon.is_absolute() or ".." in relative_icon.parts:
            raise ValueError(f"invalid icon resource in template: {template_id}")
        resource = resources.files("streamdock_n3")
        for part in relative_icon.parts:
            resource = resource.joinpath(part)
        icon_target = target_dir / "assets" / f"{action_id}{relative_icon.suffix}"
        icon_target.parent.mkdir(parents=True, exist_ok=True)
        icon_target.write_bytes(resource.read_bytes())
        action["icon"] = str(icon_target)
    save_user_action(action_id, action, target_dir)
    return action_id


def resolve_action_references(action: Any, action_dir: Path | None = None) -> Any:
    def resolve(value: Any, active_ids: frozenset[str]) -> Any:
        if isinstance(value, list):
            return [resolve(item, active_ids) for item in value]
        if not isinstance(value, dict):
            return value

        if value.get("type") == "reference":
            action_id = _validate_action_id(value.get("id"))
            if action_id in active_ids:
                raise ValueError(f"cyclic action reference: {action_id}")
            try:
                user_action = load_user_action(action_id, action_dir)
            except FileNotFoundError as exc:
                raise ValueError(f"action reference not found: {action_id}") from exc
            return resolve(user_action, active_ids | {action_id})

        if value.get("type") == "sequence" and isinstance(value.get("steps"), list):
            resolved = dict(value)
            resolved["steps"] = [resolve(step, active_ids) for step in value["steps"]]
            return resolved
        return value

    return resolve(action, frozenset())


def _migrate_terminal_actions(actions: dict[str, Any]) -> None:
    for event, action in list(actions.items()):
        if isinstance(action, str):
            if action.startswith("Action: "):
                action_id = action.removeprefix("Action: ").strip()
                try:
                    _validate_action_id(action_id)
                except ValueError:
                    continue
                actions[event] = {"type": "reference", "id": action_id}
                continue
            migrated = terminals.migrate_legacy_terminal_command(action)
            if migrated is not None:
                actions[event] = migrated


def normalize(config: dict[str, Any]) -> dict[str, Any]:
    """Coerce a loaded config into the shape the daemon and GUI assume.

    A hand-edited file can hold junk — a string where a key object belongs, a
    missing "keys" object. The daemon tolerated this field by field; the GUI
    builds widgets straight from these values, so it has to do the same or the
    window fails to construct. Doing it once, up front, keeps both honest.

    Mutates and returns `config`. Deliberately does not invent entries for
    absent LCD keys: callers that need one use setdefault, so "key present but
    unusable" and "key absent" stay distinguishable here.
    """
    if not isinstance(config.get("terminal"), str) or not config.get("terminal"):
        config["terminal"] = "auto"

    # Normalize root-level keys (legacy flat configs without pages)
    keys = config.get("keys")
    config["keys"] = {
        str(k): (v if isinstance(v, dict) else {})
        for k, v in (keys.items() if isinstance(keys, dict) else ())
    }

    # Normalize each page's keys and actions
    pages = config.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_keys = page.get("keys")
            page["keys"] = {
                str(k): (v if isinstance(v, dict) else {})
                for k, v in (page_keys.items() if isinstance(page_keys, dict) else ())
            }
            if not isinstance(page.get("actions"), dict):
                page["actions"] = {}
            _migrate_terminal_actions(page["actions"])

    if not isinstance(config.get("actions"), dict):
        config["actions"] = {}
    _migrate_terminal_actions(config["actions"])
    return config


def load_normalized(path: Path | None = None) -> dict[str, Any]:
    """Load, normalize, and persist one-time migrations for the runtime config."""
    data = load(path)
    original = copy.deepcopy(data)
    normalize(data)
    if data != original:
        save(data, path)
    return data


def action_map(config: dict[str, Any]) -> dict[str, Any]:
    actions = config.get("actions", {})
    return actions if isinstance(actions, dict) else {}
