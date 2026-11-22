"""Cross-platform OS controls for browser fallback, local video/audio apps, and volume."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import List, Optional, Tuple


def _run_quiet(cmd: list[str], timeout: float = 1.5) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _win32_vk(vk_code: int) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        KEYEVENTF_KEYUP = 0x0002
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def _friendly_mpris_name(bus_name: str) -> str:
    low = bus_name.lower()
    if "firefox" in low or "zen" in low or "librewolf" in low:
        return "Browser"
    if "chrom" in low or "brave" in low or "edge" in low:
        return "Browser"
    if "mpv" in low:
        return "mpv"
    if "vlc" in low:
        return "VLC"
    if "spotify" in low:
        return "Spotify"
    if "celluloid" in low:
        return "Celluloid"
    return bus_name.replace("org.mpris.MediaPlayer2.", "").split(".")[0].title()


class SystemController:
    """Adjusts OS master volume and controls browser/local desktop media players."""

    def __init__(self) -> None:
        self._last_mpris_dest: Optional[str] = None
        self.last_target_label: str = ""

    def get_system_volume_percent(self) -> Optional[int]:
        if sys.platform.startswith("linux"):
            if shutil.which("wpctl"):
                rc, out = _run_quiet(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
                if rc == 0 and "Volume:" in out:
                    try:
                        val = float(out.split("Volume:", 1)[1].strip().split()[0])
                        return max(0, min(150, round(val * 100)))
                    except ValueError:
                        pass
            if shutil.which("pactl"):
                rc, out = _run_quiet(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
                if rc == 0 and "%" in out:
                    for token in out.split():
                        if token.endswith("%"):
                            try:
                                return int(token.rstrip("%"))
                            except ValueError:
                                pass
        elif sys.platform == "darwin":
            rc, out = _run_quiet(["osascript", "-e", "output volume of (get volume settings)"])
            if rc == 0 and out.isdigit():
                return int(out)
        return None

    def adjust_volume(self, delta_percent: int) -> Tuple[bool, Optional[int]]:
        """Change OS audio volume by delta_percent (positive or negative)."""
        if delta_percent == 0:
            return True, self.get_system_volume_percent()

        if sys.platform.startswith("linux"):
            step = abs(int(delta_percent))
            sign = "+" if delta_percent > 0 else "-"
            if shutil.which("wpctl"):
                rc, _ = _run_quiet(
                    ["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{step}%{sign}"]
                )
                if rc == 0:
                    return True, self.get_system_volume_percent()
            if shutil.which("pactl"):
                rc, _ = _run_quiet(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{step}%"])
                if rc == 0:
                    return True, self.get_system_volume_percent()
            return False, None

        if sys.platform == "darwin":
            cur = self.get_system_volume_percent()
            cur = 50 if cur is None else cur
            target = max(0, min(100, cur + delta_percent))
            rc, _ = _run_quiet(["osascript", "-e", f"set volume output volume {target}"])
            return rc == 0, target if rc == 0 else None

        if sys.platform == "win32":
            vk = 0xAF if delta_percent > 0 else 0xAE
            presses = max(1, round(abs(delta_percent) / 2))
            ok = True
            for _ in range(presses):
                ok = _win32_vk(vk) and ok
            return ok, None

        return False, None

    def toggle_mute(self) -> bool:
        if sys.platform.startswith("linux"):
            if shutil.which("wpctl"):
                rc, _ = _run_quiet(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
                if rc == 0:
                    return True
            if shutil.which("pactl"):
                rc, _ = _run_quiet(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
                if rc == 0:
                    return True
            return False
        if sys.platform == "darwin":
            rc, _ = _run_quiet(
                ["osascript", "-e", "set volume output muted not (output muted of (get volume settings))"]
            )
            return rc == 0
        if sys.platform == "win32":
            return _win32_vk(0xAD)
        return False

    def _list_mpris_players(self) -> List[Tuple[str, str]]:
        """Return list of (bus_name, playback_status) via gdbus."""
        if not shutil.which("gdbus"):
            return []
        rc, names = _run_quiet(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.DBus",
                "--object-path",
                "/org/freedesktop/DBus",
                "--method",
                "org.freedesktop.DBus.ListNames",
            ]
        )
        if rc != 0:
            return []
        cleaned = (
            names.replace("(", " ")
            .replace(")", " ")
            .replace("[", " ")
            .replace("]", " ")
            .replace("'", " ")
            .replace(",", " ")
        )
        players: List[Tuple[str, str]] = []
        for token in cleaned.split():
            if not token.startswith("org.mpris.MediaPlayer2."):
                continue
            r2, st_out = _run_quiet(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    token,
                    "--object-path",
                    "/org/mpris/MediaPlayer2",
                    "--method",
                    "org.freedesktop.DBus.Properties.Get",
                    "org.mpris.MediaPlayer2.Player",
                    "PlaybackStatus",
                ]
            )
            status = "Unknown"
            if r2 == 0:
                if "Playing" in st_out:
                    status = "Playing"
                elif "Paused" in st_out:
                    status = "Paused"
                elif "Stopped" in st_out:
                    status = "Stopped"
            players.append((token, status))
        return players

    def _pick_hyprland_media_window(self) -> Optional[dict]:
        """Find the most recently focused media or browser window, skipping Hey Handy itself."""
        if not shutil.which("hyprctl"):
            return None
        rc, out = _run_quiet(["hyprctl", "clients", "-j"])
        if rc != 0 or not out:
            return None
        try:
            clients = json.loads(out)
        except json.JSONDecodeError:
            return None

        media_classes = (
            "mpv",
            "vlc",
            "celluloid",
            "totem",
            "zen",
            "firefox",
            "librewolf",
            "chromium",
            "google-chrome",
            "brave",
            "spotify",
        )
        best = None
        best_rank = (999, 999)
        for c in clients:
            cls = str(c.get("class") or "").lower()
            title = str(c.get("title") or "").lower()
            if "hey-handy" in cls or "hey handy" in title:
                continue
            focus_id = int(c.get("focusHistoryID") if c.get("focusHistoryID") is not None else 999)
            is_media = any(m in cls for m in media_classes)
            rank = (0 if is_media else 1, focus_id)
            if rank < best_rank:
                best_rank = rank
                best = c
        return best

    def fallback_media_action(self, action: str) -> bool:
        """Control desktop media players (Zen, Chrome, VLC, mpv, Spotify) without extension."""
        self.last_target_label = ""
        if sys.platform.startswith("linux"):
            if action in ("play_pause", "pause", "play"):
                players = self._list_mpris_players()
                if players:
                    # Prefer playing player when pausing/toggling; prefer last paused when resuming.
                    def _prio(item: Tuple[str, str]) -> int:
                        bus, status = item
                        if action in ("pause", "play_pause") and status == "Playing":
                            return 0
                        if action in ("play", "play_pause") and bus == self._last_mpris_dest:
                            return 0
                        if status == "Paused":
                            return 1
                        return 2

                    players.sort(key=_prio)
                    method_map = {"play_pause": "PlayPause", "pause": "Pause", "play": "Play"}
                    for bus, _status in players:
                        rc, _ = _run_quiet(
                            [
                                "gdbus",
                                "call",
                                "--session",
                                "--dest",
                                bus,
                                "--object-path",
                                "/org/freedesktop/MediaPlayer2",
                                "--method",
                                f"org.mpris.MediaPlayer2.Player.{method_map[action]}",
                            ]
                        )
                        if rc == 0:
                            self._last_mpris_dest = bus
                            self.last_target_label = _friendly_mpris_name(bus)
                            return True

                if shutil.which("playerctl"):
                    cmd_map = {"play_pause": "play-pause", "pause": "pause", "play": "play"}
                    rc, _ = _run_quiet(["playerctl", cmd_map[action]])
                    if rc == 0:
                        self.last_target_label = "Media Player"
                        return True

                win = self._pick_hyprland_media_window()
                if win and win.get("address"):
                    addr = win["address"]
                    cls = str(win.get("class") or "").lower()
                    key = "space" if any(p in cls for p in ("mpv", "vlc", "celluloid")) else "XF86AudioPlay"
                    rc, _ = _run_quiet(["hyprctl", "dispatch", "sendshortcut", f", {key}, address:{addr}"])
                    if rc == 0:
                        self.last_target_label = str(win.get("class") or "Active Window")
                        return True
                return False

            if action == "fullscreen":
                win = self._pick_hyprland_media_window()
                if win and win.get("address"):
                    addr = win["address"]
                    cls = str(win.get("class") or "").lower()
                    self.last_target_label = str(win.get("class") or "Active Window")
                    if any(p in cls for p in ("mpv", "vlc", "celluloid", "totem")):
                        rc, _ = _run_quiet(
                            ["hyprctl", "--batch", f"dispatch focuswindow address:{addr} ; dispatch fullscreen 0"]
                        )
                        if rc == 0:
                            return True
                    rc, _ = _run_quiet(
                        ["hyprctl", "--batch", f"dispatch focuswindow address:{addr} ; dispatch fullscreen 0"]
                    )
                    if rc == 0:
                        return True
                if shutil.which("wtype"):
                    rc, _ = _run_quiet(["wtype", "-k", "F11"])
                    if rc == 0:
                        self.last_target_label = "Active Window"
                        return True
                return False

            return False

        if sys.platform == "win32":
            if action in ("play_pause", "pause", "play"):
                self.last_target_label = "Windows Media"
                return _win32_vk(0xB3)
            if action == "fullscreen":
                self.last_target_label = "Active Window"
                return _win32_vk(0x7A)
        elif sys.platform == "darwin":
            if action == "fullscreen":
                rc, _ = _run_quiet(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to keystroke "f" using {command down, control down}',
                    ]
                )
                if rc == 0:
                    self.last_target_label = "Active Window"
                return rc == 0

        return False
