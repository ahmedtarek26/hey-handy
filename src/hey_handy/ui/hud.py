"""Minimal translucent click-through desktop HUD pill for wake and action feedback."""

from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets


class FloatingHud(QtWidgets.QWidget):
    """Non-focus-stealing corner pill showing 'Hey Handy' armed state and last action."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
            | QtCore.Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(310, 62)

        self._title = "Hey Handy"
        self._subtitle = "Listening..."
        self._accent = QtGui.QColor("#2dd4bf")
        self._armed = False

        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_armed(self, remaining_s: float) -> None:
        self._armed = True
        self._accent = QtGui.QColor("#2dd4bf")
        self._title = "Hey Handy • Ready"
        if math.isinf(remaining_s):
            self._subtitle = "Always-on gesture mode"
        else:
            self._subtitle = f"Show a gesture ({max(1, math.ceil(remaining_s))}s)"
        self._hide_timer.stop()
        self._position_top_right()
        self.show()
        self.update()

    def show_action(self, label: str, detail: str = "") -> None:
        self._accent = QtGui.QColor("#22c55e")
        self._title = label
        self._subtitle = detail or "Executed on active media"
        self._position_top_right()
        self.show()
        self.update()
        if not self._armed:
            self._hide_timer.start(1800)

    def show_sleeping(self) -> None:
        self._armed = False
        self._hide_timer.start(1200)
        self.update()

    def _position_top_right(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self.move(geo.right() - self.width() - 22, geo.top() + 22)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        del event
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        rect = QtCore.QRectF(1, 1, self.width() - 2, self.height() - 2)
        p.setBrush(QtGui.QColor(15, 18, 25, 228))
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 36), 1.0))
        p.drawRoundedRect(rect, 16, 16)

        # Glowing status dot
        dot_center = QtCore.QPointF(24, self.height() / 2.0)
        glow = QtGui.QColor(self._accent)
        glow.setAlpha(60)
        p.setBrush(glow)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(dot_center, 11, 11)

        p.setBrush(self._accent)
        p.drawEllipse(dot_center, 5.5, 5.5)

        title_font = QtGui.QFont(self.font())
        title_font.setPointSize(11)
        title_font.setWeight(QtGui.QFont.Weight.DemiBold)
        p.setFont(title_font)
        p.setPen(QtGui.QColor("#f8fafc"))
        p.drawText(
            QtCore.QRectF(44, 10, self.width() - 56, 22),
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
            self._title,
        )

        sub_font = QtGui.QFont(self.font())
        sub_font.setPointSize(9)
        p.setFont(sub_font)
        p.setPen(QtGui.QColor("#94a3b8"))
        p.drawText(
            QtCore.QRectF(44, 32, self.width() - 56, 20),
            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
            self._subtitle,
        )
