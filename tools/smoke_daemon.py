#!/usr/bin/env python3
"""End-to-end smoke test: boot the real daemon, talk to its real Unix socket,
then shut it down and assert it exited cleanly.

The unit tests exercise `_process_message` directly. This exercises the parts
they cannot: `asyncio.start_unix_server`, the socket path layout, the
newline-delimited framing over an actual connection, and -- most importantly --
the ordered shutdown. A request racing `storage.close()` used to raise
`sqlite3.ProgrammingError: Cannot operate on a closed database`, escape the
client handler, and crash-loop the systemd service. That race is asserted
against here.

Runs anywhere Python and evdev import: no Hyprland, no input devices, no
systemd. Used by CI's install-smoke job and runnable by hand:

    python tools/smoke_daemon.py
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

failures: list[str] = []


def check(condition: bool, description: str) -> None:
    if condition:
        print(f"  ok   {description}")
    else:
        print(f"  FAIL {description}")
        failures.append(description)


class Client:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self._id = 0

    async def request(self, command: str, **fields):
        self._id += 1
        payload = {"v": 1, "id": self._id, "command": command}
        payload.update(fields)
        self.writer.write((json.dumps(payload) + "\n").encode())
        await self.writer.drain()
        # Skip any pushed events that arrive before our answer.
        while True:
            line = await asyncio.wait_for(self.reader.readline(), 10)
            if not line:
                return None
            message = json.loads(line)
            if message.get("type") == "response" and message.get("id") == self._id:
                return message

    async def close(self):
        self.writer.close()
        with contextlib.suppress(ConnectionError, OSError):
            await self.writer.wait_closed()


async def main() -> int:
    import daemon as mod

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_DATA_HOME"] = os.path.join(tmp, "data")
        os.environ["XDG_RUNTIME_DIR"] = os.path.join(tmp, "run")
        os.makedirs(os.environ["XDG_RUNTIME_DIR"], mode=0o700, exist_ok=True)

        tracker = mod.Daemon()
        run_task = asyncio.create_task(tracker.run())

        sock = mod.socket_path()
        for _ in range(100):
            if os.path.exists(sock):
                break
            await asyncio.sleep(0.05)
        check(os.path.exists(sock), f"daemon created its socket at {sock}")

        client = Client(*await asyncio.open_unix_connection(sock))

        print("protocol:")
        reply = await client.request("hello")
        check(reply is not None and reply["ok"] is True, "hello succeeds")
        check(reply["result"]["daemon_version"] == mod.DAEMON_VERSION,
              f"hello reports version {mod.DAEMON_VERSION}")

        for window in ("today", "week", "month", "all"):
            reply = await client.request("stats", window=window)
            check(reply["ok"] is True and reply["result"]["window"] == window,
                  f"stats window={window}")

        reply = await client.request("records")
        check(reply["ok"] is True, "records succeeds on an empty database")

        reply = await client.request("history", days=14)
        check(reply["ok"] is True and len(reply["result"]["series"]) == 14,
              "history returns a full 14-day series")

        reply = await client.request("get_log")
        check(reply["ok"] is True and "lines" in reply["result"], "get_log succeeds")

        reply = await client.request("set_mouse_weight", value=2.5)
        check(reply["ok"] is True and reply["result"]["mouse_weight"] == 2.5,
              "set_mouse_weight persists a value")

        reply = await client.request("set_mouse_weight", value="not-a-number")
        check(reply["ok"] is False and reply["error"]["code"] == "invalid_value",
              "a bad value is a protocol error, not a disconnect")

        reply = await client.request("nonsense")
        check(reply["ok"] is False and reply["error"]["code"] == "unknown_command",
              "unknown command is a protocol error")

        # The connection must survive every error above.
        reply = await client.request("hello")
        check(reply is not None and reply["ok"] is True,
              "connection still alive after error responses")

        print("shutdown:")
        # SIGTERM with a client still connected -- exactly the shape systemd
        # produces on `systemctl --user restart`, and exactly the shape that
        # used to crash the service.
        os.kill(os.getpid(), signal.SIGTERM)
        try:
            await asyncio.wait_for(run_task, 15)
            clean = True
        except TimeoutError:
            clean = False
            run_task.cancel()
        except Exception as exc:  # noqa: BLE001
            clean = False
            print(f"       shutdown raised {type(exc).__name__}: {exc}")

        check(clean, "SIGTERM with a connected client shuts down cleanly")
        check(not os.path.exists(sock), "socket file was removed on shutdown")
        check(tracker.storage.closed, "storage was closed")

        await client.close()

        # Storage must survive a second close, and answer late calls with
        # StorageClosed rather than sqlite3.ProgrammingError.
        from storage import StorageClosed
        tracker.storage.close()
        try:
            tracker.storage.get_records()
            check(False, "late request after close raises StorageClosed")
        except StorageClosed:
            check(True, "late request after close raises StorageClosed")
        except Exception as exc:  # noqa: BLE001
            check(False, f"late request raised {type(exc).__name__} instead of StorageClosed")

    if failures:
        print(f"\nsmoke: FAILED ({len(failures)} check(s))")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("\nsmoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
