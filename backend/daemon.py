#!/usr/bin/env python3
"""Omarchy Adoption Tracker background daemon.

Ties together evdev input classification, Hyprland IPC nav-attribution, and
the SUPER+K cheatsheet notification into local SQLite aggregates, served to
the plugin's Quickshell BarWidget/Panel over a Unix socket. Local-only: no
network calls, no raw keycodes or content ever persisted.

Run standalone with --self-test to sanity-check the environment without
starting the full daemon.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time

import evdev

from evdev_reader import EvdevSource
from hypr_ipc import HyprSocketClient
from keybinds import NavComboMatcher, fetch_nav_allowlist
from nav_attrib import EpisodeCoalescer, NavAttributor
from protocol import PROTOCOL_VERSION, dumps, event, parse_line, response
from storage import Storage

DAEMON_VERSION = "0.1.0"
SLUG = "omarchy-adoption-tracker"

FLUSH_INTERVAL_S = 2.0


def data_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, SLUG)


def default_db_path() -> str:
    return os.path.join(data_dir(), "tracker.db")


def runtime_socket_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(base, SLUG)


def socket_path() -> str:
    return os.path.join(runtime_socket_dir(), "daemon.sock")


class Daemon:
    def __init__(self) -> None:
        os.makedirs(data_dir(), exist_ok=True)
        self.storage = Storage(default_db_path())
        self.nav_matcher = NavComboMatcher()
        self.attributor = NavAttributor()
        self.coalescer = EpisodeCoalescer()
        self.clients: set[asyncio.StreamWriter] = set()
        self.evdev_source = EvdevSource(
            self.nav_matcher,
            on_typing_burst=self._on_typing_burst,
            on_mouse_activity=self.attributor.note_mouse_activity,
            on_keyboard_nav_combo=self.attributor.note_keyboard_nav_combo,
        )
        self.hypr_client = HyprSocketClient(
            on_nav_event=self._on_nav_event,
            on_config_reloaded=self._refresh_allowlist,
        )
        self._stopping = False

    def _on_typing_burst(self, burst) -> None:
        self.storage.queue_typing_burst(burst)

    def _on_nav_event(self) -> None:
        episode_ts = self.coalescer.add_event(time.monotonic())
        if episode_ts is None:
            return
        method = self.attributor.attribute(episode_ts)
        if method is not None:
            self.storage.queue_nav_event(method, time.time())

    async def _refresh_allowlist(self) -> None:
        try:
            allowlist = await fetch_nav_allowlist()
            self.nav_matcher.update_allowlist(allowlist)
        except OSError:
            pass

    async def _flush_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            burst = self.evdev_source.check_idle()
            if burst is not None:
                self.storage.queue_typing_burst(burst)
            if self.storage.flush():
                await self._push_stats_update()

    async def _push_stats_update(self) -> None:
        if not self.clients:
            return
        payload = (dumps(event("stats_update", self.storage.get_stats("today"))) + "\n"
                   ).encode("utf-8")
        dead = []
        for writer in self.clients:
            try:
                writer.write(payload)
                await writer.drain()
            except (ConnectionError, OSError):
                dead.append(writer)
        for writer in dead:
            self.clients.discard(writer)

    async def _handle_client(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter) -> None:
        self.clients.add(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                message = parse_line(line.decode("utf-8", errors="replace"))
                if message is None:
                    continue
                await self._process_message(message, writer)
        except (ConnectionError, OSError):
            pass
        finally:
            self.clients.discard(writer)
            try:
                writer.close()
            except OSError:
                pass

    async def _process_message(self, message: dict, writer: asyncio.StreamWriter) -> None:
        if message.get("type") == "event":
            if message.get("name") == "cheatsheet_invoked":
                try:
                    ts = float(message.get("ts"))
                except (TypeError, ValueError):
                    ts = time.time()
                self.storage.queue_cheatsheet_invocation(ts)
            return  # fire-and-forget, no response expected

        request_id = message.get("id")
        command = message.get("command")
        if command == "hello":
            result = response(request_id, True,
                               {"protocol": PROTOCOL_VERSION, "daemon_version": DAEMON_VERSION})
        elif command == "stats":
            window = message.get("window", "today")
            result = response(request_id, True, self.storage.get_stats(window))
        elif command == "records":
            result = response(request_id, True, self.storage.get_records())
        elif command == "history":
            try:
                days = int(message.get("days", 14))
            except (TypeError, ValueError):
                days = 14
            result = response(request_id, True, self.storage.get_daily_history(days))
        elif command == "set_mouse_weight":
            try:
                weight = self.storage.set_mouse_weight(message.get("value"))
                result = response(request_id, True, {"mouse_weight": weight})
                await self._push_stats_update()  # widgets re-render the split
            except (TypeError, ValueError) as exc:
                result = response(request_id, False, code="invalid_value",
                                  message=str(exc))
        else:
            result = response(request_id, False, code="unknown_command",
                               message=f"Unknown command: {command!r}")
        writer.write((dumps(result) + "\n").encode("utf-8"))
        await writer.drain()

    async def run(self) -> None:
        await self._refresh_allowlist()

        sock_path = socket_path()
        os.makedirs(os.path.dirname(sock_path), mode=0o700, exist_ok=True)
        if os.path.exists(sock_path):
            os.remove(sock_path)
        server = await asyncio.start_unix_server(self._handle_client, path=sock_path)
        os.chmod(sock_path, 0o600)

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)

        tasks = [
            asyncio.create_task(self.evdev_source.run()),
            asyncio.create_task(self.hypr_client.run()),
            asyncio.create_task(self._flush_loop()),
        ]

        await stop_event.wait()
        self._stopping = True
        self.evdev_source.stop()
        self.hypr_client.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        burst = self.evdev_source.flush_typing()
        if burst is not None:
            self.storage.queue_typing_burst(burst)
        self.storage.flush()
        self.storage.close()

        server.close()
        await server.wait_closed()
        try:
            os.remove(sock_path)
        except OSError:
            pass


def self_test() -> bool:
    ok = True

    try:
        opened = False
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                dev.close()
                opened = True
                break
            except OSError:
                continue
        if not opened:
            print("self-test: no /dev/input/event* device could be opened "
                  "(check you're in the 'input' group)", file=sys.stderr)
            ok = False
    except Exception as exc:  # noqa: BLE001 -- self-test wants to report, not crash
        print(f"self-test: evdev check failed: {exc}", file=sys.stderr)
        ok = False

    try:
        os.makedirs(data_dir(), exist_ok=True)
        store = Storage(default_db_path())
        store.close()
    except Exception as exc:  # noqa: BLE001
        print(f"self-test: sqlite schema check failed: {exc}", file=sys.stderr)
        ok = False

    try:
        os.makedirs(runtime_socket_dir(), mode=0o700, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        print(f"self-test: runtime socket dir check failed: {exc}", file=sys.stderr)
        ok = False

    return ok


def main() -> int:
    if "--self-test" in sys.argv:
        ok = self_test()
        print("self-test: OK" if ok else "self-test: FAILED")
        return 0 if ok else 1

    asyncio.run(Daemon().run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
