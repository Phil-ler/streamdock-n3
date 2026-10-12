from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Terminal:
    id: str
    label: str
    executable: str
    style: str


_TERMINALS = (
    Terminal("konsole", "Konsole", "konsole", "konsole"),
    Terminal("alacritty", "Alacritty", "alacritty", "execute"),
    Terminal("kitty", "kitty", "kitty", "direct"),
    Terminal("foot", "foot", "foot", "direct"),
    Terminal("ghostty", "Ghostty", "ghostty", "execute"),
    Terminal("gnome-terminal", "GNOME Terminal", "gnome-terminal", "gnome"),
    Terminal("kgx", "GNOME Console", "kgx", "gnome"),
    Terminal("xfce4-terminal", "Xfce Terminal", "xfce4-terminal", "xfce"),
    Terminal("mate-terminal", "MATE Terminal", "mate-terminal", "gnome"),
    Terminal("tilix", "Tilix", "tilix", "execute"),
    Terminal("terminator", "Terminator", "terminator", "terminator"),
    Terminal("qterminal", "QTerminal", "qterminal", "execute"),
    Terminal("lxterminal", "LXTerminal", "lxterminal", "execute"),
    Terminal("xterm", "xterm", "xterm", "xterm"),
    Terminal("urxvt", "URxvt", "urxvt", "xterm"),
    Terminal("wezterm", "WezTerm", "wezterm", "wezterm"),
)

_DESKTOP_DEFAULTS = (
    ("KDE", ("konsole",)),
    ("GNOME", ("gnome-terminal", "kgx", "kitty", "foot")),
    ("XFCE", ("xfce4-terminal", "xterm")),
    ("MATE", ("mate-terminal", "xfce4-terminal", "xterm")),
    ("LXQT", ("qterminal", "konsole", "xterm")),
    ("LXDE", ("lxterminal", "xterm")),
    ("HYPRLAND", ("alacritty", "kitty", "foot", "konsole")),
    ("SWAY", ("foot", "alacritty", "kitty", "konsole")),
)
_DESKTOP_IDS = {
    "org.kde.konsole": "konsole",
    "org.gnome.terminal": "gnome-terminal",
    "org.gnome.console": "kgx",
    "org.wezfurlong.wezterm": "wezterm",
}


def available_terminals(path: str | None = None) -> list[Terminal]:
    found: list[Terminal] = []
    resolved_paths: set[str] = set()
    for terminal in _TERMINALS:
        executable = shutil.which(terminal.executable, path=path)
        if executable is None:
            continue
        resolved = os.path.realpath(executable)
        if resolved in resolved_paths:
            continue
        resolved_paths.add(resolved)
        found.append(terminal)
    return found


def terminal_id_for_command(command: str | None) -> str | None:
    if not command:
        return None
    try:
        first_word = shlex.split(command)[0]
    except (ValueError, IndexError):
        return None
    executable = Path(first_word).name
    if executable.endswith(".desktop"):
        desktop_id = executable[:-8]
        if desktop_id in _DESKTOP_IDS:
            return _DESKTOP_IDS[desktop_id]
    for terminal in _TERMINALS:
        if executable == terminal.executable:
            return terminal.id
    return None


def choose_default_terminal(
    available: Iterable[str],
    *,
    terminal_env: str | None = None,
    desktop: str = "",
    kde_preference: str | None = None,
    gnome_preference: str | None = None,
    alternative: str | None = None,
) -> str | None:
    available_ids = set(available)
    preferences = [terminal_env, kde_preference, gnome_preference, alternative]
    for preference in preferences:
        terminal_id = terminal_id_for_command(preference)
        if terminal_id in available_ids:
            return terminal_id

    desktop_upper = desktop.upper()
    for desktop_name, defaults in _DESKTOP_DEFAULTS:
        if desktop_name in desktop_upper:
            for terminal_id in defaults:
                if terminal_id in available_ids:
                    return terminal_id

    return next((terminal.id for terminal in _TERMINALS if terminal.id in available_ids), None)


def _read_kde_preference() -> str | None:
    for executable in ("kreadconfig6", "kreadconfig5"):
        if not shutil.which(executable):
            continue
        for key in ("TerminalApplication", "TerminalService"):
            try:
                result = subprocess.run(
                    [executable, "--file", "kdeglobals", "--group", "General", "--key", key],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            preference = result.stdout.strip()
            if preference:
                return preference
    return None


def _read_gnome_preference() -> str | None:
    if not shutil.which("gsettings"):
        return None
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.default-applications.terminal", "exec"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip().strip("'\"") if result.returncode == 0 else None


def detect_default_terminal(
    *,
    path: str | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    environ = os.environ if environ is None else environ
    available = available_terminals(path)
    ids = [terminal.id for terminal in available]

    kde_preference = None
    gnome_preference = None
    desktop = environ.get("XDG_CURRENT_DESKTOP", "")
    if "KDE" in desktop.upper():
        kde_preference = _read_kde_preference()
    if "GNOME" in desktop.upper():
        gnome_preference = _read_gnome_preference()

    alternative = None
    alternative_path = shutil.which("x-terminal-emulator", path=path)
    if alternative_path:
        alternative = os.path.realpath(alternative_path)

    return choose_default_terminal(
        ids,
        terminal_env=environ.get("TERMINAL"),
        desktop=desktop,
        kde_preference=kde_preference,
        gnome_preference=gnome_preference,
        alternative=alternative,
    )


def terminal_argv(
    terminal_id: str | None,
    command: str | None = None,
    *,
    cwd: str | None = None,
    title: str | None = None,
    path: str | None = None,
) -> list[str]:
    available = {terminal.id: terminal for terminal in available_terminals(path)}
    selected_id = terminal_id if terminal_id in available else detect_default_terminal(path=path)
    terminal = available.get(selected_id or "")
    if terminal is None:
        raise FileNotFoundError("No supported terminal emulator was detected")

    executable = shutil.which(terminal.executable, path=path)
    if executable is None:
        raise FileNotFoundError(f"Terminal emulator is not installed: {terminal.id}")
    argv = [executable]
    if title:
        if terminal.style in {"konsole", "execute"}:
            argv.extend(["--title", title])
        elif terminal.style == "xterm":
            argv.extend(["-T", title])
        elif terminal.style == "gnome":
            argv.append(f"--title={title}")

    if command is None:
        return argv

    script = []
    if cwd:
        expanded_cwd = os.path.expandvars(os.path.expanduser(cwd))
        script.append(f"cd -- {shlex.quote(expanded_cwd)} || exit $?\n")
    script.extend(
        [
            command,
            "action_status=$?",
            "printf '\\nCommand finished with exit code %s.\\n' \"$action_status\"",
            "read -r -p 'Press Enter to close this terminal...' _",
            'exit "$action_status"',
        ]
    )
    shell_command = "\n".join(script)
    shell = "/bin/bash" if os.path.exists("/bin/bash") else "/bin/sh"

    if terminal.style in {"konsole", "execute"}:
        argv.extend(["-e", shell, "-lc", shell_command])
    elif terminal.style == "direct":
        argv.extend([shell, "-lc", shell_command])
    elif terminal.style == "gnome":
        argv.extend(["--", shell, "-lc", shell_command])
    elif terminal.style == "xfce":
        argv.extend(["--execute", shell, "-lc", shell_command])
    elif terminal.style == "xterm":
        argv.extend(["-e", shell, "-lc", shell_command])
    elif terminal.style == "wezterm":
        argv.extend(["start", "--", shell, "-lc", shell_command])
    elif terminal.style == "terminator":
        argv.extend(["-x", shell, "-lc", shell_command])
    return argv


def migrate_legacy_terminal_command(command: str) -> dict[str, str | bool] | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts:
        return None
    terminal_id = terminal_id_for_command(parts[0])
    if terminal_id is None:
        return None
    if len(parts) == 1:
        return {"type": "terminal"}

    execution_flags = {"-e", "--execute", "-x"}
    flag_index = next(
        (index for index, part in enumerate(parts[1:], start=1) if part in execution_flags),
        None,
    )
    if flag_index is None:
        return None
    command_parts = parts[flag_index + 1 :]
    if not command_parts:
        return {"type": "terminal"}
    if len(command_parts) >= 3 and command_parts[0] in {"bash", "sh"} and command_parts[1] == "-c":
        migrated_command = re.sub(
            r"(?:;|\n)\s*read(?:\s+-r)?\s*$", "", command_parts[2]
        ).strip()
    else:
        migrated_command = shlex.join(command_parts)
    return {
        "type": "shell",
        "command": migrated_command,
        "show_output": True,
    }
