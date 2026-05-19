"""Tests for the VESIcal model-registry lookup helper.

Regression coverage for the bug where ``VESIcal_MS`` raised ``KeyError``
because ``MagmaSat`` is not registered in ``v.models.default_models`` — it
lives at ``v.models.magmasat.MagmaSat`` as a class instead.

These tests instantiate model objects but do not invoke MELTS, so they run
fine without ``thermoengine`` available at test time.
"""
from __future__ import annotations

import pytest


# Skip the whole module cleanly if VESIcal isn't installed.
pytest.importorskip("VESIcal")


def test_get_vesical_model_resolves_magmasat():
    """The previously-broken case: VESIcal_MS must resolve to a usable model."""
    from volcatenate.backends.vesical import _get_vesical_model

    model = _get_vesical_model("MagmaSat")
    assert model is not None
    assert type(model).__name__ == "MagmaSat"
    assert hasattr(model, "calculate_saturation_pressure")
    assert hasattr(model, "calculate_degassing_path")


def test_get_vesical_model_resolves_default_models():
    """The non-MagmaSat path must keep working untouched."""
    from volcatenate.backends.vesical import _get_vesical_model

    for variant in ["IaconoMarziano", "Dixon", "Liu", "ShishkinaIdealMixing"]:
        model = _get_vesical_model(variant)
        assert model is not None, f"{variant} resolved to None"
        assert hasattr(model, "calculate_saturation_pressure"), (
            f"{variant} model has no calculate_saturation_pressure"
        )
        assert hasattr(model, "calculate_degassing_path"), (
            f"{variant} model has no calculate_degassing_path"
        )


def test_get_vesical_model_raises_on_unknown_variant():
    """Unknown variants should fail at lookup time, not silently return None."""
    from volcatenate.backends.vesical import _get_vesical_model

    with pytest.raises(KeyError):
        _get_vesical_model("NotARealModel")


def test_backend_construction_does_not_invoke_model():
    """Constructing the Backend for VESIcal_MS must not require MELTS.

    The model is resolved lazily, inside ``calculate_*`` calls — not at
    Backend construction.  Otherwise importing volcatenate would crash on
    machines that have VESIcal but not MELTS/thermoengine installed.
    """
    from volcatenate.backends.vesical import Backend

    backend = Backend(variant="MagmaSat")
    assert backend.name == "VESIcal_MS"
    assert backend.is_available() is True  # VESIcal is importable per module-level skip


# ── stdout-capture context manager ─────────────────────────────────────

def test_quiet_vesical_captures_stdout_to_logger(caplog):
    """``_quiet_vesical`` must redirect stdout to logger.debug, not the terminal."""
    import logging
    from volcatenate.backends.vesical import _quiet_vesical

    with caplog.at_level(logging.DEBUG, logger="volcatenate"):
        with _quiet_vesical():
            print("noisy MELTS-style message")

    messages = [r.getMessage() for r in caplog.records]
    assert any("noisy MELTS-style message" in m for m in messages), (
        f"Expected captured stdout in logger.debug; got: {messages}"
    )


def test_quiet_vesical_captures_stderr_to_logger(caplog):
    import logging
    import sys
    from volcatenate.backends.vesical import _quiet_vesical

    with caplog.at_level(logging.DEBUG, logger="volcatenate"):
        with _quiet_vesical():
            print("error-ish text", file=sys.stderr)

    messages = [r.getMessage() for r in caplog.records]
    assert any("error-ish text" in m for m in messages)


def test_quiet_vesical_restores_streams_on_exit():
    """After the context exits, stdout/stderr must be back to normal."""
    import sys
    from volcatenate.backends.vesical import _quiet_vesical

    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with _quiet_vesical():
        pass
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr


def test_quiet_vesical_restores_streams_on_exception():
    """Streams must restore even if the wrapped code raises."""
    import sys
    from volcatenate.backends.vesical import _quiet_vesical

    original_stdout = sys.stdout
    original_stderr = sys.stderr

    class BoomError(RuntimeError):
        pass

    with pytest.raises(BoomError):
        with _quiet_vesical():
            print("about to fail")
            raise BoomError("simulated VESIcal failure")

    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr
