"""Local WebSocket bridge linking Hey Handy Desktop with the active-tab browser extension."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Set


@dataclass(frozen=True)
class ExtensionStatus:
    connected: bool
    client_count: int
    browser: str = ""
    active_tab_title: str = ""
    media_type: str = ""  # "video", "audio", or ""


class WSBridge:
    """Runs an asyncio WebSocket server on localhost for the browser extension."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 17421,
        on_status_change: Optional[Callable[[ExtensionStatus], None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_status_change = on_status_change

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._clients: Set[Any] = set()
        self._pending: Dict[str, asyncio.Future[dict]] = {}
        self._status = ExtensionStatus(connected=False, client_count=0)
        self._stop_future: Optional[asyncio.Future[None]] = None
        self._ready_event = threading.Event()
        self._start_error: Optional[str] = None

    @property
    def status(self) -> ExtensionStatus:
        return self._status

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready_event.clear()
        self._start_error = None
        self._thread = threading.Thread(target=self._run_thread, name="hey-handy-ws", daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

    def stop(self) -> None:
        loop = self._loop
        stop_fut = self._stop_future
        if loop and stop_fut and not stop_fut.done():
            loop.call_soon_threadsafe(stop_fut.set_result, None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        self._loop = None

    def send_command(self, action: str, **kwargs: Any) -> Optional[dict]:
        """Synchronously dispatch a media command to connected extension clients."""
        loop = self._loop
        if not loop or not self._clients:
            return None
        fut = asyncio.run_coroutine_threadsafe(
            self._async_send_command(action, **kwargs),
            loop,
        )
        try:
            return fut.result(timeout=0.85)
        except Exception:
            return None

    def broadcast_hud(self, payload: dict) -> None:
        """Broadcast non-blocking HUD state updates to the active browser tab."""
        loop = self._loop
        if not loop or not self._clients:
            return
        msg = json.dumps({"type": "hud", **payload})
        asyncio.run_coroutine_threadsafe(self._async_broadcast(msg), loop)

    def _emit_status(self, browser: str = "", title: str = "", media_type: str = "") -> None:
        self._status = ExtensionStatus(
            connected=len(self._clients) > 0,
            client_count=len(self._clients),
            browser=browser or (self._status.browser if self._clients else ""),
            active_tab_title=title if self._clients else "",
            media_type=media_type if self._clients else "",
        )
        if self.on_status_change:
            self.on_status_change(self._status)

    async def _async_broadcast(self, raw: str) -> None:
        stale = []
        for ws in list(self._clients):
            try:
                await ws.send(raw)
            except Exception:
                stale.append(ws)
        if stale:
            for ws in stale:
                self._clients.discard(ws)
            self._emit_status()

    async def _async_send_command(self, action: str, **kwargs: Any) -> Optional[dict]:
        if not self._clients:
            return None
        cmd_id = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        resp_fut: asyncio.Future[dict] = loop.create_future()
        self._pending[cmd_id] = resp_fut
        payload = json.dumps({"type": "command", "id": cmd_id, "action": action, **kwargs})

        sent = False
        for ws in list(self._clients):
            try:
                await ws.send(payload)
                sent = True
            except Exception:
                self._clients.discard(ws)

        if not sent:
            self._pending.pop(cmd_id, None)
            self._emit_status()
            return None

        try:
            return await asyncio.wait_for(resp_fut, timeout=0.65)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending.pop(cmd_id, None)

    async def _handler(self, websocket: Any) -> None:
        self._clients.add(websocket)
        self._emit_status()
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                mtype = msg.get("type")
                if mtype == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                elif mtype == "hello":
                    self._emit_status(
                        browser=str(msg.get("browser") or "Browser"),
                        title=str(msg.get("title") or ""),
                        media_type=str(msg.get("mediaType") or ""),
                    )
                elif mtype == "tab_status":
                    self._emit_status(
                        browser=str(msg.get("browser") or self._status.browser),
                        title=str(msg.get("title") or ""),
                        media_type=str(msg.get("mediaType") or ""),
                    )
                elif mtype == "command_result":
                    cmd_id = str(msg.get("id") or "")
                    fut = self._pending.get(cmd_id)
                    if fut and not fut.done():
                        fut.set_result(msg)
                    if msg.get("title") or msg.get("mediaType"):
                        self._emit_status(
                            title=str(msg.get("title") or self._status.active_tab_title),
                            media_type=str(msg.get("mediaType") or self._status.media_type),
                        )
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            self._emit_status()

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._serve())
        except Exception as exc:
            self._start_error = str(exc)
            self._ready_event.set()
        finally:
            loop.close()

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve

        self._stop_future = asyncio.get_running_loop().create_future()
        async with serve(self._handler, self.host, self.port):
            self._ready_event.set()
            await self._stop_future
