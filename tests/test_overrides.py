"""Tests for per-sample config overrides."""

from volcatenate.config import EVoConfig, MAGECConfig


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
