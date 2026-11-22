"""Configuration persistence and defaults for Hey Handy."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Optional

DEFAULT_GESTURE_MAP: Dict[str, str] = {
    "Open_Palm": "play_pause",
    "Closed_Fist": "pause",
    "Victory": "fullscreen",
    "Thumb_Up": "volume_up",
    "Thumb_Down": "volume_down",
    "Pointing_Up": "mute",
}

VALID_ACTIONS = (
    "play_pause",
    "pause",
    "play",
    "fullscreen",
    "volume_up",
    "volume_down",
    "mute",
    "sleep",
    "none",
)

ACTION_LABELS: Dict[str, str] = {
    "play_pause": "Play / Pause",
    "pause": "Pause (Stop)",
    "play": "Resume (Play)",
    "fullscreen": "Toggle Fullscreen",
    "volume_up": "Volume Up",
    "volume_down": "Volume Down",
    "mute": "Mute / Unmute",
    "sleep": "Dismiss Handy",
    "none": "Disabled",
}

GESTURE_LABELS: Dict[str, str] = {
    "Open_Palm": "Open Palm ✋",
    "Closed_Fist": "Closed Fist ✊",
    "Victory": "Peace / Victory ✌️",
    "Thumb_Up": "Thumbs Up 👍",
    "Thumb_Down": "Thumbs Down 👎",
    "Pointing_Up": "Pointing Up ☝️",
}


def get_config_dir() -> Path:
    """Return the platform-appropriate configuration directory."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "hey-handy"


def get_data_dir() -> Path:
    """Return the platform-appropriate data directory (for ML models)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "hey-handy"


@dataclass
class HeyHandyConfig:
    """User-configurable settings for wake word, gestures, and active tab control."""

    wake_phrase: str = "HEY HANDY"
    wake_sensitivity: float = 0.55  # 0.1 (strict) .. 1.0 (sensitive)
    wake_window_s: float = 8.0
    post_action_grace_s: float = 3.0
    action_cooldown_s: float = 1.4
    volume_repeat_s: float = 0.28
    volume_step: int = 8  # percent (1..25)
    volume_mode: str = "system"  # "system", "tab", or "both"
    stability_frames: int = 4  # consecutive/consensus frames required
    min_confidence: float = 0.58
    min_hand_span: float = 0.08
    keep_camera_warm: bool = False
    always_on_gestures: bool = False
    show_desktop_hud: bool = True
    show_tab_hud: bool = True
    sound_feedback: bool = True
    ws_host: str = "127.0.0.1"
    ws_port: int = 17421
    camera_index: int = 0
    mic_device: Optional[int] = None
    gesture_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_GESTURE_MAP))

    def normalized(self) -> "HeyHandyConfig":
        """Clamp numerical fields and sanitize gesture mappings."""
        self.wake_phrase = (self.wake_phrase or "HEY HANDY").strip().upper()
        self.wake_sensitivity = max(0.1, min(1.0, float(self.wake_sensitivity)))
        self.wake_window_s = max(2.0, min(60.0, float(self.wake_window_s)))
        self.post_action_grace_s = max(0.5, min(15.0, float(self.post_action_grace_s)))
        self.action_cooldown_s = max(0.4, min(5.0, float(self.action_cooldown_s)))
        self.volume_repeat_s = max(0.12, min(1.5, float(self.volume_repeat_s)))
        self.volume_step = max(1, min(25, int(self.volume_step)))
        if self.volume_mode not in ("system", "tab", "both"):
            self.volume_mode = "system"
        self.stability_frames = max(2, min(10, int(self.stability_frames)))
        self.min_confidence = max(0.35, min(0.95, float(self.min_confidence)))
        self.min_hand_span = max(0.03, min(0.30, float(self.min_hand_span)))
        self.ws_port = max(1024, min(65535, int(self.ws_port)))
        self.camera_index = max(0, int(self.camera_index))

        merged = dict(DEFAULT_GESTURE_MAP)
        for gesture, action in (self.gesture_map or {}).items():
            if gesture in GESTURE_LABELS and action in VALID_ACTIONS:
                merged[gesture] = action
        self.gesture_map = merged
        return self

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "HeyHandyConfig":
        """Load configuration from disk, returning defaults if missing or invalid."""
        target = path or (get_config_dir() / "config.json")
        if not target.exists():
            return cls().normalized()
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return cls().normalized()
            valid_fields = {f for f in cls.__dataclass_fields__}
            filtered = {k: v for k, v in raw.items() if k in valid_fields}
            return cls(**filtered).normalized()
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return cls().normalized()

    def save(self, path: Optional[Path] = None) -> Path:
        """Persist configuration atomically to disk."""
        self.normalized()
        target = path or (get_config_dir() / "config.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
        return target
