"""Cross-platform OS fallback controls (volume & native player fallback)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional


def _run_quiet(cmd: list[str], timeout: float = 1.5) -> tuple[int, str]:
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


class SystemController:
    """Adjusts OS master volume and provides media fallback outside browser tabs."""

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

    def adjust_volume(self, delta_percent: int) -> tuple[bool, Optional[int]]:
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
            # Windows VK_VOLUME_UP (0xAF) / VK_VOLUME_DOWN (0xAE) step by 2% per press.
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
            return _win32_vk(0xAD)  # VK_VOLUME_MUTE
        return False

    def fallback_media_action(self, action: str) -> bool:
        """Fallback for desktop players (VLC, mpv, Spotify) when no active browser tab matched."""
        if sys.platform.startswith("linux"):
            if action in ("play_pause", "pause", "play"):
                if shutil.which("playerctl"):
                    cmd_map = {"play_pause": "play-pause", "pause": "pause", "play": "play"}
                    rc, _ = _run_quiet(["playerctl", cmd_map[action]])
                    if rc == 0:
                        return True
                # MPRIS D-Bus fallback without playerctl
                if shutil.which("gdbus"):
                    method_map = {"play_pause": "PlayPause", "pause": "Pause", "play": "Play"}
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
                    if rc == 0:
                        for token in names.replace("'", " ").replace(",", " ").split():
                            if token.startswith("org.mpris.MediaPlayer2."):
                                r2, _ = _run_quiet(
                                    [
                                        "gdbus",
                                        "call",
                                        "--session",
                                        "--dest",
                                        token,
                                        "--object-path",
                                        "/org/mpris/MediaPlayer2",
                                        "--method",
                                        f"org.mpris.MediaPlayer2.Player.{method_map[action]}",
                                    ]
                                )
                                if r2 == 0:
                                    return True
            elif action == "fullscreen":
                if shutil.which("hyprctl"):
                    rc, _ = _run_quiet(["hyprctl", "dispatch", "fullscreen", "0"])
                    if rc == 0:
                        return True
                if shutil.which("wtype"):
                    rc, _ = _run_quiet(["wtype", "-k", "F11"])
                    if rc == 0:
                        return True
            return False

        if sys.platform == "win32":
            if action in ("play_pause", "pause", "play"):
                return _win32_vk(0xB3)  # VK_MEDIA_PLAY_PAUSE
            if action == "fullscreen":
                return _win32_vk(0x7A)  # VK_F11
        elif sys.platform == "darwin":
            if action == "fullscreen":
                rc, _ = _run_quiet(
                    [
                        "osascript",
                        "-e",
                        'tell application "System Events" to keystroke "f" using {command down, control down}',
                    ]
                )
                return rc == 0

        return False
