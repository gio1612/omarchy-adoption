import os

import pytest

from hypr_ipc import _newest_live_signature, socket2_path


def _make_sig(base, name, has_socket=True):
    sig_dir = os.path.join(base, "hypr", name)
    os.makedirs(sig_dir, exist_ok=True)
    if has_socket:
        path = os.path.join(sig_dir, ".socket2.sock")
        open(path, "a").close()
    return sig_dir


def test_newest_live_signature_prefers_most_recent_socket(tmp_path):
    old = _make_sig(tmp_path, "old_sig")
    os.utime(old, (1000, 1000))
    new = _make_sig(tmp_path, "new_sig")
    os.utime(new, (2000, 2000))
    assert _newest_live_signature(str(tmp_path)) == "new_sig"


def test_newest_live_signature_skips_dirs_without_socket(tmp_path):
    _make_sig(tmp_path, "empty_sig", has_socket=False)
    winner = _make_sig(tmp_path, "live_sig")
    os.utime(winner, (5000, 5000))
    assert _newest_live_signature(str(tmp_path)) == "live_sig"


def test_newest_live_signature_returns_none_when_no_candidates(tmp_path):
    assert _newest_live_signature(str(tmp_path)) is None


def test_newest_live_signature_handles_missing_base(tmp_path):
    assert _newest_live_signature(str(tmp_path / "no-such-dir")) is None


def test_socket2_path_uses_provided_signature(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    _make_sig(tmp_path, "direct")
    result = socket2_path(runtime_dir=str(tmp_path), signature="direct")
    assert result == os.path.join(str(tmp_path), "hypr", "direct", ".socket2.sock")


def test_socket2_path_falls_back_to_discovery(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    _make_sig(tmp_path, "discovered")
    result = socket2_path(runtime_dir=str(tmp_path), signature=None)
    assert result.endswith("discovered/.socket2.sock")


def test_socket2_path_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert socket2_path(runtime_dir=str(tmp_path), signature=None) is None


def test_socket2_path_returns_none_for_missing_sig(tmp_path, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    assert socket2_path(runtime_dir=str(tmp_path), signature="ghost") is None
