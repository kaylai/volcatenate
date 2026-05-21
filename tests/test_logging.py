from __future__ import annotations

import logging
import os

import pytest


def test_quiet_evo_flushes_output_on_exception():
    """Captured EVo stdout must reach logger.debug even when the wrapped code raises."""
    from volcatenate.backends.evo import _quiet_evo
    from volcatenate.log import logger

    records = []

    class CapHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = CapHandler()
    handler.setLevel(logging.DEBUG)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        with pytest.raises(RuntimeError):
            with _quiet_evo():
                print("evo_stdout_line")
                raise RuntimeError("EVo failed")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert any("evo_stdout_line" in r for r in records), (
        "stdout captured before exception was not flushed to logger; "
        "log-flush loop is still outside the finally block"
    )


def test_quiet_volfe_flushes_output_on_exception():
    """Captured VolFe stdout must reach logger.debug even when the wrapped code raises."""
    from volcatenate.backends.volfe import _quiet_volfe
    from volcatenate.log import logger

    records = []

    class CapHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = CapHandler()
    handler.setLevel(logging.DEBUG)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        with pytest.raises(RuntimeError):
            with _quiet_volfe():
                print("volfe_stdout_line")
                raise RuntimeError("VolFe failed")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert any("volfe_stdout_line" in r for r in records), (
        "stdout captured before exception was not flushed to logger; "
        "log-flush loop is still outside the finally block"
    )


def test_quiet_volfe_restores_cwd_on_exception(tmp_path):
    """CWD must be restored even if work_dir chdir succeeds but body raises."""
    from volcatenate.backends.volfe import _quiet_volfe

    original_cwd = os.getcwd()
    work_dir = str(tmp_path / "volfe_work")

    with pytest.raises(RuntimeError):
        with _quiet_volfe(work_dir=work_dir):
            raise RuntimeError("failed mid-run")

    assert os.getcwd() == original_cwd, (
        "CWD was not restored after exception in _quiet_volfe; "
        "os.chdir is still outside the try block"
    )


def test_quiet_volfe_restores_cwd_on_success(tmp_path):
    """CWD must be restored on normal exit too."""
    from volcatenate.backends.volfe import _quiet_volfe

    original_cwd = os.getcwd()
    work_dir = str(tmp_path / "volfe_work2")

    with _quiet_volfe(work_dir=work_dir):
        pass

    assert os.getcwd() == original_cwd


# ── verbose_level: tunable terminal log threshold ─────────────────────

def test_verbose_level_filters_terminal_handler(capsys):
    """setup_logging(verbose=True, level='WARNING') must suppress INFO on stdout."""
    from volcatenate.log import logger, setup_logging

    try:
        setup_logging(verbose=True, log_file="", level="WARNING")
        logger.info("info-should-be-hidden")
        logger.warning("warning-should-be-shown")
        out = capsys.readouterr().out
        assert "info-should-be-hidden" not in out
        assert "warning-should-be-shown" in out
    finally:
        setup_logging(verbose=False, log_file="")  # restore silent state


def test_verbose_level_default_is_info(capsys):
    """When level is unspecified, INFO messages still appear (backwards compat)."""
    from volcatenate.log import logger, setup_logging

    try:
        setup_logging(verbose=True, log_file="")
        logger.info("info-default-visible")
        out = capsys.readouterr().out
        assert "info-default-visible" in out
    finally:
        setup_logging(verbose=False, log_file="")


def test_verbose_level_rejects_unknown_value():
    """Misconfigured YAML should fail loudly, not silently drop messages."""
    from volcatenate.log import setup_logging

    with pytest.raises(ValueError, match="verbose_level"):
        setup_logging(verbose=True, log_file="", level="SHOUT")


def test_verbose_level_roundtrips_through_yaml(tmp_path):
    """RunConfig.verbose_level survives save_config → load_config."""
    from volcatenate.config import RunConfig, load_config, save_config

    cfg = RunConfig(verbose=True, verbose_level="WARNING")
    path = tmp_path / "cfg.yaml"
    save_config(cfg, str(path))

    loaded = load_config(str(path))
    assert loaded.verbose is True
    assert loaded.verbose_level == "WARNING"


def test_log_file_always_debug_regardless_of_verbose_level(tmp_path):
    """Terminal level must not affect the file handler — runlog stays comprehensive."""
    from volcatenate.log import logger, setup_logging

    log_file = tmp_path / "run.log"
    try:
        setup_logging(verbose=True, log_file=str(log_file), level="ERROR")
        logger.debug("debug-must-be-in-file")
        logger.info("info-must-be-in-file")
        # Flush all handlers so the file is readable
        for h in logger.handlers:
            h.flush()
        text = log_file.read_text()
        assert "debug-must-be-in-file" in text
        assert "info-must-be-in-file" in text
    finally:
        setup_logging(verbose=False, log_file="")
        