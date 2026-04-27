"""Tests for per-sample config overrides."""

import logging

from volcatenate.config import EVoConfig, MAGECConfig, resolve_sample_config


def test_evo_config_has_overrides_field():
    cfg = EVoConfig()
    assert cfg.overrides == {}


def test_magec_config_has_overrides_field():
    cfg = MAGECConfig()
    assert cfg.overrides == {}


def test_magec_p_start_overrides_removed():
    cfg = MAGECConfig()
    assert not hasattr(cfg, "p_start_overrides")


def test_overrides_field_is_independent_per_instance():
    a = EVoConfig()
    b = EVoConfig()
    a.overrides["MORB"] = {"dp_max": 25}
    assert b.overrides == {}


def test_resolve_returns_same_object_when_no_override():
    cfg = EVoConfig()
    out = resolve_sample_config(cfg, "AnySample")
    assert out is cfg


def test_resolve_applies_known_field_for_matching_sample():
    cfg = EVoConfig(overrides={"MORB": {"dp_max": 25}})
    out = resolve_sample_config(cfg, "MORB")
    assert out is not cfg            # must be a copy
    assert out.dp_max == 25
    assert cfg.dp_max == 100         # original untouched


def test_resolve_falls_through_for_unmatched_sample():
    cfg = EVoConfig(overrides={"MORB": {"dp_max": 25}})
    out = resolve_sample_config(cfg, "Fogo")
    assert out is cfg                 # no copy needed
    assert out.dp_max == 100


def test_resolve_warns_and_skips_unknown_field(caplog):
    cfg = EVoConfig(overrides={"MORB": {"dp_maxx": 25}})  # typo
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        out = resolve_sample_config(cfg, "MORB")
    assert out.dp_max == 100          # original kept
    assert "dp_maxx" in caplog.text
    assert "MORB" in caplog.text


def test_resolve_skips_attempts_to_override_overrides_field(caplog):
    cfg = EVoConfig(overrides={"MORB": {"overrides": {"X": {"y": 1}}}})
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        out = resolve_sample_config(cfg, "MORB")
    # Guard preserved the original — the inner {"X": {"y": 1}} value did not become
    # the new `overrides` dict (which would happen if the guard had been bypassed).
    assert "X" not in out.overrides
    assert out.overrides == cfg.overrides
    assert "overrides" in caplog.text


def test_resolve_applies_multiple_fields():
    cfg = EVoConfig(overrides={"Fogo": {"p_start": 5000, "gas_system": "coh"}})
    out = resolve_sample_config(cfg, "Fogo")
    assert out.p_start == 5000
    assert out.gas_system == "coh"


def test_resolve_works_for_magec_config():
    cfg = MAGECConfig(overrides={"Fogo": {"p_start_kbar": 8.0}})
    out = resolve_sample_config(cfg, "Fogo")
    assert out.p_start_kbar == 8.0
    assert cfg.p_start_kbar == 3.0


def test_resolve_does_not_alias_overrides_dict():
    """Mutating the resolved copy's overrides must not leak into the original."""
    cfg = EVoConfig(overrides={"MORB": {"dp_max": 25}})
    out = resolve_sample_config(cfg, "MORB")
    out.overrides["NewSample"] = {"dp_max": 50}
    assert "NewSample" not in cfg.overrides
