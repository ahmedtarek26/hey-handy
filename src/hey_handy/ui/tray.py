"""System tray icon and quick menu for Hey Handy."""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


def make_tray_icon(state: str = "sleeping") -> QtGui.QIcon:
    """Render a crisp geometric hand/badge tray icon for the current state."""
    color_map = {
        "armed": QtGui.QColor("#2dd4bf"),
        "paused": QtGui.QColor("#f59e0b"),
        "sleeping": QtGui.QColor("#64748b"),
    }
    accent = color_map.get(state, color_map["sleeping"])

    pix = QtGui.QPixmap(64, 64)
    pix.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

    p.setBrush(QtGui.QColor("#111827"))
    p.setPen(QtGui.QPen(accent, 4))
    p.drawRoundedRect(4, 4, 56, 56, 16, 16)

    # Stylized raised fingers / palm icon
    p.setBrush(accent)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawRoundedRect(20, 29, 24, 20, 7, 7)
    for idx, (x, h) in enumerate([(20, 17), (26, 21), (32, 20), (38, 16)]):
        p.drawRoundedRect(x, 31 - h, 4, h + 4, 2, 2)
    p.drawRoundedRect(14, 34, 7, 10, 3, 3)

    p.end()
    return QtGui.QIcon(pix)


class HandyTrayIcon(QtWidgets.QSystemTrayIcon):
    """Cross-platform tray icon for Hey Handy background operation."""

    openSettingsRequested = QtCore.Signal()
    wakeRequested = QtCore.Signal()
    alwaysOnToggled = QtCore.Signal(bool)
    micPausedToggled = QtCore.Signal(bool)
    quitRequested = QtCore.Signal()

    def __init__(self, always_on: bool = False, parent: QtCore.QObject | None = None) -> None:
        super().__init__(make_tray_icon("armed" if always_on else "sleeping"), parent)
        self.setToolTip("Hey Handy — Say 'Hey Handy' to control active media")

        menu = QtWidgets.QMenu()
        self._status_action = menu.addAction("Status: Listening for 'Hey Handy'")
        self._status_action.setEnabled(False)
        menu.addSeparator()

        wake_action = menu.addAction("Wake Handy Now")
        wake_action.triggered.connect(self.wakeRequested)

        self._always_on_action = menu.addAction("Always-On Gestures")
        self._always_on_action.setCheckable(True)
        self._always_on_action.setChecked(always_on)
        self._always_on_action.toggled.connect(self.alwaysOnToggled)

        self._snooze_action = menu.addAction("Snooze Microphone")
        self._snooze_action.setCheckable(True)
        self._snooze_action.toggled.connect(self.micPausedToggled)

        menu.addSeparator()
        settings_action = menu.addAction("Settings & Camera Test...")
        settings_action.triggered.connect(self.openSettingsRequested)

        quit_action = menu.addAction("Quit Hey Handy")
        quit_action.triggered.connect(self.quitRequested)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QtWidgets.QSystemTrayIcon.ActivationReason.Trigger,
            QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.openSettingsRequested.emit()

    def set_state(self, state: str, mic_paused: bool = False, always_on: bool = False) -> None:
        self._always_on_action.blockSignals(True)
        self._always_on_action.setChecked(always_on)
        self._always_on_action.blockSignals(False)

        self._snooze_action.blockSignals(True)
        self._snooze_action.setChecked(mic_paused)
        self._snooze_action.blockSignals(False)

        if mic_paused and not always_on:
            self.setIcon(make_tray_icon("paused"))
            self._status_action.setText("Status: Microphone snoozed")
        elif state == "armed" or always_on:
            self.setIcon(make_tray_icon("armed"))
            self._status_action.setText("Status: Armed — show gesture")
        else:
            self.setIcon(make_tray_icon("sleeping"))
            self._status_action.setText("Status: Listening for 'Hey Handy'")
