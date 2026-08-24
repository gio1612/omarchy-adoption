from protocol import PROTOCOL_VERSION, dumps, event, parse_line, response


def test_response_ok_shape():
    payload = response(7, True, {"foo": "bar"})
    assert payload == {
        "type": "response", "v": PROTOCOL_VERSION, "id": 7,
        "ok": True, "result": {"foo": "bar"},
    }


def test_response_error_shape():
    payload = response(7, False, code="bad", message="nope")
    assert payload["ok"] is False
    assert payload["error"] == {"code": "bad", "message": "nope"}


def test_event_shape():
    payload = event("stats_update", {"a": 1})
    assert payload == {
        "type": "event", "v": PROTOCOL_VERSION,
        "event": "stats_update", "state": {"a": 1},
    }


def test_parse_line_roundtrip():
    payload = response(1, True, {"x": 1})
    assert parse_line(dumps(payload)) == payload


def test_parse_line_invalid_input():
    assert parse_line("not json") is None
    assert parse_line("") is None
    assert parse_line("   ") is None
    assert parse_line("[1,2,3]") is None
