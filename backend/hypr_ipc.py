"""Raw Hyprland IPC event-stream client (socket2).

Independent of the Omarchy shell -- connects directly to Hyprland's own
per-instance event socket. Not an Omarchy-documented convention; no `socat`
dependency, a raw asyncio Unix connection is enough.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

NAV_EVENT_PREFIXES = ("workspace>>", "workspacev2>>", "activewindow>>", "activewindowv2>>")
RECONNECT_MIN_S = 0.5
RECONNECT_MAX_S = 5.0


def socket2_path() -> str | None:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        return None
    return f"{runtime_dir}/hypr/{signature}/.socket2.sock"


class HyprSocketClient:
    """Connects to Hyprland's socket2 and dispatches nav / config-reload
    events. Reconnects with backoff on compositor restart so a Hyprland
    restart never takes down the rest of the daemon."""

    def __init__(self, on_nav_event: Callable[[], None],
                 on_config_reloaded: Callable[[], Awaitable[None] | None]):
        self._on_nav_event = on_nav_event
        self._on_config_reloaded = on_config_reloaded
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    async def run(self) -> None:
        backoff = RECONNECT_MIN_S
        while not self._stop:
            path = socket2_path()
            if not path:
                await asyncio.sleep(RECONNECT_MAX_S)
                continue
            try:
                reader, _writer = await asyncio.open_unix_connection(path)
                backoff = RECONNECT_MIN_S
                await self._invoke_config_reloaded()
                await self._read_loop(reader)
            except (OSError, ConnectionError):
                pass
            if self._stop:
                return
            await asyncio.sleep(backoff)
            backoff = min(RECONNECT_MAX_S, backoff * 2)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        while not self._stop:
            line = await reader.readline()
            if not line:
                return  # socket closed -- outer loop reconnects
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            if text.startswith(NAV_EVENT_PREFIXES):
                self._on_nav_event()
            elif text.startswith("configreloaded>>"):
                await self._invoke_config_reloaded()

    async def _invoke_config_reloaded(self) -> None:
        result = self._on_config_reloaded()
        if asyncio.iscoroutine(result):
            await result
