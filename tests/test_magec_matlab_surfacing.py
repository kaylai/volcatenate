"""MAGEC's MATLAB wrapper prints `MAGEC: FAILED - <msg>` to stdout then exits.
Historically that line was logged only at DEBUG and the wrapper exited 0, so a
solver failure (e.g. an unusable redox input) was invisible at the default log
level. These tests cover the surfacing helper that lifts such failures to
WARNING.
"""

from __future__ import annotations

import logging

from volcatenate.backends.magec import _surface_matlab_result


def test_failure_line_surfaced_at_warning(caplog):
    stdout = "MAGEC: FAILED - Output argument 'logfO2' not assigned in fun_redox_opt_P\n"
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        _surface_matlab_result(stdout, returncode=1)
    assert "MAGEC: FAILED" in caplog.text or "fun_redox_opt_P" in caplog.text
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "a MAGEC failure must produce a WARNING"


def test_success_emits_no_warning(caplog):
    with caplog.at_level(logging.DEBUG, logger="volcatenate"):
        _surface_matlab_result("MAGEC: OK\n", returncode=0)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_returns_failure_lines():
    failed = _surface_matlab_result("noise\nMAGEC: FAILED - boom\nmore\n", returncode=1)
    assert any("boom" in line for line in failed)
