"""Integration tests for the localhost WebSocket bridge."""

from __future__ import annotations

import asyncio
import json
import socket

from hey_handy.ws_bridge import WSBridge


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_ws_bridge_command_roundtrip_and_hud_broadcast() -> None:
    from websockets.asyncio.client import connect

    port = _free_port()
    statuses = []
    bridge = WSBridge(host="127.0.0.1", port=port, on_status_change=statuses.append)
    bridge.start()

    received_hud = []

    async def _run_client() -> None:
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "browser": "Chromium",
                        "title": "Demo Video",
                        "mediaType": "video",
                    }
                )
            )
            await ws.send(json.dumps({"type": "ping"}))
            pong = json.loads(await ws.recv())
            assert pong == {"type": "pong"}

            # Trigger command + hud from a worker thread while client handles messages
            async def _reply_loop() -> None:
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    if msg.get("type") == "command":
                        await ws.send(
                            json.dumps(
                                {
                                    "type": "command_result",
                                    "id": msg["id"],
                                    "handled": True,
                                    "label": "Paused",
                                    "title": "Demo Video",
                                    "mediaType": "video",
                                }
                            )
                        )
                    elif msg.get("type") == "hud":
                        received_hud.append(msg)
                        if msg.get("state") == "armed":
                            return

            task = asyncio.create_task(_reply_loop())
            res = await asyncio.to_thread(bridge.send_command, "play_pause")
            assert res is not None and res["handled"] is True
            assert res["label"] == "Paused"
            await asyncio.to_thread(bridge.broadcast_hud, {"state": "armed", "remaining": 8})
            await asyncio.wait_for(task, timeout=2.0)

    try:
        asyncio.run(_run_client())
        assert any(m.get("state") == "armed" for m in received_hud)
        assert any(s.connected and s.media_type == "video" for s in statuses)
    finally:
        bridge.stop()
