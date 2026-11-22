"""Offscreen PySide6 UI + dependency import compatibility tests."""

from __future__ import annotations

import os


def test_qt_and_cv_imports_and_ui_offscreen() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from hey_handy import ensure_qt_env

    ensure_qt_env()
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    import cv2  # noqa: F401
    import mediapipe  # noqa: F401
    import sherpa_onnx  # noqa: F401

    from hey_handy.config import HeyHandyConfig
    from hey_handy.ui.hud import FloatingHud
    from hey_handy.ui.settings_window import SettingsWindow
    from hey_handy.ui.tray import make_tray_icon
    from hey_handy.ws_bridge import ExtensionStatus

    cfg = HeyHandyConfig()

    hud = FloatingHud()
    hud.show_armed(8.0)
    hud.show_action("Paused", "YouTube — Video")
    hud.show_sleeping()

    win = SettingsWindow(config=cfg, models_ready=True, minimize_to_tray=False)
    win.update_state("armed", 6.5)
    win.update_extension_status(
        ExtensionStatus(
            connected=True,
            client_count=1,
            browser="Chromium",
            active_tab_title="Lo-fi Mix",
            media_type="audio",
        )
    )
    win.show()
    app.processEvents()
    assert win._two_column_active is True

    win.apply_window_mode("compact")
    app.processEvents()
    assert win.width() == 500
    assert win._two_column_active is False

    win.apply_window_mode("standard")
    app.processEvents()
    assert win.width() == 980
    assert win._two_column_active is True

    icon = make_tray_icon("armed")
    assert not icon.isNull()

    win.close()
    hud.close()
    win.deleteLater()
    hud.deleteLater()
    app.processEvents()
