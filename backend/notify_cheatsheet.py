#!/usr/bin/env python3
"""Notifies the tracker daemon that SUPER+K (the keybindings cheatsheet) was
invoked. Best-effort and silent: cheatsheet-wrapper.sh calls this, backgrounded
and disowned, then immediately execs the real cheatsheet regardless of whether
this succeeds -- tracking must never delay or break the cheatsheet opening.
"""

from __future__ import annotations

import socket
import sys
import time

from protocol import dumps

TIMEOUT_S = 0.2


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    sock_path = sys.argv[1]
    payload = {"v": 1, "type": "event", "name": "cheatsheet_invoked", "ts": time.time()}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT_S)
            sock.connect(sock_path)
            sock.sendall((dumps(payload) + "\n").encode("utf-8"))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
