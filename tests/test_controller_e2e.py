"""End-to-end AppController + WSBridge + GestureEvent dispatch test."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time

from hey_handy import ensure_qt_env
from hey_handy.config import HeyHandyConfig
from hey_handy.gesture_engine import GestureEvent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_controller_wakes_dispatches_to_extension_and_broadcasts_hud(tmp_path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    ensure_qt_env()
    from PySide6 import QtWidgets
    from websockets.asyncio.client import connect

    from hey_handy.controller import AppController
    from hey_handy.models import resolve_model_paths

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    port = _free_port()
    cfg = HeyHandyConfig(ws_port=port, sound_feedback=False).normalized()
    controller = AppController(config=cfg, models=resolve_model_paths(tmp_path / "empty_models"))

    executed = []
    controller.actionExecuted.connect(lambda act, lbl, det: executed.append((act, lbl, det)))
    controller.bridge.start()

    hud_events = []
    cmd_events = []

    async def _client() -> None:
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(
                json.dumps({"type": "hello", "browser": "Zen", "title": "Podcast Tab", "mediaType": "audio"})
            )
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") == "hud":
                    hud_events.append(msg)
                elif msg.get("type") == "command":
                    cmd_events.append(msg)
                    await ws.send(
                        json.dumps(
                            {
                                "type": "command_result",
                                "id": msg["id"],
                                "handled": True,
                                "label": "Paused",
                                "title": "Podcast Tab",
                                "mediaType": "audio",
                            }
                        )
                    )
                    if msg.get("action") == "pause":
                        return

    def _drive_controller() -> None:
        deadline = time.monotonic() + 2.0
        while not controller.bridge.status.connected and time.monotonic() < deadline:
            time.sleep(0.02)
        controller._emit_armed(8.0)
        controller._on_gesture_event(
            GestureEvent(gesture="Closed_Fist", action="pause", confidence=0.92, continuous=False)
        )

    driver = threading.Thread(target=_drive_controller, daemon=True)
    driver.start()
    try:
        asyncio.run(asyncio.wait_for(_client(), timeout=3.0))
        driver.join(timeout=1.5)
        app.processEvents()
        assert len(cmd_events) == 1 and cmd_events[0]["action"] == "pause"
        assert any(h.get("state") == "armed" for h in hud_events)
        assert executed and executed[0][0] == "pause"
    finally:
        driver.join(timeout=1.0)
        controller.shutdown()
