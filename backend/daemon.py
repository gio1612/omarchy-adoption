#!/usr/bin/env python3
"""Omarchy Adoption Tracker background daemon.

Ties together evdev input classification, Hyprland IPC nav-attribution, and
the SUPER+K cheatsheet combo detected straight off the raw keyboard stream
into local SQLite aggregates, served to the plugin's Quickshell
BarWidget/Panel over a Unix socket. Local-only: no network calls, no raw
keycodes or content ever persisted.

Structure:

  * `Daemon` owns lifecycle only -- sockets, tasks, ordered shutdown.
  * `_COMMANDS` is the socket protocol's dispatch table; each handler is a
    small coroutine that takes the request and returns a result dict.
  * every SQLite call goes through `_db()`, which runs it on a worker thread
    behind a single lock, so a slow query can never stall the event loop
    (and with it, evdev reads).

Run standalone with --self-test to sanity-check the environment without
starting the full daemon, or --version to print the daemon version.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import glob
import logging
import os
import signal
import sys
import time
from collections.abc import Awaitable, Callable

import evdev
from app_launch_attrib import AppLaunchAttributor
from evdev_reader import EvdevSource
from hypr_ipc import HyprSocketClient
from keybinds import NavComboMatcher, fetch_keybind_allowlists
from nav_attrib import EpisodeCoalescer, NavAttributor
from protocol import PROTOCOL_VERSION, dumps, event, parse_line, response
from storage import Storage, StorageClosed

DAEMON_VERSION = "0.2.0"
SLUG = "omarchy-adoption-tracker"

FLUSH_INTERVAL_S = 2.0

# How often the retention sweep is *considered*. Storage.prune_if_due() is
# the real gate -- it runs at most once per local day -- so this only needs
# to be frequent enough that a machine left on across midnight still sweeps.
PRUNE_CHECK_INTERVAL_S = 3600.0

# Max audit-log lines kept in memory for the panel's `get_log` view.
AUDIT_LOG_LIMIT = 400

# Cap on how many audit lines one `get_log` response carries. The panel polls
# this while the Debug Audit view is open and rebuilds its list from the
# answer; shipping the whole 400-line ring every poll is what made the shell
# hitch, so the newest slice is the default and the client can ask for more.
AUDIT_LOG_DEFAULT_LIMIT = 120

VALID_WINDOWS = ("today", "week", "month", "all")

# Ceiling on any single wait during shutdown. The systemd unit's
# TimeoutStopSec is the outer bound; staying well inside it means we always
# get to flush and close storage rather than being SIGKILLed mid-write.
SHUTDOWN_TIMEOUT_S = 3.0

log = logging.getLogger(SLUG)


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


def normalize_window(value) -> str:
    window = str(value or "today").lower()
    return window if window in VALID_WINDOWS else "today"


class _Client:
    """One connected panel/widget. Tracks the stats window that client last
    asked for, so pushed updates match what it is actually displaying --
    previously every push carried 'today' regardless, so a panel set to
    'This week' was overwritten with today's numbers a couple of seconds
    after opening."""

    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer
        self.window = "today"


class Daemon:
    def __init__(self, db_path: str | None = None) -> None:
        os.makedirs(data_dir(), exist_ok=True)
        self.storage = Storage(db_path or default_db_path())
        self._db_lock = asyncio.Lock()
        self.nav_matcher = NavComboMatcher()
        self.attributor = NavAttributor()
        self.coalescer = EpisodeCoalescer()
        self.app_launch_attributor = AppLaunchAttributor()
        self.clients: dict[asyncio.StreamWriter, _Client] = {}
        self._client_tasks: set[asyncio.Task] = set()
        # Audited input activity lives in a bounded in-memory ring that the
        # panel can read via `get_log` while logging is enabled -- never
        # persisted, and only logged when logging_enabled is on.
        self._log_ring: list[str] = []
        self._log_enabled = self.storage.logging_enabled()
        self.evdev_source = EvdevSource(
            self.nav_matcher,
            on_typing_burst=self._on_typing_burst,
            on_mouse_activity=self.attributor.note_mouse_activity,
            on_keyboard_nav_combo=self.attributor.note_keyboard_nav_combo,
            on_app_launch_keybind_combo=self.app_launch_attributor.note_keybind_press,
            on_panel_launch_combo=self.app_launch_attributor.note_panel_press,
            on_cheatsheet_combo=self._on_cheatsheet_combo,
            logging_enabled=self._log_enabled,
            on_log=self._on_audit_log,
        )
        self.hypr_client = HyprSocketClient(
            on_nav_event=self._on_nav_event,
            on_config_reloaded=self._refresh_allowlist,
            on_openwindow_event=self._on_openwindow_event,
        )
        self._stopping = False

    # ------------------------------------------------------------------ db

    async def _db(self, fn: Callable, *args):
        """Runs one Storage call on a worker thread, serialized by a lock.

        Storage is plain synchronous sqlite3. Calling it inline from the
        event loop meant a slow flush (or a VACUUM) froze evdev reads and
        every connected panel for its whole duration. The lock keeps sqlite
        single-user, which is why Storage can safely use
        check_same_thread=False."""
        async with self._db_lock:
            return await asyncio.to_thread(fn, *args)

    # -------------------------------------------------------------- inputs

    def _on_audit_log(self, line: str) -> None:
        self._log_ring.append(line)
        if len(self._log_ring) > AUDIT_LOG_LIMIT:
            del self._log_ring[: len(self._log_ring) - AUDIT_LOG_LIMIT]

    def _on_typing_burst(self, burst) -> None:
        self.storage.queue_typing_burst(burst)

    def _on_nav_event(self) -> None:
        episode_ts = self.coalescer.add_event(time.monotonic())
        if episode_ts is None:
            return
        method = self.attributor.attribute(episode_ts)
        if method is not None:
            self.storage.queue_nav_event(method, time.time())

    def _on_openwindow_event(self) -> None:
        method = self.app_launch_attributor.on_openwindow(time.monotonic())
        if method is not None:
            self.storage.queue_app_launch_event(method, time.time())

    def _on_cheatsheet_combo(self, wall_ts: float) -> None:
        self.storage.queue_cheatsheet_invocation(wall_ts)

    async def _refresh_allowlist(self) -> None:
        try:
            allowlists = await fetch_keybind_allowlists()
        except (TimeoutError, OSError) as exc:
            log.warning("keybind allowlist refresh failed: %s", exc)
            return
        self.nav_matcher.update_allowlist(allowlists["nav"])
        self.nav_matcher.update_app_launch_allowlist(allowlists["app_launch"])
        self.nav_matcher.update_panel_launch_allowlist(allowlists["panel_launch"])
        self.nav_matcher.update_cheatsheet_allowlist(allowlists["cheatsheet"])
        log.debug("allowlists: nav=%d app=%d panel=%d cheatsheet=%d",
                  *(len(allowlists[k]) for k in
                    ("nav", "app_launch", "panel_launch", "cheatsheet")))

    # ------------------------------------------------------------- periodic

    async def _flush_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(FLUSH_INTERVAL_S)
            burst = self.evdev_source.check_idle()
            if burst is not None:
                self.storage.queue_typing_burst(burst)
            if not self.storage.has_pending():
                continue
            try:
                wrote = await self._db(self.storage.flush)
            except StorageClosed:
                return
            except Exception:
                log.exception("flush failed; dropping this batch")
                continue
            if wrote:
                await self._push_stats_update()

    async def _prune_loop(self) -> None:
        while not self._stopping:
            try:
                removed = await self._db(self.storage.prune_if_due)
            except StorageClosed:
                return
            except Exception:
                log.exception("retention sweep failed")
            else:
                if removed:
                    log.info("retention sweep removed %d raw rows", removed)
            await asyncio.sleep(PRUNE_CHECK_INTERVAL_S)

    async def _push_stats_update(self) -> None:
        if not self.clients:
            return
        # One query per distinct window in use, not one per client.
        windows = {client.window for client in self.clients.values()}
        payloads: dict[str, bytes] = {}
        for window in windows:
            try:
                state = await self._db(self.storage.get_stats, window)
            except StorageClosed:
                return
            except Exception:
                log.exception("stats push failed for window %r", window)
                continue
            state["logging_enabled"] = self._log_enabled
            state["input_health"] = self.evdev_source.health()
            payloads[window] = (dumps(event("stats_update", state)) + "\n").encode("utf-8")

        for client in list(self.clients.values()):
            payload = payloads.get(client.window)
            if payload is None:
                continue
            await self._write(client.writer, payload)

    async def _write(self, writer: asyncio.StreamWriter, payload: bytes) -> bool:
        try:
            writer.write(payload)
            await writer.drain()
            return True
        except (ConnectionError, OSError, RuntimeError):
            self.clients.pop(writer, None)
            return False

    # -------------------------------------------------------------- clients

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._client_tasks.add(task)
        client = _Client(writer)
        self.clients[writer] = client
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                message = parse_line(line.decode("utf-8", errors="replace"))
                if message is None:
                    continue
                await self._process_message(message, client)
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        except Exception:
            # A handler bug must cost one client, never the whole service.
            log.exception("client handler failed")
        finally:
            self.clients.pop(writer, None)
            if task is not None:
                self._client_tasks.discard(task)
            with contextlib.suppress(OSError, RuntimeError):
                writer.close()

    async def _process_message(self, message: dict, client: _Client) -> None:
        request_id = message.get("id")
        command = str(message.get("command") or "")
        handler = _COMMANDS.get(command)
        if handler is None:
            result = response(request_id, False, code="unknown_command",
                              message=f"Unknown command: {command!r}")
        else:
            try:
                payload = await handler(self, message, client)
                result = response(request_id, True, payload)
            except StorageClosed:
                result = response(request_id, False, code="shutting_down",
                                  message="Daemon is shutting down")
            except (TypeError, ValueError) as exc:
                result = response(request_id, False, code="invalid_value",
                                  message=str(exc))
            except Exception as exc:
                # Any other failure is reported over the wire instead of
                # tearing down the connection with a traceback.
                log.exception("command %r failed", command)
                result = response(request_id, False, code="internal_error",
                                  message=f"{type(exc).__name__}: {exc}")
        await self._write(client.writer, (dumps(result) + "\n").encode("utf-8"))

    # ------------------------------------------------------------ lifecycle

    async def run(self) -> None:
        await self._refresh_allowlist()

        sock_path = socket_path()
        os.makedirs(os.path.dirname(sock_path), mode=0o700, exist_ok=True)
        if os.path.exists(sock_path):
            os.remove(sock_path)
        server = await asyncio.start_unix_server(self._handle_client, path=sock_path)
        os.chmod(sock_path, 0o600)
        log.info("listening on %s (daemon %s, protocol %d)",
                 sock_path, DAEMON_VERSION, PROTOCOL_VERSION)

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop_event.set)

        tasks = [
            asyncio.create_task(self.evdev_source.run(), name="evdev"),
            asyncio.create_task(self.hypr_client.run(), name="hypr"),
            asyncio.create_task(self._flush_loop(), name="flush"),
            asyncio.create_task(self._prune_loop(), name="prune"),
        ]

        # Held in `tasks` so it cannot be garbage-collected mid-flight and
        # so shutdown cancels it like every other worker.
        tasks.append(asyncio.create_task(
            self._report_input_access(), name="input-check"))

        try:
            await stop_event.wait()
        finally:
            await self._shutdown(server, tasks, sock_path)

    async def _report_input_access(self) -> None:
        """Logs the input-access verdict shortly after the first rescan.

        Without membership of the `input` group most /dev/input/event* nodes
        are EACCES. The daemon then runs perfectly happily and measures
        nothing at all, which reads downstream as an empty widget rather than
        a permissions problem -- so say it plainly, once, in the journal."""
        await asyncio.sleep(2.0)
        health = self.evdev_source.health()
        if health["keyboards"] > 0:
            log.info("input: %d/%d device(s) readable, %d keyboard(s)",
                     health["readable"], health["total"], health["keyboards"])
            return
        log.warning(
            "input: no readable keyboard (%d of %d device(s) blocked). "
            "Nothing will be measured. Add yourself to the 'input' group: "
            "sudo usermod -aG input $USER, then log out and back in.",
            health["blocked"], health["total"])

    async def _shutdown(self, server, tasks, sock_path: str) -> None:
        """Ordered shutdown. The order matters: everything that could still
        touch storage has to be stopped *before* storage closes. Closing
        storage first is what produced the `sqlite3.ProgrammingError: Cannot
        operate on a closed database` crash-loop -- an in-flight `records`
        request landed after close and took the service down with it."""
        self._stopping = True

        # 1. stop accepting new connections. `server.close()` only stops the
        #    listener; it does NOT touch established connections.
        server.close()

        # 2. cancel the live client handlers. This has to happen BEFORE
        #    `wait_closed()`: on Python 3.12+ that call waits for every
        #    handler to finish, and ours sit blocked in `readline()` forever,
        #    so awaiting it first hung the whole shutdown until systemd's
        #    TimeoutStopSec fired and SIGKILLed us -- which is why storage
        #    never got its clean flush on restart.
        for task in list(self._client_tasks):
            task.cancel()
        if self._client_tasks:
            await asyncio.gather(*self._client_tasks, return_exceptions=True)
        self.clients.clear()

        # Bounded: a wedged transport must not outlive TimeoutStopSec.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(server.wait_closed(), SHUTDOWN_TIMEOUT_S)

        # 3. stop the producers.
        self.evdev_source.stop()
        self.hypr_client.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # 4. only now is it safe to drain and close storage.
        burst = self.evdev_source.flush_typing()
        if burst is not None:
            self.storage.queue_typing_burst(burst)
        with contextlib.suppress(Exception):
            self.storage.flush()
        self.storage.close()

        with contextlib.suppress(OSError):
            os.remove(sock_path)
        log.info("stopped cleanly")


# --------------------------------------------------------------- commands
#
# One coroutine per socket command. Each returns the `result` dict; errors
# are raised and turned into a protocol error response by _process_message,
# so no handler needs its own try/except.

async def _cmd_hello(daemon: Daemon, message: dict, client: _Client) -> dict:
    return {"protocol": PROTOCOL_VERSION, "daemon_version": DAEMON_VERSION}


async def _cmd_stats(daemon: Daemon, message: dict, client: _Client) -> dict:
    client.window = normalize_window(message.get("window"))
    stats = await daemon._db(daemon.storage.get_stats, client.window)
    # tack the runtime flags onto the stats so the panel can render the
    # toggle's initial state and the input-access banner on connect, without
    # extra round-trips.
    stats["logging_enabled"] = daemon._log_enabled
    stats["input_health"] = daemon.evdev_source.health()
    return stats


async def _cmd_records(daemon: Daemon, message: dict, client: _Client) -> dict:
    return await daemon._db(daemon.storage.get_records)


async def _cmd_history(daemon: Daemon, message: dict, client: _Client) -> dict:
    try:
        days = int(message.get("days", 14))
    except (TypeError, ValueError):
        days = 14
    return await daemon._db(daemon.storage.get_daily_history, days)


async def _cmd_get_log(daemon: Daemon, message: dict, client: _Client) -> dict:
    try:
        limit = int(message.get("limit", AUDIT_LOG_DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = AUDIT_LOG_DEFAULT_LIMIT
    limit = max(1, min(limit, AUDIT_LOG_LIMIT))
    ring = daemon._log_ring
    return {
        "logging_enabled": daemon._log_enabled,
        "total": len(ring),
        "lines": ring[-limit:],
    }


async def _cmd_set_logging(daemon: Daemon, message: dict, client: _Client) -> dict:
    enabled = bool(message.get("enabled", False))
    daemon._log_enabled = enabled
    await daemon._db(daemon.storage.set_logging_enabled, enabled)
    daemon.evdev_source.logging_enabled = enabled
    if not enabled:
        daemon._log_ring.clear()
    return {"logging_enabled": daemon._log_enabled}


async def _cmd_set_mouse_weight(daemon: Daemon, message: dict, client: _Client) -> dict:
    weight = await daemon._db(daemon.storage.set_mouse_weight, message.get("value"))
    await daemon._push_stats_update()  # widgets re-render the split
    return {"mouse_weight": weight}


_Handler = Callable[[Daemon, dict, _Client], Awaitable[dict]]

_COMMANDS: dict[str, _Handler] = {
    "hello": _cmd_hello,
    "stats": _cmd_stats,
    "records": _cmd_records,
    "history": _cmd_history,
    "get_log": _cmd_get_log,
    "set_logging": _cmd_set_logging,
    "set_mouse_weight": _cmd_set_mouse_weight,
}


# -------------------------------------------------------------- self-test

def self_test() -> bool:
    ok = True

    # This used to pass as long as ANY node opened -- including a power
    # button or a "System Control" node -- so a session locked out of every
    # real keyboard still got a green "self-test: OK" while measuring
    # nothing. The check is now specifically for a readable keyboard.
    try:
        all_paths = sorted(glob.glob("/dev/input/event*"))
        readable = evdev.list_devices()
        keyboards = []
        for path in readable:
            try:
                dev = evdev.InputDevice(path)
                keys = dev.capabilities().get(evdev.ecodes.EV_KEY, ())
                if all(code in keys for code in
                       (evdev.ecodes.KEY_A, evdev.ecodes.KEY_S, evdev.ecodes.KEY_SPACE)):
                    keyboards.append(dev.name)
                dev.close()
            except OSError:
                continue

        print(f"self-test: input devices: {len(readable)}/{len(all_paths)} readable, "
              f"{len(keyboards)} keyboard(s)")
        for name in keyboards:
            print(f"self-test:   keyboard: {name}")

        if not keyboards:
            blocked = len(all_paths) - len(readable)
            print(f"self-test: no readable keyboard ({blocked} device(s) blocked). "
                  f"Nothing can be measured.", file=sys.stderr)
            print(f"self-test: fix with:  sudo usermod -aG input {os.environ.get('USER', '$USER')}"
                  f"   then log out and back in.", file=sys.stderr)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=SLUG, description=__doc__)
    parser.add_argument("--self-test", action="store_true",
                        help="check the environment and exit")
    parser.add_argument("--version", action="version",
                        version=f"{SLUG} {DAEMON_VERSION}")
    parser.add_argument("--log-level", default=os.environ.get("TRACKER_LOG_LEVEL", "INFO"),
                        help="DEBUG, INFO, WARNING, ERROR (default: INFO)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr)

    if args.self_test:
        ok = self_test()
        print("self-test: OK" if ok else "self-test: FAILED")
        return 0 if ok else 1

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(Daemon().run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
