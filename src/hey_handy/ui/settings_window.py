"""Settings, browser extension setup, and live camera test window for Hey Handy."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import ACTION_LABELS, GESTURE_LABELS, VALID_ACTIONS, HeyHandyConfig
from ..gesture_engine import PreviewFrame
from ..models import ensure_models
from ..ws_bridge import ExtensionStatus

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)

DARK_STYLESHEET = """
QWidget {
    background-color: #0e1117;
    color: #e2e8f0;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
}
QGroupBox {
    background-color: #161b24;
    border: 1px solid #262f3f;
    border-radius: 10px;
    margin-top: 10px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #2dd4bf;
}
QPushButton {
    background-color: #1f2937;
    border: 1px solid #334155;
    border-radius: 7px;
    padding: 6px 12px;
    color: #f8fafc;
}
QPushButton:hover {
    background-color: #2b384a;
    border-color: #2dd4bf;
}
QPushButton#primaryBtn {
    background-color: #0f766e;
    border-color: #14b8a6;
    font-weight: 600;
}
QPushButton#primaryBtn:hover {
    background-color: #0d9488;
}
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #0f141d;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 5px 8px;
    color: #f8fafc;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #0f141d;
}
QCheckBox::indicator:hover {
    border-color: #2dd4bf;
}
QCheckBox::indicator:checked {
    background-color: #14b8a6;
    border-color: #2dd4bf;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #1f2937;
    border-left: 1px solid #334155;
    width: 18px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #cbd5e1;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #cbd5e1;
}
QLabel#muted {
    color: #94a3b8;
    font-size: 12px;
}
"""


class SettingsWindow(QtWidgets.QMainWindow):
    """Configuration & live gesture verification UI (stays hidden during normal use)."""

    configSaved = QtCore.Signal(object)  # HeyHandyConfig
    wakeClicked = QtCore.Signal()
    actionTestClicked = QtCore.Signal(str)
    previewToggled = QtCore.Signal(bool)
    modelsReady = QtCore.Signal()

    def __init__(
        self,
        config: HeyHandyConfig,
        models_ready: bool,
        minimize_to_tray: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._minimize_to_tray = minimize_to_tray
        self._gesture_combos: Dict[str, QtWidgets.QComboBox] = {}

        self.setWindowTitle("Hey Handy — Gestures & Active Tab Control")
        self.resize(940, 680)
        self.setStyleSheet(DARK_STYLESHEET)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(12)
        right = QtWidgets.QVBoxLayout()
        right.setSpacing(12)
        root.addLayout(left, 1)
        root.addLayout(right, 1)

        # --- Left Top: Live Status & Quick Controls ---
        status_group = QtWidgets.QGroupBox("Live Status && Quick Test")
        status_lay = QtWidgets.QVBoxLayout(status_group)
        status_lay.setSpacing(8)

        self._state_label = QtWidgets.QLabel("State: Sleeping (say 'Hey Handy')")
        self._state_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #2dd4bf;")
        status_lay.addWidget(self._state_label)

        self._ext_label = QtWidgets.QLabel("Browser Extension: Waiting for connection on ws://127.0.0.1:17421")
        self._ext_label.setWordWrap(True)
        self._ext_label.setObjectName("muted")
        status_lay.addWidget(self._ext_label)

        self._model_label = QtWidgets.QLabel(
            "Models: Ready (offline)" if models_ready else "Models: Not downloaded yet"
        )
        self._model_label.setObjectName("muted")
        status_lay.addWidget(self._model_label)

        btn_row = QtWidgets.QHBoxLayout()
        self._wake_btn = QtWidgets.QPushButton("Simulate 'Hey Handy'")
        self._wake_btn.setObjectName("primaryBtn")
        self._wake_btn.clicked.connect(self.wakeClicked)
        btn_row.addWidget(self._wake_btn)

        self._ext_btn = QtWidgets.QPushButton("Open Extension Folder")
        self._ext_btn.clicked.connect(self._open_extension_folder)
        btn_row.addWidget(self._ext_btn)

        if not models_ready:
            self._dl_btn = QtWidgets.QPushButton("Download Models")
            self._dl_btn.clicked.connect(self._download_models_async)
            btn_row.addWidget(self._dl_btn)
        else:
            self._dl_btn = None
        status_lay.addLayout(btn_row)

        quick_row = QtWidgets.QHBoxLayout()
        for act, title in (
            ("play_pause", "Play/Pause"),
            ("pause", "Pause"),
            ("fullscreen", "Fullscreen"),
            ("volume_down", "Vol -"),
            ("volume_up", "Vol +"),
        ):
            b = QtWidgets.QPushButton(title)
            b.clicked.connect(lambda _=False, a=act: self.actionTestClicked.emit(a))
            quick_row.addWidget(b)
        status_lay.addLayout(quick_row)
        left.addWidget(status_group)

        # --- Left Bottom: Optional Camera Test Preview ---
        cam_group = QtWidgets.QGroupBox("Camera && Gesture Tester")
        cam_lay = QtWidgets.QVBoxLayout(cam_group)
        self._preview_toggle = QtWidgets.QCheckBox("Enable live camera test preview (off during normal eating use)")
        self._preview_toggle.toggled.connect(self._on_preview_toggled)
        cam_lay.addWidget(self._preview_toggle)

        self._preview_view = QtWidgets.QLabel("Camera stays off until you say 'Hey Handy' or enable preview.")
        self._preview_view.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview_view.setMinimumHeight(260)
        self._preview_view.setStyleSheet(
            "background-color: #090b10; border: 1px dashed #2d3748; border-radius: 8px; color: #64748b;"
        )
        cam_lay.addWidget(self._preview_view, 1)

        self._detected_label = QtWidgets.QLabel("Detected: —")
        self._detected_label.setObjectName("muted")
        cam_lay.addWidget(self._detected_label)
        left.addWidget(cam_group, 1)

        # --- Right Top: Wake Word & Eating Safety ---
        wake_group = QtWidgets.QGroupBox("Wake Word && Eating Safety")
        form = QtWidgets.QFormLayout(wake_group)
        form.setSpacing(8)

        self._phrase_edit = QtWidgets.QLineEdit(config.wake_phrase)
        form.addRow("Wake phrase:", self._phrase_edit)

        self._sensitivity_spin = QtWidgets.QDoubleSpinBox()
        self._sensitivity_spin.setRange(0.10, 1.00)
        self._sensitivity_spin.setSingleStep(0.05)
        self._sensitivity_spin.setValue(config.wake_sensitivity)
        form.addRow("Wake sensitivity:", self._sensitivity_spin)

        self._wake_window_spin = QtWidgets.QDoubleSpinBox()
        self._wake_window_spin.setRange(2.0, 60.0)
        self._wake_window_spin.setSuffix(" s")
        self._wake_window_spin.setValue(config.wake_window_s)
        form.addRow("Wake window:", self._wake_window_spin)

        self._stability_spin = QtWidgets.QSpinBox()
        self._stability_spin.setRange(2, 10)
        self._stability_spin.setSuffix(" frames")
        self._stability_spin.setValue(config.stability_frames)
        form.addRow("Hold stability:", self._stability_spin)

        self._vol_step_spin = QtWidgets.QSpinBox()
        self._vol_step_spin.setRange(1, 25)
        self._vol_step_spin.setSuffix(" %")
        self._vol_step_spin.setValue(config.volume_step)
        form.addRow("Volume step:", self._vol_step_spin)

        self._vol_mode_combo = QtWidgets.QComboBox()
        self._vol_mode_combo.addItem("System Volume (works everywhere)", "system")
        self._vol_mode_combo.addItem("Active Browser Tab Volume", "tab")
        self._vol_mode_combo.addItem("Active Tab + System", "both")
        idx = self._vol_mode_combo.findData(config.volume_mode)
        if idx >= 0:
            self._vol_mode_combo.setCurrentIndex(idx)
        form.addRow("Volume target:", self._vol_mode_combo)

        self._camera_spin = QtWidgets.QSpinBox()
        self._camera_spin.setRange(0, 8)
        self._camera_spin.setValue(config.camera_index)
        form.addRow("Webcam index:", self._camera_spin)

        checks_lay = QtWidgets.QGridLayout()
        self._always_on_chk = QtWidgets.QCheckBox("Always-on gestures (skip wake word)")
        self._always_on_chk.setChecked(config.always_on_gestures)
        self._warm_cam_chk = QtWidgets.QCheckBox("Keep camera warm (faster wake)")
        self._warm_cam_chk.setChecked(config.keep_camera_warm)
        self._tab_hud_chk = QtWidgets.QCheckBox("Show in-tab HUD pill")
        self._tab_hud_chk.setChecked(config.show_tab_hud)
        self._desk_hud_chk = QtWidgets.QCheckBox("Show desktop HUD pill")
        self._desk_hud_chk.setChecked(config.show_desktop_hud)
        self._sound_chk = QtWidgets.QCheckBox("Audio chimes")
        self._sound_chk.setChecked(config.sound_feedback)

        checks_lay.addWidget(self._always_on_chk, 0, 0)
        checks_lay.addWidget(self._warm_cam_chk, 0, 1)
        checks_lay.addWidget(self._tab_hud_chk, 1, 0)
        checks_lay.addWidget(self._desk_hud_chk, 1, 1)
        checks_lay.addWidget(self._sound_chk, 2, 0)
        form.addRow(checks_lay)
        right.addWidget(wake_group)

        # --- Right Bottom: Gesture Mapping ---
        map_group = QtWidgets.QGroupBox("Gesture Mapping")
        map_form = QtWidgets.QFormLayout(map_group)
        map_form.setSpacing(8)
        for gesture_key, gesture_label in GESTURE_LABELS.items():
            combo = QtWidgets.QComboBox()
            for act in VALID_ACTIONS:
                combo.addItem(ACTION_LABELS[act], act)
            current = config.gesture_map.get(gesture_key, "none")
            c_idx = combo.findData(current)
            if c_idx >= 0:
                combo.setCurrentIndex(c_idx)
            self._gesture_combos[gesture_key] = combo
            map_form.addRow(gesture_label, combo)
        right.addWidget(map_group)

        save_row = QtWidgets.QHBoxLayout()
        save_row.addStretch(1)
        reset_btn = QtWidgets.QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        save_row.addWidget(reset_btn)

        save_btn = QtWidgets.QPushButton("Save && Apply")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        right.addLayout(save_row)

    def _on_preview_toggled(self, checked: bool) -> None:
        if not checked:
            self._preview_view.setPixmap(QtGui.QPixmap())
            self._preview_view.setText("Camera stays off until you say 'Hey Handy' or enable preview.")
            self._detected_label.setText("Detected: —")
        self.previewToggled.emit(checked)

    @QtCore.Slot(str, float)
    def update_state(self, state: str, remaining_s: float) -> None:
        if state == "armed":
            rem = "∞" if math.isinf(remaining_s) else f"{max(0.0, remaining_s):.1f}s"
            self._state_label.setText(f"State: ARMED ({rem}) — waiting for hand gesture")
            self._state_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #22c55e;")
        else:
            self._state_label.setText(f"State: Sleeping — say '{self._phrase_edit.text().title()}'")
            self._state_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #2dd4bf;")

    @QtCore.Slot(object)
    def update_extension_status(self, status: ExtensionStatus) -> None:
        if status.connected:
            tab = status.active_tab_title or "No active media tab reported yet"
            kind = f" [{status.media_type}]" if status.media_type else ""
            self._ext_label.setText(f"Browser Extension: Connected ({status.browser or 'Browser'}) — {tab}{kind}")
        else:
            self._ext_label.setText(
                f"Browser Extension: Not connected (load extension/ folder in Chrome/Firefox; ws://127.0.0.1:{self._config.ws_port})"
            )

    @QtCore.Slot(object)
    def update_preview(self, frame: PreviewFrame) -> None:
        if not self._preview_toggle.isChecked():
            return
        rgb = frame.rgb_image
        h, w, ch = rgb.shape
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format.Format_RGB888).copy()
        pix = QtGui.QPixmap.fromImage(qimg)

        if frame.landmarks:
            p = QtGui.QPainter(pix)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            p.setPen(QtGui.QPen(QtGui.QColor("#2dd4bf"), 2))
            for a, b in HAND_CONNECTIONS:
                la, lb = frame.landmarks[a], frame.landmarks[b]
                p.drawLine(int(la.x * w), int(la.y * h), int(lb.x * w), int(lb.y * h))
            p.setBrush(QtGui.QColor("#f8fafc"))
            for lm in frame.landmarks:
                p.drawEllipse(QtCore.QPointF(lm.x * w, lm.y * h), 3.5, 3.5)
            p.end()

        scaled = pix.scaled(
            self._preview_view.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_view.setPixmap(scaled)
        if frame.gesture:
            self._detected_label.setText(
                f"Detected: {GESTURE_LABELS.get(frame.gesture, frame.gesture)} ({frame.confidence:.0%})"
            )
        else:
            self._detected_label.setText("Detected: —")

    def _open_extension_folder(self) -> None:
        ext_dir = Path(__file__).resolve().parents[3] / "extension"
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(ext_dir)))

    def _download_models_async(self) -> None:
        if self._dl_btn:
            self._dl_btn.setEnabled(False)
        self._model_label.setText("Models: Downloading...")

        class _Worker(QtCore.QThread):
            progressed = QtCore.Signal(str, float)
            finished_ok = QtCore.Signal()
            failed = QtCore.Signal(str)

            def run(self) -> None:
                try:
                    ensure_models(progress_cb=lambda msg, frac: self.progressed.emit(msg, frac))
                    self.finished_ok.emit()
                except Exception as exc:
                    self.failed.emit(str(exc))

        self._dl_thread = _Worker(self)
        self._dl_thread.progressed.connect(
            lambda msg, frac: self._model_label.setText(f"{msg} ({frac:.0%})")
        )
        self._dl_thread.finished_ok.connect(self._on_models_downloaded)
        self._dl_thread.failed.connect(self._on_models_failed)
        self._dl_thread.start()

    def _on_models_downloaded(self) -> None:
        self._model_label.setText("Models: Ready (offline)")
        if self._dl_btn:
            self._dl_btn.hide()
        self.modelsReady.emit()

    def _on_models_failed(self, err: str) -> None:
        self._model_label.setText(f"Models download failed: {err}")
        if self._dl_btn:
            self._dl_btn.setEnabled(True)

    def _reset_defaults(self) -> None:
        defaults = HeyHandyConfig()
        self._phrase_edit.setText(defaults.wake_phrase)
        self._sensitivity_spin.setValue(defaults.wake_sensitivity)
        self._wake_window_spin.setValue(defaults.wake_window_s)
        self._stability_spin.setValue(defaults.stability_frames)
        self._vol_step_spin.setValue(defaults.volume_step)
        self._vol_mode_combo.setCurrentIndex(0)
        self._camera_spin.setValue(defaults.camera_index)
        self._always_on_chk.setChecked(defaults.always_on_gestures)
        self._warm_cam_chk.setChecked(defaults.keep_camera_warm)
        self._tab_hud_chk.setChecked(defaults.show_tab_hud)
        self._desk_hud_chk.setChecked(defaults.show_desktop_hud)
        self._sound_chk.setChecked(defaults.sound_feedback)
        for key, combo in self._gesture_combos.items():
            idx = combo.findData(defaults.gesture_map[key])
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _save(self) -> None:
        cfg = HeyHandyConfig(
            wake_phrase=self._phrase_edit.text(),
            wake_sensitivity=self._sensitivity_spin.value(),
            wake_window_s=self._wake_window_spin.value(),
            post_action_grace_s=self._config.post_action_grace_s,
            action_cooldown_s=self._config.action_cooldown_s,
            volume_repeat_s=self._config.volume_repeat_s,
            volume_step=self._vol_step_spin.value(),
            volume_mode=str(self._vol_mode_combo.currentData()),
            stability_frames=self._stability_spin.value(),
            min_confidence=self._config.min_confidence,
            min_hand_span=self._config.min_hand_span,
            keep_camera_warm=self._warm_cam_chk.isChecked(),
            always_on_gestures=self._always_on_chk.isChecked(),
            show_desktop_hud=self._desk_hud_chk.isChecked(),
            show_tab_hud=self._tab_hud_chk.isChecked(),
            sound_feedback=self._sound_chk.isChecked(),
            ws_host=self._config.ws_host,
            ws_port=self._config.ws_port,
            camera_index=self._camera_spin.value(),
            mic_device=self._config.mic_device,
            gesture_map={k: str(c.currentData()) for k, c in self._gesture_combos.items()},
        ).normalized()
        self._config = cfg
        self.configSaved.emit(cfg)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self._preview_toggle.isChecked():
            self._preview_toggle.setChecked(False)
        if self._minimize_to_tray:
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)
