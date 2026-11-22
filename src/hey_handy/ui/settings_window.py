"""Modern responsive Settings, Mic/Camera Tester, and Window-Mode UI for Hey Handy."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from ..config import ACTION_LABELS, GESTURE_LABELS, VALID_ACTIONS, HeyHandyConfig
from ..gesture_engine import PreviewFrame
from ..models import ensure_models
from ..wake_word import list_input_devices
from ..ws_bridge import ExtensionStatus

HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)

GESTURE_HINTS: Dict[str, str] = {
    "Open_Palm": "Show 5 open fingers",
    "Closed_Fist": "Hold a closed fist",
    "Victory": "Two fingers (peace sign)",
    "Thumb_Up": "Hold to raise volume",
    "Thumb_Down": "Hold to lower volume",
    "Pointing_Up": "Index finger straight up",
}

DARK_STYLESHEET = """
QWidget {
    background-color: #0b0e14;
    color: #e2e8f0;
    font-size: 13px;
}
QLabel, QCheckBox {
    background-color: transparent;
}
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    background: #0b0e14;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #273244;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QFrame#headerBar {
    background-color: #111621;
    border-bottom: 1px solid #1f2937;
}
QFrame#footerBar {
    background-color: #111621;
    border-top: 1px solid #1f2937;
}
QFrame#card {
    background-color: #131924;
    border: 1px solid #232d3f;
    border-radius: 12px;
}
QFrame#gestureRow {
    background-color: #0e131c;
    border: 1px solid #1f2937;
    border-radius: 9px;
}
QFrame#gestureRow[active="true"] {
    background-color: #102a2a;
    border: 1px solid #2dd4bf;
}
QLabel#cardTitle {
    color: #2dd4bf;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.02em;
}
QLabel#brandTitle {
    color: #f8fafc;
    font-size: 16px;
    font-weight: 700;
}
QLabel#statusPill {
    background-color: #172030;
    border: 1px solid #283548;
    border-radius: 12px;
    padding: 4px 11px;
    font-size: 12px;
    font-weight: 600;
    color: #2dd4bf;
}
QLabel#statusPill[armed="true"] {
    background-color: #0d2b22;
    border-color: #22c55e;
    color: #4ade80;
}
QLabel#valuePill {
    background-color: #0d121b;
    border: 1px solid #263245;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 600;
    color: #cbd5e1;
    min-width: 68px;
}
QLabel#muted {
    color: #94a3b8;
    font-size: 12px;
}
QPushButton {
    background-color: #1a2232;
    border: 1px solid #2e3b52;
    border-radius: 8px;
    padding: 6px 12px;
    color: #f8fafc;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #243045;
    border-color: #2dd4bf;
}
QPushButton:checked {
    background-color: #114441;
    border-color: #2dd4bf;
    color: #5eead4;
}
QPushButton#primaryBtn {
    background-color: #0f766e;
    border-color: #14b8a6;
    font-weight: 600;
}
QPushButton#primaryBtn:hover {
    background-color: #0d9488;
}
QPushButton#segBtn {
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 7px;
}
QComboBox, QLineEdit, QSpinBox {
    background-color: #0d121b;
    border: 1px solid #2b384d;
    border-radius: 7px;
    padding: 5px 9px;
    color: #f8fafc;
}
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #1f2937;
    border-left: 1px solid #334155;
    width: 18px;
}
QSpinBox::up-arrow {
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #cbd5e1;
}
QSpinBox::down-arrow {
    width: 0px;
    height: 0px;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #cbd5e1;
}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover {
    border-color: #3e5270;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #1f2937;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #14b8a6;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #f8fafc;
    border: 2px solid #2dd4bf;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 8px;
}
QProgressBar {
    background-color: #0d121b;
    border: 1px solid #283548;
    border-radius: 5px;
    height: 10px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #2dd4bf;
    border-radius: 4px;
}
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #0d121b;
}
QCheckBox::indicator:hover {
    border-color: #2dd4bf;
}
QCheckBox::indicator:checked {
    background-color: #14b8a6;
    border-color: #2dd4bf;
}
"""


def _make_card(title: str) -> Tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
    card = QtWidgets.QFrame()
    card.setObjectName("card")
    lay = QtWidgets.QVBoxLayout(card)
    lay.setContentsMargins(14, 12, 14, 14)
    lay.setSpacing(10)
    lbl = QtWidgets.QLabel(title)
    lbl.setObjectName("cardTitle")
    lay.addWidget(lbl)
    return card, lay


class SettingsWindow(QtWidgets.QMainWindow):
    """Responsive Configuration, Mic/Camera Tester, and Window-Preset UI."""

    configSaved = QtCore.Signal(object)  # HeyHandyConfig
    wakeClicked = QtCore.Signal()
    actionTestClicked = QtCore.Signal(str)
    previewToggled = QtCore.Signal(bool)
    modelsReady = QtCore.Signal()

    COMPACT_BREAKPOINT = 860

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
        self._gesture_rows: Dict[str, QtWidgets.QFrame] = {}
        self._two_column_active: Optional[bool] = None
        self._window_mode = config.window_mode

        self.setWindowTitle("Hey Handy — Gestures & Active Media Control")
        self.setMinimumSize(420, 460)
        self.setStyleSheet(DARK_STYLESHEET)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Top Header Bar ---
        header = QtWidgets.QFrame()
        header.setObjectName("headerBar")
        header_lay = QtWidgets.QHBoxLayout(header)
        header_lay.setContentsMargins(16, 10, 16, 10)
        header_lay.setSpacing(10)

        brand = QtWidgets.QLabel("✋ Hey Handy")
        brand.setObjectName("brandTitle")
        header_lay.addWidget(brand)

        self._state_pill = QtWidgets.QLabel("● Sleeping — say 'Hey Handy'")
        self._state_pill.setObjectName("statusPill")
        self._state_pill.setProperty("armed", "false")
        header_lay.addWidget(self._state_pill)
        header_lay.addStretch(1)

        self._compact_btn = QtWidgets.QPushButton("Small")
        self._compact_btn.setObjectName("segBtn")
        self._compact_btn.setCheckable(True)
        self._compact_btn.setToolTip("Switch to compact single-column window (500×680)")
        self._compact_btn.clicked.connect(lambda: self.apply_window_mode("compact"))

        self._standard_btn = QtWidgets.QPushButton("Standard")
        self._standard_btn.setObjectName("segBtn")
        self._standard_btn.setCheckable(True)
        self._standard_btn.setToolTip("Switch to standard two-column window (980×760)")
        self._standard_btn.clicked.connect(lambda: self.apply_window_mode("standard"))

        self._full_btn = QtWidgets.QPushButton("Full")
        self._full_btn.setObjectName("segBtn")
        self._full_btn.setCheckable(True)
        self._full_btn.setToolTip("Expand to full screen/maximized window")
        self._full_btn.clicked.connect(lambda: self.apply_window_mode("full"))

        for b in (self._compact_btn, self._standard_btn, self._full_btn):
            header_lay.addWidget(b)

        if minimize_to_tray:
            hide_btn = QtWidgets.QPushButton("Tray")
            hide_btn.setObjectName("segBtn")
            hide_btn.setToolTip("Minimize to system tray (keeps listening in background)")
            hide_btn.clicked.connect(self.hide)
            header_lay.addWidget(hide_btn)

        outer.addWidget(header)

        # --- Scrollable Responsive Body ---
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        body = QtWidgets.QWidget()
        scroll.setWidget(body)
        self._grid = QtWidgets.QGridLayout(body)
        self._grid.setContentsMargins(14, 14, 14, 14)
        self._grid.setSpacing(12)

        # Build the 4 cards
        self._status_card = self._build_status_card(models_ready)
        self._camera_card = self._build_camera_card()
        self._settings_card = self._build_settings_card()
        self._mapping_card = self._build_mapping_card()

        # --- Footer Bar ---
        footer = QtWidgets.QFrame()
        footer.setObjectName("footerBar")
        footer_lay = QtWidgets.QHBoxLayout(footer)
        footer_lay.setContentsMargins(16, 10, 16, 10)
        footer_lay.setSpacing(10)

        self._footer_hint = QtWidgets.QLabel(
            "Tip: Say 'Hey Handy' softly — camera stays off until you wake it."
        )
        self._footer_hint.setObjectName("muted")
        footer_lay.addWidget(self._footer_hint, 1)

        reset_btn = QtWidgets.QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        footer_lay.addWidget(reset_btn)

        self._save_btn = QtWidgets.QPushButton("Save && Apply")
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.clicked.connect(self._save)
        footer_lay.addWidget(self._save_btn)

        outer.addWidget(footer)

        self._save_feedback_timer = QtCore.QTimer(self)
        self._save_feedback_timer.setSingleShot(True)
        self._save_feedback_timer.timeout.connect(lambda: self._save_btn.setText("Save && Apply"))

        self._apply_initial_geometry()

    def _build_status_card(self, models_ready: bool) -> QtWidgets.QFrame:
        card, lay = _make_card("LIVE STATUS & QUICK CONTROLS")

        self._last_action_label = QtWidgets.QLabel("Last action: Ready (say 'Hey Handy' or click below)")
        self._last_action_label.setWordWrap(True)
        lay.addWidget(self._last_action_label)

        self._ext_label = QtWidgets.QLabel(
            "Target: Desktop MPRIS + Hyprland active (load extension/ for per-tab HUD)"
        )
        self._ext_label.setWordWrap(True)
        self._ext_label.setObjectName("muted")
        lay.addWidget(self._ext_label)

        mic_row = QtWidgets.QHBoxLayout()
        self._mic_status_label = QtWidgets.QLabel("Mic level:")
        self._mic_status_label.setObjectName("muted")
        self._mic_bar = QtWidgets.QProgressBar()
        self._mic_bar.setRange(0, 100)
        self._mic_bar.setTextVisible(False)
        self._mic_bar.setValue(0)
        mic_row.addWidget(self._mic_status_label)
        mic_row.addWidget(self._mic_bar, 1)
        lay.addLayout(mic_row)

        self._model_label = QtWidgets.QLabel(
            "Models: Offline Ready (MediaPipe + sherpa-onnx)" if models_ready else "Models: Not downloaded yet"
        )
        self._model_label.setObjectName("muted")
        lay.addWidget(self._model_label)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self._wake_btn = QtWidgets.QPushButton("Simulate 'Hey Handy'")
        self._wake_btn.setObjectName("primaryBtn")
        self._wake_btn.clicked.connect(self.wakeClicked)
        btn_row.addWidget(self._wake_btn, 1)

        self._ext_btn = QtWidgets.QPushButton("Extension Folder")
        self._ext_btn.clicked.connect(self._open_extension_folder)
        btn_row.addWidget(self._ext_btn)

        if not models_ready:
            self._dl_btn = QtWidgets.QPushButton("Download Models")
            self._dl_btn.clicked.connect(self._download_models_async)
            btn_row.addWidget(self._dl_btn)
        else:
            self._dl_btn = None
        lay.addLayout(btn_row)

        quick_grid = QtWidgets.QGridLayout()
        quick_grid.setSpacing(6)
        buttons = (
            ("play_pause", "⏯ Play / Pause", 0, 0),
            ("pause", "⏸ Pause", 0, 1),
            ("fullscreen", "⛶ Fullscreen", 0, 2),
            ("volume_down", "🔉 Vol -", 1, 0),
            ("volume_up", "🔊 Vol +", 1, 1),
            ("mute", "🔇 Mute", 1, 2),
        )
        for act, title, r, c in buttons:
            b = QtWidgets.QPushButton(title)
            b.setFixedHeight(32)
            b.clicked.connect(lambda _=False, a=act: self.actionTestClicked.emit(a))
            quick_grid.addWidget(b, r, c)
        lay.addLayout(quick_grid)
        lay.addStretch(1)
        return card

    def _build_camera_card(self) -> QtWidgets.QFrame:
        card, lay = _make_card("CAMERA & GESTURE TESTER")
        self._preview_toggle = QtWidgets.QCheckBox(
            "Enable live camera test preview (runs gestures live while checked)"
        )
        self._preview_toggle.toggled.connect(self._on_preview_toggled)
        lay.addWidget(self._preview_toggle)

        self._preview_view = QtWidgets.QLabel("Camera stays off until you say 'Hey Handy' or enable preview.")
        self._preview_view.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._preview_view.setWordWrap(True)
        self._preview_view.setMinimumHeight(210)
        self._preview_view.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self._preview_view.setStyleSheet(
            "background-color: #080a0f; border: 1px dashed #263143; border-radius: 9px; color: #64748b; padding: 12px;"
        )
        lay.addWidget(self._preview_view, 1)

        self._detected_label = QtWidgets.QLabel("Detected: —")
        self._detected_label.setObjectName("muted")
        lay.addWidget(self._detected_label)
        return card

    def _make_slider_row(
        self,
        minimum: int,
        maximum: int,
        value: int,
        formatter,
    ) -> Tuple[QtWidgets.QWidget, QtWidgets.QSlider, QtWidgets.QLabel]:
        row = QtWidgets.QWidget()
        row.setStyleSheet("background: transparent;")
        h = QtWidgets.QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        pill = QtWidgets.QLabel(formatter(value))
        pill.setObjectName("valuePill")
        pill.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        slider.valueChanged.connect(lambda v: pill.setText(formatter(v)))
        h.addWidget(slider, 1)
        h.addWidget(pill)
        return row, slider, pill

    def _build_settings_card(self) -> QtWidgets.QFrame:
        card, lay = _make_card("WAKE WORD & EATING SAFETY")
        form = QtWidgets.QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

        self._phrase_edit = QtWidgets.QLineEdit(self._config.wake_phrase)
        form.addRow("Wake phrase:", self._phrase_edit)

        self._mic_combo = QtWidgets.QComboBox()
        self._mic_combo.addItem("Auto (best hardware mic)", None)
        for dev_idx, dev_name in list_input_devices():
            self._mic_combo.addItem(f"[{dev_idx}] {dev_name}", dev_idx)
        m_idx = self._mic_combo.findData(self._config.mic_device)
        if m_idx >= 0:
            self._mic_combo.setCurrentIndex(m_idx)
        form.addRow("Microphone:", self._mic_combo)

        sens_row, self._sens_slider, _ = self._make_slider_row(
            10, 100, round(self._config.wake_sensitivity * 100),
            lambda v: f"{v}% (Soft)" if v >= 65 else f"{v}%",
        )
        form.addRow("Wake sensitivity:", sens_row)

        win_row, self._window_slider, _ = self._make_slider_row(
            2, 30, round(self._config.wake_window_s),
            lambda v: f"{v} s",
        )
        form.addRow("Wake window:", win_row)

        stab_row, self._stability_slider, _ = self._make_slider_row(
            2, 8, self._config.stability_frames,
            lambda v: f"{v} frames",
        )
        form.addRow("Hold stability:", stab_row)

        conf_row, self._conf_slider, _ = self._make_slider_row(
            30, 85, round(self._config.min_confidence * 100),
            lambda v: f"{v}%",
        )
        form.addRow("Gesture confidence:", conf_row)

        vol_row, self._vol_slider, _ = self._make_slider_row(
            2, 20, self._config.volume_step,
            lambda v: f"{v}%",
        )
        form.addRow("Volume step:", vol_row)

        self._vol_mode_combo = QtWidgets.QComboBox()
        self._vol_mode_combo.addItem("System Volume (works everywhere)", "system")
        self._vol_mode_combo.addItem("Active Browser Tab Volume", "tab")
        self._vol_mode_combo.addItem("Active Tab + System", "both")
        idx = self._vol_mode_combo.findData(self._config.volume_mode)
        if idx >= 0:
            self._vol_mode_combo.setCurrentIndex(idx)
        form.addRow("Volume target:", self._vol_mode_combo)

        self._camera_spin = QtWidgets.QSpinBox()
        self._camera_spin.setRange(0, 8)
        self._camera_spin.setValue(self._config.camera_index)
        form.addRow("Webcam index:", self._camera_spin)

        lay.addLayout(form)

        checks_lay = QtWidgets.QGridLayout()
        checks_lay.setSpacing(6)
        self._always_on_chk = QtWidgets.QCheckBox("Always-on gestures")
        self._always_on_chk.setChecked(self._config.always_on_gestures)
        self._warm_cam_chk = QtWidgets.QCheckBox("Keep camera warm")
        self._warm_cam_chk.setChecked(self._config.keep_camera_warm)
        self._tab_hud_chk = QtWidgets.QCheckBox("In-tab HUD pill")
        self._tab_hud_chk.setChecked(self._config.show_tab_hud)
        self._desk_hud_chk = QtWidgets.QCheckBox("Desktop HUD pill")
        self._desk_hud_chk.setChecked(self._config.show_desktop_hud)
        self._sound_chk = QtWidgets.QCheckBox("Audio chimes")
        self._sound_chk.setChecked(self._config.sound_feedback)

        checks_lay.addWidget(self._always_on_chk, 0, 0)
        checks_lay.addWidget(self._warm_cam_chk, 0, 1)
        checks_lay.addWidget(self._tab_hud_chk, 1, 0)
        checks_lay.addWidget(self._desk_hud_chk, 1, 1)
        checks_lay.addWidget(self._sound_chk, 2, 0)
        lay.addLayout(checks_lay)
        return card

    def _build_mapping_card(self) -> QtWidgets.QFrame:
        card, lay = _make_card("GESTURE MAPPING")
        for gesture_key, gesture_label in GESTURE_LABELS.items():
            row = QtWidgets.QFrame()
            row.setObjectName("gestureRow")
            row.setProperty("active", "false")
            r_lay = QtWidgets.QHBoxLayout(row)
            r_lay.setContentsMargins(10, 6, 10, 6)
            r_lay.setSpacing(10)

            info = QtWidgets.QVBoxLayout()
            info.setSpacing(1)
            g_lbl = QtWidgets.QLabel(gesture_label)
            g_lbl.setStyleSheet("font-weight: 600; color: #f8fafc;")
            h_lbl = QtWidgets.QLabel(GESTURE_HINTS.get(gesture_key, ""))
            h_lbl.setObjectName("muted")
            info.addWidget(g_lbl)
            info.addWidget(h_lbl)
            r_lay.addLayout(info, 1)

            combo = QtWidgets.QComboBox()
            combo.setMinimumWidth(160)
            for act in VALID_ACTIONS:
                combo.addItem(ACTION_LABELS[act], act)
            current = self._config.gesture_map.get(gesture_key, "none")
            c_idx = combo.findData(current)
            if c_idx >= 0:
                combo.setCurrentIndex(c_idx)
            r_lay.addWidget(combo)

            self._gesture_combos[gesture_key] = combo
            self._gesture_rows[gesture_key] = row
            lay.addWidget(row)
        return card

    def _apply_initial_geometry(self) -> None:
        self.resize(self._config.window_width, self._config.window_height)
        self._sync_mode_buttons(self._config.window_mode)
        self._relayout_cards(self._config.window_width)
        if self._config.window_mode == "full":
            self.setWindowState(self.windowState() | QtCore.Qt.WindowState.WindowMaximized)

    def _sync_mode_buttons(self, mode: str) -> None:
        self._compact_btn.setChecked(mode == "compact")
        self._standard_btn.setChecked(mode == "standard")
        self._full_btn.setChecked(mode == "full")

    def apply_window_mode(self, mode: str) -> None:
        """Switch between Small (compact), Standard, and Full window sizes."""
        self._window_mode = mode
        self._sync_mode_buttons(mode)
        if mode == "full":
            self.showMaximized()
        else:
            if self.isMaximized():
                self.showNormal()
            if mode == "compact":
                self.resize(500, 680)
            else:
                self.resize(980, 880)
        self._relayout_cards(self.width())

    def _relayout_cards(self, width: int) -> None:
        two_col = width >= self.COMPACT_BREAKPOINT
        if self._two_column_active is two_col:
            return
        self._two_column_active = two_col

        while self._grid.count():
            self._grid.takeAt(0)

        if two_col:
            self._grid.addWidget(self._status_card, 0, 0)
            self._grid.addWidget(self._camera_card, 1, 0)
            self._grid.addWidget(self._settings_card, 0, 1)
            self._grid.addWidget(self._mapping_card, 1, 1)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 1)
            self._grid.setRowStretch(0, 0)
            self._grid.setRowStretch(1, 1)
        else:
            self._grid.addWidget(self._status_card, 0, 0)
            self._grid.addWidget(self._camera_card, 1, 0)
            self._grid.addWidget(self._mapping_card, 2, 0)
            self._grid.addWidget(self._settings_card, 3, 0)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)
            self._grid.setRowStretch(0, 0)
            self._grid.setRowStretch(1, 0)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        w = event.size().width()
        self._relayout_cards(w)
        self._footer_hint.setVisible(w >= 640)
        if not self.isMaximized():
            inferred = "compact" if event.size().width() < self.COMPACT_BREAKPOINT else "standard"
            self._window_mode = inferred
            self._sync_mode_buttons(inferred)
        else:
            self._window_mode = "full"
            self._sync_mode_buttons("full")

    def _on_preview_toggled(self, checked: bool) -> None:
        if not checked:
            self._preview_view.setPixmap(QtGui.QPixmap())
            self._preview_view.setText("Camera stays off until you say 'Hey Handy' or enable preview.")
            self._detected_label.setText("Detected: —")
            self._highlight_gesture_row("")
        self.previewToggled.emit(checked)

    def _highlight_gesture_row(self, active_gesture: str) -> None:
        for key, row in self._gesture_rows.items():
            want = "true" if key == active_gesture else "false"
            if row.property("active") != want:
                row.setProperty("active", want)
                row.style().unpolish(row)
                row.style().polish(row)

    @QtCore.Slot(str, float)
    def update_state(self, state: str, remaining_s: float) -> None:
        if state == "armed":
            rem = "Always-On" if math.isinf(remaining_s) else f"{max(0.0, remaining_s):.1f}s"
            self._state_pill.setText(f"● ARMED • {rem}")
            self._state_pill.setProperty("armed", "true")
        else:
            self._state_pill.setText(f"● Sleeping — say '{self._phrase_edit.text().title()}'")
            self._state_pill.setProperty("armed", "false")
        self._state_pill.style().unpolish(self._state_pill)
        self._state_pill.style().polish(self._state_pill)

    @QtCore.Slot(str, str, str)
    def update_last_action(self, _action: str, label: str, detail: str) -> None:
        text = f"Last action: {label}" + (f" ({detail})" if detail else "")
        self._last_action_label.setText(text)

    @QtCore.Slot(float)
    def update_mic_level(self, level: float) -> None:
        self._mic_bar.setValue(max(0, min(100, int(level * 100))))

    @QtCore.Slot(str)
    def update_mic_device(self, device_name: str) -> None:
        self._mic_status_label.setText(f"Mic ({device_name[:26]}):")

    @QtCore.Slot(object)
    def update_extension_status(self, status: ExtensionStatus) -> None:
        if status.connected:
            tab = status.active_tab_title or "No active media tab reported yet"
            kind = f" [{status.media_type}]" if status.media_type else ""
            self._ext_label.setText(f"Target: Extension ({status.browser or 'Browser'}) — {tab}{kind}")
        else:
            self._ext_label.setText(
                f"Target: Desktop MPRIS + Hyprland active (extension optional on ws://127.0.0.1:{self._config.ws_port})"
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
        if frame.gesture and frame.gesture != "None":
            self._detected_label.setText(
                f"Detected (live): {GESTURE_LABELS.get(frame.gesture, frame.gesture)} ({frame.confidence:.0%})"
            )
            self._highlight_gesture_row(frame.gesture)
        else:
            self._highlight_gesture_row("")
            self._detected_label.setText(
                "Detected (live): Hand visible — hold a gesture clearly" if frame.landmarks else "Detected (live): —"
            )

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
        self._model_label.setText("Models: Offline Ready (MediaPipe + sherpa-onnx)")
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
        self._mic_combo.setCurrentIndex(0)
        self._sens_slider.setValue(round(defaults.wake_sensitivity * 100))
        self._window_slider.setValue(round(defaults.wake_window_s))
        self._stability_slider.setValue(defaults.stability_frames)
        self._conf_slider.setValue(round(defaults.min_confidence * 100))
        self._vol_slider.setValue(defaults.volume_step)
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
            wake_sensitivity=self._sens_slider.value() / 100.0,
            wake_window_s=float(self._window_slider.value()),
            post_action_grace_s=self._config.post_action_grace_s,
            action_cooldown_s=self._config.action_cooldown_s,
            volume_repeat_s=self._config.volume_repeat_s,
            volume_step=self._vol_slider.value(),
            volume_mode=str(self._vol_mode_combo.currentData()),
            stability_frames=self._stability_slider.value(),
            min_confidence=self._conf_slider.value() / 100.0,
            min_hand_span=self._config.min_hand_span,
            keep_camera_warm=self._warm_cam_chk.isChecked(),
            always_on_gestures=self._always_on_chk.isChecked(),
            show_desktop_hud=self._desk_hud_chk.isChecked(),
            show_tab_hud=self._tab_hud_chk.isChecked(),
            sound_feedback=self._sound_chk.isChecked(),
            ws_host=self._config.ws_host,
            ws_port=self._config.ws_port,
            camera_index=self._camera_spin.value(),
            mic_device=self._mic_combo.currentData(),
            window_width=self._config.window_width if self.isMaximized() else self.width(),
            window_height=self._config.window_height if self.isMaximized() else self.height(),
            window_mode=self._window_mode,
            gesture_map={k: str(c.currentData()) for k, c in self._gesture_combos.items()},
        ).normalized()
        self._config = cfg
        self.configSaved.emit(cfg)
        self._save_btn.setText("✓ Saved!")
        self._save_feedback_timer.start(1400)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:  # noqa: N802
        if self._preview_toggle.isChecked():
            self._preview_toggle.setChecked(False)
        super().hideEvent(event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        if self._preview_toggle.isChecked():
            self._preview_toggle.setChecked(False)
        if self._minimize_to_tray:
            event.ignore()
            self.hide()
        else:
            super().closeEvent(event)
