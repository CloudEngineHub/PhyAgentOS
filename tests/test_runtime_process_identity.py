import os
import signal

import pytest

from PhyAgentOS.skill_runtime.processes import RuntimeProcessTracker


@pytest.mark.parametrize(
    "observed_start,expected_signals", [("original", 1), ("reused", 0), (None, 0)]
)
def test_signal_requires_matching_start_time_and_pinned_pid(
    tmp_path, monkeypatch, observed_start, expected_signals
):
    tracker = RuntimeProcessTracker(tmp_path, "runtime_probe")
    read_fd, write_fd = os.pipe()
    calls = []
    monkeypatch.setattr(os, "pidfd_open", lambda pid: os.dup(read_fd), raising=False)
    monkeypatch.setattr(
        signal, "pidfd_send_signal", lambda fd, sig: calls.append(sig), raising=False
    )
    monkeypatch.setattr(tracker, "_identity", lambda pid: observed_start)
    try:
        tracker._signal(123, "original", signal.SIGTERM)
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert calls == [signal.SIGTERM] * expected_signals


def test_signal_falls_back_when_pidfd_is_unavailable(tmp_path, monkeypatch):
    tracker = RuntimeProcessTracker(tmp_path, "runtime_probe")
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    monkeypatch.delattr(signal, "pidfd_send_signal", raising=False)
    calls = []
    monkeypatch.setattr(tracker, "_identity", lambda pid: "original")
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append((pid, sig)))
    tracker._signal(123, "original", signal.SIGTERM)
    assert calls == [(123, signal.SIGTERM)]


def test_fallback_signal_still_requires_matching_start_time(tmp_path, monkeypatch):
    tracker = RuntimeProcessTracker(tmp_path, "runtime_probe")
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    monkeypatch.delattr(signal, "pidfd_send_signal", raising=False)
    calls = []
    monkeypatch.setattr(tracker, "_identity", lambda pid: "reused")
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append((pid, sig)))
    tracker._signal(123, "original", signal.SIGTERM)
    assert calls == []
