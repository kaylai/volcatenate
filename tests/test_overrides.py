"""Tests for per-sample config overrides."""

import logging
import os
from unittest.mock import patch

import pandas as pd
import pytest
import yaml

from volcatenate.composition import MeltComposition
from volcatenate.config import EVoConfig, MAGECConfig, RunConfig, resolve_sample_config


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


# ── End-to-end EVo backend tests ────────────────────────────────────


@pytest.fixture
def morb_comp():
    """Minimal MORB-like composition for backend tests."""
    return MeltComposition(
        sample="MORB",
        T_C=1200.0,
        SiO2=50.0, TiO2=1.5, Al2O3=15.0, FeOT=10.0, MnO=0.18,
        MgO=8.0, CaO=11.0, Na2O=2.5, K2O=0.2, P2O5=0.2,
        H2O=0.5, CO2=0.05, S=0.1,
        dFMQ=-1.24,
    )


def _written_env(tmp_path, sample):
    """Locate the env.yaml written by the EVo backend for `sample`.

    Asserts that exactly one of the degassing or satp env.yaml files exists,
    so a test can never silently match the wrong one.
    """
    candidates = [
        tmp_path / "raw_tool_output" / f"{sample}_evo_degas" / "env.yaml",
        tmp_path / "raw_tool_output" / f"{sample}_evo_satp" / "env.yaml",
    ]
    found = [p for p in candidates if p.exists()]
    assert len(found) == 1, f"Expected exactly 1 env.yaml for {sample}, found: {found}"
    return yaml.safe_load(found[0].read_text())


def test_evo_backend_applies_dp_max_override(tmp_path, morb_comp):
    pytest.importorskip("evo")
    from volcatenate.backends.evo import Backend

    config = RunConfig(output_dir=str(tmp_path))
    config.evo.overrides = {"MORB": {"dp_max": 25}}

    # Make run_evo a no-op that writes a stub CSV so the backend can read it.
    def fake_run_evo(chem_path, env_path, out_yaml, folder):
        os.makedirs(folder, exist_ok=True)
        stub = pd.DataFrame({
            "P": [100.0, 50.0],
            "T(K)": [1473.15, 1473.15],
            "fO2": [-8.0, -8.5],
            "F": [0.99, 0.95],
        })
        stub.to_csv(os.path.join(folder, "dgs_output_test.csv"), index=False)

    with patch("evo.run_evo", side_effect=fake_run_evo):
        Backend().calculate_degassing(morb_comp, config)

    env = _written_env(tmp_path, "MORB")
    assert env["DP_MAX"] == 25
    # global default is 100 — confirm the override won, not the default
    assert config.evo.dp_max == 100


def test_evo_backend_uses_global_default_for_unlisted_sample(tmp_path, morb_comp):
    pytest.importorskip("evo")
    from volcatenate.backends.evo import Backend

    config = RunConfig(output_dir=str(tmp_path))
    config.evo.overrides = {"OtherSample": {"dp_max": 25}}

    def fake_run_evo(chem_path, env_path, out_yaml, folder):
        os.makedirs(folder, exist_ok=True)
        pd.DataFrame({"P": [1.0], "T(K)": [1473.15], "fO2": [-8.0], "F": [1.0]}) \
            .to_csv(os.path.join(folder, "dgs_output_test.csv"), index=False)

    with patch("evo.run_evo", side_effect=fake_run_evo):
        Backend().calculate_degassing(morb_comp, config)

    env = _written_env(tmp_path, "MORB")
    assert env["DP_MAX"] == 100  # global default


def test_magec_resolve_changes_p_start_kbar():
    """resolve_sample_config applies overrides to MAGECConfig fields."""
    cfg = MAGECConfig(overrides={"Fogo": {"p_start_kbar": 8.0}})
    resolved = resolve_sample_config(cfg, "Fogo")
    assert resolved.p_start_kbar == 8.0
    # Unmatched sample falls through to default
    assert resolve_sample_config(cfg, "MORB").p_start_kbar == 3.0


def test_evo_backend_satp_applies_override(tmp_path, morb_comp):
    pytest.importorskip("evo")
    from volcatenate.backends.evo import Backend

    config = RunConfig(output_dir=str(tmp_path))
    config.evo.overrides = {"MORB": {"dp_max": 25}}

    def fake_run_evo(chem_path, env_path, out_yaml, folder):
        os.makedirs(folder, exist_ok=True)
        pd.DataFrame({
            "P": [3000.0],
            "T(K)": [1473.15],
            "fO2": [-8.0],
            "F": [1.0],
        }).to_csv(os.path.join(folder, "dgs_output_satp.csv"), index=False)

    with patch("evo.run_evo", side_effect=fake_run_evo):
        Backend().calculate_saturation_pressure(morb_comp, config)

    env = _written_env(tmp_path, "MORB")
    assert env["DP_MAX"] == 25
