"""Tests for per-sample config overrides."""

import logging
import os
from unittest.mock import patch

import pandas as pd
import pytest
import yaml

import volcatenate
from volcatenate.composition import MeltComposition
from volcatenate.config import (
    EVoConfig,
    MAGECConfig,
    RunConfig,
    default_config_path,
    load_config,
    resolve_sample_config,
    save_config,
)


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


def test_load_config_folds_deprecated_p_start_overrides(tmp_path, caplog):
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(
        "magec:\n"
        "  p_start_overrides: {Fogo: 8.0, Fuego: 5.0}\n"
    )
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        cfg = load_config(str(yaml_path))
    assert cfg.magec.overrides == {
        "Fogo": {"p_start_kbar": 8.0},
        "Fuego": {"p_start_kbar": 5.0},
    }
    assert "p_start_overrides" in caplog.text
    assert "deprecated" in caplog.text.lower()


def test_load_config_new_overrides_win_on_conflict(tmp_path, caplog):
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(
        "magec:\n"
        "  p_start_overrides: {Fogo: 8.0}\n"
        "  overrides: {Fogo: {p_start_kbar: 4.0, n_steps: 50}}\n"
    )
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        cfg = load_config(str(yaml_path))
    # New shape wins — does NOT get clobbered by the deprecated value.
    assert cfg.magec.overrides["Fogo"]["p_start_kbar"] == 4.0
    assert cfg.magec.overrides["Fogo"]["n_steps"] == 50


def test_load_config_does_not_double_log_when_no_deprecation(tmp_path, caplog):
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(
        "magec:\n"
        "  overrides: {Fogo: {p_start_kbar: 8.0}}\n"
    )
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        cfg = load_config(str(yaml_path))
    assert cfg.magec.overrides == {"Fogo": {"p_start_kbar": 8.0}}
    assert "deprecated" not in caplog.text.lower()


def test_run_comparison_raises_on_unknown_evo_override_sample(tmp_path, morb_comp):
    config = RunConfig(output_dir=str(tmp_path))
    config.evo.overrides = {"NotASample": {"dp_max": 25}}
    with pytest.raises(ValueError, match="NotASample"):
        volcatenate.run_comparison(
            degassing_compositions=[morb_comp],
            models=["EVo"],
            config=config,
        )


def test_run_comparison_raises_on_unknown_magec_override_sample(tmp_path, morb_comp):
    config = RunConfig(output_dir=str(tmp_path))
    config.magec.overrides = {"NotASample": {"p_start_kbar": 8.0}}
    with pytest.raises(ValueError, match="NotASample"):
        volcatenate.run_comparison(
            degassing_compositions=[morb_comp],
            models=["MAGEC"],
            config=config,
        )


def test_run_comparison_error_names_the_backend(tmp_path, morb_comp):
    config = RunConfig(output_dir=str(tmp_path))
    config.evo.overrides = {"Bogus": {"dp_max": 25}}
    with pytest.raises(ValueError) as excinfo:
        volcatenate.run_comparison(
            degassing_compositions=[morb_comp],
            models=["EVo"],
            config=config,
        )
    assert "evo" in str(excinfo.value).lower()


def test_validate_override_sample_names_accepts_valid():
    """Direct unit test of the validation helper — accepts a valid sample."""
    from volcatenate.core import _validate_override_sample_names
    config = RunConfig()
    config.evo.overrides = {"MORB": {"dp_max": 25}}
    config.magec.overrides = {"MORB": {"p_start_kbar": 8.0}}
    # Must not raise
    _validate_override_sample_names(config, ["MORB"])


def test_validate_override_sample_names_raises_on_unknown():
    """Direct unit test — raises when a sample is not in the known list."""
    from volcatenate.core import _validate_override_sample_names
    config = RunConfig()
    config.evo.overrides = {"NotASample": {"dp_max": 25}}
    with pytest.raises(ValueError, match="NotASample"):
        _validate_override_sample_names(config, ["MORB"])


def test_overrides_round_trip(tmp_path):
    """save_config + load_config preserves nested overrides on both backends."""
    cfg = RunConfig()
    cfg.evo.overrides = {"MORB": {"dp_max": 25}}
    cfg.magec.overrides = {"Fogo": {"p_start_kbar": 8.0}}

    out = tmp_path / "round_trip.yaml"
    save_config(cfg, str(out))
    reloaded = load_config(str(out))

    assert reloaded.evo.overrides == {"MORB": {"dp_max": 25}}
    assert reloaded.magec.overrides == {"Fogo": {"p_start_kbar": 8.0}}


def test_default_yaml_loads_clean(caplog):
    """Bundled default_config.yaml loads with empty overrides and no deprecation warning."""
    with caplog.at_level(logging.WARNING, logger="volcatenate"):
        cfg = load_config(default_config_path())
    assert cfg.evo.overrides == {}
    assert cfg.magec.overrides == {}
    assert cfg.volfe.overrides == {}
    assert cfg.vesical.overrides == {}
    assert cfg.sulfurx.overrides == {}
    assert "deprecated" not in caplog.text.lower()


# ── VolFe overrides ─────────────────────────────────────────────────


def test_volfe_config_has_overrides_field():
    from volcatenate.config import VolFeConfig
    cfg = VolFeConfig()
    assert cfg.overrides == {}


def test_volfe_overrides_field_is_independent_per_instance():
    from volcatenate.config import VolFeConfig
    a = VolFeConfig()
    b = VolFeConfig()
    a.overrides["MORB"] = {"gassing_style": "open"}
    assert b.overrides == {}


def test_resolve_works_for_volfe_config():
    from volcatenate.config import VolFeConfig
    cfg = VolFeConfig(overrides={"Fogo": {"gassing_style": "open"}})
    out = resolve_sample_config(cfg, "Fogo")
    assert out.gassing_style == "open"
    assert cfg.gassing_style == "closed"


def test_volfe_backend_applies_override_to_models_df(morb_comp):
    pytest.importorskip("VolFe")
    from volcatenate.backends.volfe import Backend, _build_models_df

    config = RunConfig()
    config.volfe.overrides = {"MORB": {"gassing_style": "open"}}

    captured: dict = {}

    def fake_build_models_df(cfg):
        captured["gassing_style"] = cfg.gassing_style
        return _build_models_df(cfg)

    def fake_calc_gassing(setup_df, models, suppress_warnings):
        return pd.DataFrame({"P_bar": [1.0], "wt_g_O": [0.0]})

    with patch("volcatenate.backends.volfe._build_models_df",
               side_effect=fake_build_models_df), \
         patch("VolFe.calc_gassing", side_effect=fake_calc_gassing):
        try:
            Backend().calculate_degassing(morb_comp, config)
        except Exception:
            pass  # converter may fail on the stub frame — we only care about cfg

    assert captured["gassing_style"] == "open"
    assert config.volfe.gassing_style == "closed"


# ── VESIcal overrides ───────────────────────────────────────────────


def test_vesical_config_has_overrides_field():
    from volcatenate.config import VESIcalConfig
    cfg = VESIcalConfig()
    assert cfg.overrides == {}


def test_vesical_overrides_field_is_independent_per_instance():
    from volcatenate.config import VESIcalConfig
    a = VESIcalConfig()
    b = VESIcalConfig()
    a.overrides["MORB"] = {"steps": 50}
    assert b.overrides == {}


def test_resolve_works_for_vesical_config():
    from volcatenate.config import VESIcalConfig
    cfg = VESIcalConfig(overrides={"Fogo": {"steps": 50, "final_pressure": 10.0}})
    out = resolve_sample_config(cfg, "Fogo")
    assert out.steps == 50
    assert out.final_pressure == 10.0
    assert cfg.steps == 101
    assert cfg.final_pressure == 1.0


def test_vesical_backend_applies_steps_override(morb_comp):
    pytest.importorskip("VESIcal")
    from volcatenate.backends.vesical import Backend

    config = RunConfig()
    config.vesical.overrides = {"MORB": {"steps": 7}}

    captured: dict = {}

    class _FakeModel:
        def calculate_degassing_path(self, sample, temperature, pressure,
                                     fractionate_vapor, final_pressure, steps):
            captured["steps"] = steps
            return pd.DataFrame({"Pressure_bars": [100.0], "H2O_liq": [0.0],
                                 "CO2_liq": [0.0], "XH2O_fl": [0.5], "XCO2_fl": [0.5]})

    with patch.dict("VESIcal.models.default_models", {"IaconoMarziano": _FakeModel()}):
        try:
            Backend(variant="IaconoMarziano").calculate_degassing(morb_comp, config)
        except Exception:
            pass  # converter may complain about minimal stub — we only check cfg flow

    assert captured["steps"] == 7
    assert config.vesical.steps == 101


# ── SulfurX overrides ───────────────────────────────────────────────


def test_sulfurx_config_has_overrides_field():
    from volcatenate.config import SulfurXConfig
    cfg = SulfurXConfig()
    assert cfg.overrides == {}


def test_sulfurx_overrides_field_is_independent_per_instance():
    from volcatenate.config import SulfurXConfig
    a = SulfurXConfig()
    b = SulfurXConfig()
    a.overrides["MORB"] = {"n_steps": 100}
    assert b.overrides == {}


def test_resolve_works_for_sulfurx_config():
    from volcatenate.config import SulfurXConfig
    cfg = SulfurXConfig(overrides={"Fogo": {"n_steps": 100, "sigma": 0.001}})
    out = resolve_sample_config(cfg, "Fogo")
    assert out.n_steps == 100
    assert out.sigma == 0.001
    assert cfg.n_steps == 600
    assert cfg.sigma == 0.005


def test_sulfurx_backend_passes_resolved_cfg_to_run_degassing(morb_comp):
    from volcatenate.backends.sulfurx import Backend

    config = RunConfig()
    config.sulfurx.path = "/nonexistent"  # we'll patch _ensure_on_path
    config.sulfurx.overrides = {"MORB": {"n_steps": 42}}

    captured: dict = {}

    def fake_run_degassing(comp, cfg):
        captured["n_steps"] = cfg.n_steps
        return pd.DataFrame()

    with patch.object(Backend, "_ensure_on_path", lambda self, config: None), \
         patch("volcatenate.backends.sulfurx._run_degassing",
               side_effect=fake_run_degassing):
        try:
            Backend().calculate_degassing(morb_comp, config)
        except Exception:
            pass  # converter may fail on the empty frame; we only check cfg

    assert captured["n_steps"] == 42
    assert config.sulfurx.n_steps == 600


def test_yaml_round_trip_preserves_all_backend_overrides(tmp_path):
    """save_config + load_config must preserve overrides on every backend."""
    from volcatenate.config import save_config, load_config

    cfg = RunConfig()
    cfg.evo.overrides = {"MORB": {"dp_max": 25}}
    cfg.magec.overrides = {"Fogo": {"p_start_kbar": 8.0}}
    cfg.volfe.overrides = {"Sample1": {"gassing_style": "open"}}
    cfg.vesical.overrides = {"Sample2": {"steps": 50}}
    cfg.sulfurx.overrides = {"Sample3": {"n_steps": 100}}

    yaml_path = tmp_path / "test.yaml"
    save_config(cfg, str(yaml_path))
    loaded = load_config(str(yaml_path))

    assert loaded.evo.overrides == {"MORB": {"dp_max": 25}}
    assert loaded.magec.overrides == {"Fogo": {"p_start_kbar": 8.0}}
    assert loaded.volfe.overrides == {"Sample1": {"gassing_style": "open"}}
    assert loaded.vesical.overrides == {"Sample2": {"steps": 50}}
    assert loaded.sulfurx.overrides == {"Sample3": {"n_steps": 100}}
