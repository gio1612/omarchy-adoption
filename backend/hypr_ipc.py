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


def _newest_live_signature(runtime_dir: str) -> str | None:
    """Finds the running Hyprland instance without trusting the environment.

    When launched as a systemd --user service at login, this daemon often
    starts BEFORE Hyprland has exported HYPRLAND_INSTANCE_SIGNATURE to the
    user manager, so the variable can be permanently absent. The runtime dir
    is ground truth: pick the most recently touched instance dir that
    actually has a live .socket2.sock."""
    base = os.path.join(runtime_dir, "hypr")
    try:
        entries = list(os.scandir(base))
    except OSError:
        return None
    best: tuple[float, str] | None = None
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
            st = os.stat(os.path.join(entry.path, ".socket2.sock"))
        except OSError:
            continue
        if best is None or st.st_mtime > best[0]:
            best = (st.st_mtime, entry.name)
    return best[1] if best else None


def socket2_path(runtime_dir: str | None = None,
                  signature: str | None = None) -> str | None:
    runtime_dir = runtime_dir or os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    signature = signature or os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        signature = _newest_live_signature(runtime_dir)
    if not signature:
        return None
    path = f"{runtime_dir}/hypr/{signature}/.socket2.sock"
    return path if os.path.exists(path) else None


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
                # When auto-started at login before Hyprland exports its env
                # to systemd --user, this daemon won't have the signature.
                # Now that we know it's live, set it so child processes
                # (hyprctl binds -j for the allowlist) inherit it.
                if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
                    sig = os.path.basename(os.path.dirname(path))
                    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = sig
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
