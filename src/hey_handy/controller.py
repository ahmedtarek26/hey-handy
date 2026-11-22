"""Main application controller uniting wake word, gestures, active-tab bridge, and UI signals."""

from __future__ import annotations

import threading
from typing import Optional

from PySide6 import QtCore

from .audio_feedback import play_chime
from .config import ACTION_LABELS, HeyHandyConfig
from .gesture_engine import CameraGestureWorker, GestureEvent, PreviewFrame
from .models import ModelPaths, resolve_model_paths
from .system_control import SystemController
from .wake_word import WakeWordListener
from .ws_bridge import ExtensionStatus, WSBridge


class AppController(QtCore.QObject):
    """Coordinates wake word, gesture tracking, browser extension dispatch, and Qt UI."""

    stateChanged = QtCore.Signal(str, float)  # ("sleeping" | "armed", remaining_s)
    actionExecuted = QtCore.Signal(str, str, str)  # (action, display_label, detail)
    extensionChanged = QtCore.Signal(object)  # ExtensionStatus
    previewReady = QtCore.Signal(object)  # PreviewFrame
    errorOccurred = QtCore.Signal(str)
    micPausedChanged = QtCore.Signal(bool)

    def __init__(
        self,
        config: Optional[HeyHandyConfig] = None,
        models: Optional[ModelPaths] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.config = config or HeyHandyConfig.load()
        self.models = models or resolve_model_paths()
        self.system = SystemController()
        self._dispatch_lock = threading.Lock()
        self._armed = bool(self.config.always_on_gestures)

        self.bridge = WSBridge(
            host=self.config.ws_host,
            port=self.config.ws_port,
            on_status_change=lambda st: self.extensionChanged.emit(st),
        )
        self.cam_worker = CameraGestureWorker(
            model_paths=self.models,
            config=self.config,
            on_event=self._on_gesture_event,
            on_preview=lambda frame: self.previewReady.emit(frame),
            on_sleep=self._on_sleep,
            on_countdown=self._on_countdown,
            on_error=lambda msg: self.errorOccurred.emit(msg),
        )
        self.wake_listener = WakeWordListener(
            model_paths=self.models,
            phrase=self.config.wake_phrase,
            sensitivity=self.config.wake_sensitivity,
            mic_device=self.config.mic_device,
            on_wake=self._on_wake_word,
            on_error=lambda msg: self.errorOccurred.emit(msg),
        )

    def start(self) -> None:
        self.bridge.start()
        self.cam_worker.start()
        if self.models.kws_ready:
            self.wake_listener.start()
        if self.config.always_on_gestures:
            self._emit_armed(self.config.wake_window_s)
        else:
            self._emit_sleeping()

    def shutdown(self) -> None:
        self.wake_listener.stop()
        self.cam_worker.stop()
        self.bridge.stop()

    def reload_models(self) -> None:
        self.models = resolve_model_paths(self.models.base_dir)
        self.cam_worker.model_paths = self.models
        self.wake_listener.model_paths = self.models
        if self.models.kws_ready and not self.wake_listener.is_running:
            self.wake_listener.start()

    def apply_config(self, config: HeyHandyConfig) -> None:
        self.config = config.normalized()
        self.config.save()
        self.cam_worker.update_config(self.config)
        self.wake_listener.update_config(
            phrase=self.config.wake_phrase,
            sensitivity=self.config.wake_sensitivity,
            mic_device=self.config.mic_device,
        )
        if self.config.always_on_gestures:
            self._emit_armed(float("inf"))
        elif not self.cam_worker.state_machine.is_armed:
            self._emit_sleeping()

    @QtCore.Slot()
    def wake_now(self) -> None:
        """Manually wake Handy (from tray, hotkey, or test button)."""
        self._on_wake_word("MANUAL")

    @QtCore.Slot()
    def sleep_now(self) -> None:
        self.cam_worker.sleep_now()

    @QtCore.Slot(bool)
    def set_always_on(self, enabled: bool) -> None:
        self.config.always_on_gestures = bool(enabled)
        self.apply_config(self.config)

    @QtCore.Slot(bool)
    def set_mic_paused(self, paused: bool) -> None:
        self.wake_listener.set_paused(paused)
        self.micPausedChanged.emit(bool(paused))

    @QtCore.Slot(bool)
    def set_preview_enabled(self, enabled: bool) -> None:
        self.cam_worker.set_preview_enabled(enabled)

    @QtCore.Slot(str)
    def trigger_action(self, action: str) -> None:
        """Execute an action directly (from gestures or Settings test buttons)."""
        self._dispatch_action(action)

    def _emit_armed(self, remaining: float) -> None:
        self._armed = True
        self.stateChanged.emit("armed", remaining)
        if self.config.show_tab_hud:
            self.bridge.broadcast_hud(
                {
                    "state": "armed",
                    "remaining": None if remaining == float("inf") else round(remaining, 1),
                    "alwaysOn": self.config.always_on_gestures,
                }
            )

    def _emit_sleeping(self) -> None:
        self._armed = False
        self.stateChanged.emit("sleeping", 0.0)
        if self.config.show_tab_hud:
            self.bridge.broadcast_hud({"state": "sleeping"})

    def _on_wake_word(self, _detected: str) -> None:
        self.cam_worker.wake()
        play_chime("wake", enabled=self.config.sound_feedback)
        self._emit_armed(self.config.wake_window_s)

    def _on_countdown(self, remaining: float) -> None:
        self.stateChanged.emit("armed", remaining)

    def _on_sleep(self) -> None:
        if self._armed:
            play_chime("sleep", enabled=self.config.sound_feedback)
        self._emit_sleeping()

    def _on_gesture_event(self, event: GestureEvent) -> None:
        if event.action == "sleep":
            return
        self._dispatch_action(event.action, chime=not event.continuous)

    def _dispatch_action(self, action: str, chime: bool = True) -> None:
        if action in ("none", ""):
            return

        with self._dispatch_lock:
            label = ACTION_LABELS.get(action, action)
            detail = ""
            ok = False

            if action in ("volume_up", "volume_down"):
                delta = self.config.volume_step if action == "volume_up" else -self.config.volume_step
                mode = self.config.volume_mode

                if mode in ("tab", "both"):
                    res = self.bridge.send_command(action, step=self.config.volume_step)
                    if res and res.get("handled"):
                        ok = True
                        vol = res.get("volumePercent")
                        detail = f"Tab {vol}%" if vol is not None else "Active tab"

                if mode in ("system", "both") or (mode == "tab" and not ok):
                    sys_ok, sys_vol = self.system.adjust_volume(delta)
                    if sys_ok:
                        ok = True
                        detail = f"{sys_vol}%" if sys_vol is not None else "System audio"

            elif action == "mute":
                if self.config.volume_mode == "tab":
                    res = self.bridge.send_command("mute")
                    ok = bool(res and res.get("handled"))
                    if ok:
                        detail = "Muted" if res.get("muted") else "Unmuted"
                if not ok:
                    ok = self.system.toggle_mute()
                    if not ok:
                        res = self.bridge.send_command("mute")
                        ok = bool(res and res.get("handled"))
                    detail = "Audio toggled"

            else:
                res = self.bridge.send_command(action)
                if res and res.get("handled"):
                    ok = True
                    detail = str(res.get("detail") or res.get("title") or "Active tab")
                    if res.get("label"):
                        label = str(res["label"])
                else:
                    ok = self.system.fallback_media_action(action)
                    detail = "System media" if ok else "No active media found"

            if chime and ok:
                play_chime("confirm", enabled=self.config.sound_feedback)

            self.actionExecuted.emit(action, label, detail)
            if self.config.show_tab_hud:
                self.bridge.broadcast_hud(
                    {
                        "state": "action",
                        "action": action,
                        "label": label,
                        "detail": detail,
                    }
                )
