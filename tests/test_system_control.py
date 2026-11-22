"""Unit tests for SystemController MPRIS and Hyprland fallback logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hey_handy.system_control import SystemController


def test_system_control_uses_correct_mpris_object_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "hey_handy" / "system_control.py"
    text = src.read_text(encoding="utf-8")
    assert "/org/freedesktop/MediaPlayer2" not in text
    assert "/org/mpris/MediaPlayer2" in text


def test_mpris_prefers_playing_player_and_remembers_last_paused() -> None:
    sc = SystemController()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], timeout: float = 1.5):
        calls.append(cmd)
        if "org.freedesktop.DBus.ListNames" in cmd:
            return 0, "(['org.mpris.MediaPlayer2.spotify', 'org.mpris.MediaPlayer2.firefox.instance_1_5038'],)"
        if "PlaybackStatus" in cmd:
            dest = cmd[cmd.index("--dest") + 1]
            return 0, "(<'Playing'>,)" if "firefox" in dest else "(<'Paused'>,)"
        return 0, "()"

    with patch("hey_handy.system_control.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "gdbus" else None):
        with patch("hey_handy.system_control._run_quiet", side_effect=fake_run):
            assert sc.fallback_media_action("pause") is True
            assert sc.last_target_label == "Browser"
            pause_cmds = [c for c in calls if any("Player.Pause" in part for part in c)]
            assert len(pause_cmds) == 1
            assert "org.mpris.MediaPlayer2.firefox.instance_1_5038" in pause_cmds[0]
            assert "/org/mpris/MediaPlayer2" in pause_cmds[0]


def test_hyprland_fullscreen_uses_lua_eval_and_f_for_video_players() -> None:
    sc = SystemController()
    cmds: list[list[str]] = []

    def fake_run(cmd: list[str], timeout: float = 1.5):
        cmds.append(cmd)
        if cmd[:2] == ["hyprctl", "clients"]:
            return 0, '[{"address":"0x123","class":"zen","title":"Video - YouTube — Zen Browser","focusHistoryID":2}]'
        if cmd[:2] == ["hyprctl", "activewindow"]:
            return 0, '{"address":"0x999"}'
        if cmd[:2] == ["hyprctl", "eval"]:
            return 0, "ok"
        return 0, ""

    with patch("hey_handy.system_control.shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "hyprctl" else None):
        with patch("hey_handy.system_control._run_quiet", side_effect=fake_run):
            assert sc.fallback_media_action("fullscreen") is True
            eval_cmds = [" ".join(c) for c in cmds if c[:2] == ["hyprctl", "eval"]]
            assert any('window = "address:0x123"' in e for e in eval_cmds)
            assert any('key = "f"' in e for e in eval_cmds)

