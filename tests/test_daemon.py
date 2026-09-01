"""Daemon socket-protocol and lifecycle tests.

Covers the two failures that made the service unusable in practice:
a request landing after storage closed took the whole daemon down, and
pushed stats always carried "today" no matter what window a client asked
for. Both are regression-tested here.
"""

import asyncio
import json

import daemon as mod
import pytest
from protocol import parse_line


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    return mod.Daemon(db_path=str(tmp_path / "tracker.db"))


class FakeWriter:
    """Minimal asyncio.StreamWriter stand-in that records written lines."""

    def __init__(self):
        self.lines = []
        self.closed = False

    def write(self, payload):
        for chunk in payload.decode("utf-8").splitlines():
            if chunk:
                self.lines.append(json.loads(chunk))

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    def messages(self, kind):
        return [m for m in self.lines if m.get("type") == kind]


async def _request(tracker, writer, command, **fields):
    client = tracker.clients.get(writer)
    if client is None:
        client = mod._Client(writer)
        tracker.clients[writer] = client
    message = {"v": 1, "id": len(writer.lines) + 1, "command": command}
    message.update(fields)
    await tracker._process_message(message, client)
    return writer.lines[-1]


# --------------------------------------------------------------- protocol

def test_hello_reports_version_and_protocol(tracker):
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "hello"))
    assert reply["ok"] is True
    assert reply["result"]["daemon_version"] == mod.DAEMON_VERSION
    assert reply["result"]["protocol"] == 1


def test_unknown_command_is_an_error_not_a_crash(tracker):
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "nope"))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "unknown_command"


def test_stats_accepts_every_window_and_falls_back_to_today(tracker):
    writer = FakeWriter()

    async def scenario():
        for window in ("today", "week", "month", "all"):
            reply = await _request(tracker, writer, "stats", window=window)
            assert reply["result"]["window"] == window
        reply = await _request(tracker, writer, "stats", window="banana")
        assert reply["result"]["window"] == "today"

    asyncio.run(scenario())


def test_malformed_line_is_ignored(tracker):
    assert parse_line("not json") is None
    assert parse_line("") is None
    assert parse_line("[1,2,3]") is None


def test_set_mouse_weight_rejects_non_numeric_without_dying(tracker):
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "set_mouse_weight", value="abc"))
    assert reply["ok"] is False
    assert reply["error"]["code"] == "invalid_value"


def test_set_mouse_weight_clamps(tracker):
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "set_mouse_weight", value=99))
    assert reply["result"]["mouse_weight"] == 10.0


# ----------------------------------------------------- audit log windowing

def test_get_log_returns_only_the_newest_slice(tracker):
    tracker._log_enabled = True
    for i in range(400):
        tracker._on_audit_log(f"line-{i}")
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "get_log"))
    result = reply["result"]
    assert result["total"] == 400
    assert len(result["lines"]) == mod.AUDIT_LOG_DEFAULT_LIMIT
    assert result["lines"][-1] == "line-399"


def test_get_log_limit_is_bounded(tracker):
    for i in range(500):
        tracker._on_audit_log(f"line-{i}")
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "get_log", limit=10_000))
    assert len(reply["result"]["lines"]) == mod.AUDIT_LOG_LIMIT


def test_audit_ring_stays_bounded(tracker):
    for i in range(mod.AUDIT_LOG_LIMIT * 3):
        tracker._on_audit_log(f"line-{i}")
    assert len(tracker._log_ring) == mod.AUDIT_LOG_LIMIT


def test_disabling_logging_clears_the_ring(tracker):
    tracker._on_audit_log("something")
    writer = FakeWriter()
    asyncio.run(_request(tracker, writer, "set_logging", enabled=False))
    assert tracker._log_ring == []


# ------------------------------------------------------- pushed stats window

def test_push_uses_each_clients_own_window(tracker):
    """Regression: every push carried 'today', so a panel showing 'This week'
    was silently overwritten with today's numbers seconds after opening."""
    today_writer, week_writer = FakeWriter(), FakeWriter()

    async def scenario():
        await _request(tracker, today_writer, "stats", window="today")
        await _request(tracker, week_writer, "stats", window="week")
        await tracker._push_stats_update()

    asyncio.run(scenario())

    pushed_today = today_writer.messages("event")
    pushed_week = week_writer.messages("event")
    assert pushed_today and pushed_today[-1]["state"]["window"] == "today"
    assert pushed_week and pushed_week[-1]["state"]["window"] == "week"


def test_push_with_no_clients_is_a_noop(tracker):
    asyncio.run(tracker._push_stats_update())  # must not raise


# -------------------------------------------------- shutdown-race regression

def test_request_after_storage_close_returns_an_error(tracker):
    """Regression for `sqlite3.ProgrammingError: Cannot operate on a closed
    database`, which escaped the client handler and crash-looped the
    service on every shutdown that raced an in-flight request."""
    tracker.storage.close()
    writer = FakeWriter()
    for command in ("stats", "records", "history"):
        reply = asyncio.run(_request(tracker, writer, command))
        assert reply["ok"] is False
        assert reply["error"]["code"] == "shutting_down"


def test_storage_close_is_idempotent(tracker):
    tracker.storage.close()
    tracker.storage.close()
    assert tracker.storage.closed is True


def test_normalize_window():
    assert mod.normalize_window(None) == "today"
    assert mod.normalize_window("WEEK") == "week"
    assert mod.normalize_window(123) == "today"


# ------------------------------------------------------------- input access

def test_stats_reports_input_health(tracker):
    """Without the `input` group most /dev/input/event* nodes are EACCES and
    the daemon measures nothing while looking perfectly healthy. The counts
    ride along with every stats reply so the widget can say so."""
    writer = FakeWriter()
    reply = asyncio.run(_request(tracker, writer, "stats"))
    health = reply["result"]["input_health"]
    assert set(health) == {"readable", "blocked", "total", "keyboards"}
    assert all(isinstance(v, int) for v in health.values())


def test_pushed_stats_carry_input_health(tracker):
    writer = FakeWriter()

    async def scenario():
        await _request(tracker, writer, "stats", window="today")
        await tracker._push_stats_update()

    asyncio.run(scenario())
    pushed = writer.messages("event")[-1]
    assert "input_health" in pushed["state"]
