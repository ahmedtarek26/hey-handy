"""CLI entrypoint for Hey Handy desktop app and model setup."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

from . import ensure_qt_env
from .config import HeyHandyConfig
from .models import ensure_models, resolve_model_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hey-handy",
        description="Wake-word gated hand gesture controller for your active browser video/audio tab.",
    )
    parser.add_argument("--settings", action="store_true", help="Open the Settings & Camera Test window on launch.")
    parser.add_argument("--always-on", action="store_true", help="Keep gesture recognition active without wake word.")
    parser.add_argument("--no-tray", action="store_true", help="Show Settings window directly and quit when closed.")
    parser.add_argument("--download-models", action="store_true", help="Download offline MediaPipe & wake-word models and exit.")
    parser.add_argument("--models-dir", type=Path, default=None, help="Override directory for downloaded ML models.")
    parser.add_argument("--port", type=int, default=None, help="Override localhost WebSocket port (default: 17421).")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.download_models:
        paths = ensure_models(
            models_dir=args.models_dir,
            progress_cb=lambda msg, frac: print(f"\r{msg} {frac:4.0%}", end="", flush=True),
        )
        print(f"\nModels ready in: {paths.base_dir}")
        return 0

    ensure_qt_env()
    from PySide6 import QtCore, QtWidgets

    from .controller import AppController
    from .ui import FloatingHud, HandyTrayIcon, SettingsWindow

    config = HeyHandyConfig.load()
    if args.always_on:
        config.always_on_gestures = True
    if args.port:
        config.ws_port = args.port
    config.normalized()

    models = resolve_model_paths(args.models_dir)
    if not models.all_ready:
        print("Downloading offline Hey Handy models on first launch...")
        try:
            models = ensure_models(
                models_dir=args.models_dir,
                progress_cb=lambda msg, frac: print(f"\r{msg} {frac:4.0%}", end="", flush=True),
            )
            print("")
        except Exception as exc:
            print(f"\nWarning: Model download failed ({exc}). You can retry from Settings.")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Hey Handy")
    app.setDesktopFileName("hey-handy")
    tray_available = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable() and not args.no_tray
    app.setQuitOnLastWindowClosed(not tray_available)

    controller = AppController(config=config, models=models)
    hud = FloatingHud()
    settings = SettingsWindow(
        config=config,
        models_ready=models.all_ready,
        minimize_to_tray=tray_available,
    )

    tray: HandyTrayIcon | None = None
    if tray_available:
        tray = HandyTrayIcon(always_on=config.always_on_gestures)
        tray.openSettingsRequested.connect(lambda: (settings.show(), settings.raise_(), settings.activateWindow()))
        tray.wakeRequested.connect(controller.wake_now)
        tray.alwaysOnToggled.connect(controller.set_always_on)
        tray.micPausedToggled.connect(controller.set_mic_paused)
        tray.quitRequested.connect(app.quit)
        tray.show()

    def _on_state(state: str, remaining: float) -> None:
        settings.update_state(state, remaining)
        if tray:
            tray.set_state(
                state,
                mic_paused=controller.wake_listener.is_paused,
                always_on=controller.config.always_on_gestures,
            )
        if controller.config.show_desktop_hud:
            if state == "armed":
                hud.show_armed(remaining)
            else:
                hud.show_sleeping()

    def _on_action(_action: str, label: str, detail: str) -> None:
        settings.update_last_action(_action, label, detail)
        if controller.config.show_desktop_hud:
            hud.show_action(label, detail)

    controller.stateChanged.connect(_on_state)
    controller.actionExecuted.connect(_on_action)
    controller.extensionChanged.connect(settings.update_extension_status)
    controller.previewReady.connect(settings.update_preview)
    controller.micLevelChanged.connect(settings.update_mic_level)
    controller.micDeviceChanged.connect(settings.update_mic_device)
    controller.errorOccurred.connect(lambda msg: print(f"[Hey Handy] {msg}", file=sys.stderr))

    settings.configSaved.connect(controller.apply_config)
    settings.wakeClicked.connect(controller.wake_now)
    settings.actionTestClicked.connect(controller.trigger_action)
    settings.previewToggled.connect(controller.set_preview_enabled)
    settings.modelsReady.connect(controller.reload_models)

    app.aboutToQuit.connect(controller.shutdown)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Periodically let Python process SIGINT under Qt's event loop.
    sig_timer = QtCore.QTimer()
    sig_timer.start(250)
    sig_timer.timeout.connect(lambda: None)

    controller.start()
    if args.settings or not tray_available:
        settings.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
