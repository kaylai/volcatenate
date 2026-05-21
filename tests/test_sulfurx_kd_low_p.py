"""Unit + integration tests for the SulfurX low-pressure kd override knobs.

Covers:
  - YAML round-trip of ``kd_low_p_increment`` / ``kd_low_p_threshold_mpa``.
  - ``_patch_kd_low_p`` context manager assigns SulfurX's ``INC`` / ``BAR``
    module globals on enter and restores the originals on exit (including
    when the wrapped block raises).
  - Runtime warning fires only when ``kd_low_p_threshold_mpa >= 20``.
"""
from __future__ import annotations

import logging
import sys
import types

import pytest

from volcatenate.config import (
    RunConfig,
    SulfurXConfig,
    load_config,
    save_config,
)


# ── YAML round-trip ─────────────────────────────────────────────────────────

class TestKdLowPYamlRoundTrip:
    def test_defaults_survive_round_trip(self, tmp_path):
        """SulfurXConfig defaults should round-trip cleanly through YAML."""
        cfg = RunConfig()
        out = tmp_path / "default.yaml"
        save_config(cfg, str(out))
        reloaded = load_config(str(out))

        assert reloaded.sulfurx.kd_low_p_increment == 20.0
        assert reloaded.sulfurx.kd_low_p_threshold_mpa == 0.0

    def test_explicit_values_survive_round_trip(self, tmp_path):
        """Non-default values written by the user must reload identically."""
        cfg = RunConfig()
        cfg.sulfurx.kd_low_p_increment = 35.5
        cfg.sulfurx.kd_low_p_threshold_mpa = 5.0

        out = tmp_path / "explicit.yaml"
        save_config(cfg, str(out))
        reloaded = load_config(str(out))

        assert reloaded.sulfurx.kd_low_p_increment == 35.5
        assert reloaded.sulfurx.kd_low_p_threshold_mpa == 5.0

    def test_override_round_trip(self, tmp_path):
        """Per-sample overrides on the new fields must round-trip."""
        cfg = RunConfig()
        cfg.sulfurx.overrides = {
            "Fuego": {"kd_low_p_threshold_mpa": 10.0, "kd_low_p_increment": 25.0},
        }
        out = tmp_path / "override.yaml"
        save_config(cfg, str(out))
        reloaded = load_config(str(out))

        assert reloaded.sulfurx.overrides == {
            "Fuego": {"kd_low_p_threshold_mpa": 10.0, "kd_low_p_increment": 25.0},
        }


# ── _patch_kd_low_p set + restore ───────────────────────────────────────────

@pytest.fixture
def fake_degassingrun():
    """Inject a fake ``degassingrun`` module with sentinel INC / BAR values.

    The context manager only needs the module to expose ``INC`` and ``BAR``;
    we don't need the real SulfurX install on path for this test.
    """
    fake = types.ModuleType("degassingrun")
    fake.INC = 999.0
    fake.BAR = 999.0
    sys.modules["degassingrun"] = fake
    try:
        yield fake
    finally:
        sys.modules.pop("degassingrun", None)


class TestPatchKdLowP:
    def test_sets_and_restores(self, fake_degassingrun):
        from volcatenate.backends.sulfurx import _patch_kd_low_p

        with _patch_kd_low_p(increment=42.0, threshold_mpa=7.5):
            assert fake_degassingrun.INC == 42.0
            assert fake_degassingrun.BAR == 7.5

        assert fake_degassingrun.INC == 999.0
        assert fake_degassingrun.BAR == 999.0

    def test_restores_on_exception(self, fake_degassingrun):
        from volcatenate.backends.sulfurx import _patch_kd_low_p

        class BoomError(RuntimeError):
            pass

        with pytest.raises(BoomError):
            with _patch_kd_low_p(increment=42.0, threshold_mpa=7.5):
                assert fake_degassingrun.INC == 42.0
                assert fake_degassingrun.BAR == 7.5
                raise BoomError("simulated SulfurX failure")

        assert fake_degassingrun.INC == 999.0
        assert fake_degassingrun.BAR == 999.0


# ── >= 20 MPa warning (integration) ─────────────────────────────────────────
#
# The warning lives inside ``_run_degassing``, which requires the real SulfurX
# install.  Marked as integration so CI skips it when SulfurX is absent.

_KILAUEA = {
    "Sample": "KilaueaKdLowP",
    "T_C": 1200.0,
    "SiO2": 50.19, "TiO2": 2.34, "Al2O3": 12.79,
    "FeOT": 11.34, "MnO": 0.18, "MgO": 9.23, "CaO": 10.44,
    "Na2O": 2.39, "K2O": 0.43, "P2O5": 0.27,
    "H2O": 0.30, "CO2": 0.008, "S": 0.15,
    "Fe3FeT": 0.18, "dNNO": -0.23,
}


def _fast_sulfurx_run_config(tmp_path, **sulfurx_kwargs):
    return RunConfig(
        output_dir=str(tmp_path),
        keep_raw_output=False,
        show_progress=False,
        sulfurx=SulfurXConfig(n_steps=20, **sulfurx_kwargs),
    )


@pytest.mark.integration
class TestHighThresholdWarning:
    @pytest.mark.filterwarnings("ignore: invalid value encountered in ")
    # filters unrelated upstream sulfur_x warning
    def test_warning_fires_when_threshold_at_or_above_20(self, tmp_path, caplog):
        """``kd_low_p_threshold_mpa >= 20`` should emit a logger.warning."""
        from volcatenate.backends.sulfurx import Backend
        from volcatenate.composition import composition_from_dict

        backend = Backend()
        comp = composition_from_dict(_KILAUEA)
        
        cfg = _fast_sulfurx_run_config(tmp_path, kd_low_p_threshold_mpa=25.0)

        with caplog.at_level(logging.WARNING, logger="volcatenate"):
            backend.calculate_degassing(comp, cfg)

        matches = [
            r for r in caplog.records
            if "kd_low_p_threshold_mpa" in r.getMessage() and ">= 20 MPa" in r.getMessage()
        ]
        assert matches, (
            "Expected a kd_low_p_threshold_mpa >= 20 MPa warning, but "
            f"got log records: {[r.getMessage() for r in caplog.records]}"
        )

    @pytest.mark.filterwarnings("ignore: invalid value encountered in ")
    # filters unrelated upstream sulfur_x warning
    def test_warning_silent_when_threshold_below_20(self, tmp_path, caplog):
        """A threshold below 20 MPa (e.g. the README-recommended range) should not warn."""
        from volcatenate.backends.sulfurx import Backend
        from volcatenate.composition import composition_from_dict

        backend = Backend()
        comp = composition_from_dict(_KILAUEA)
        cfg = _fast_sulfurx_run_config(tmp_path, kd_low_p_threshold_mpa=5.0)

        with caplog.at_level(logging.WARNING, logger="volcatenate"):
            backend.calculate_degassing(comp, cfg)

        matches = [
            r for r in caplog.records
            if "kd_low_p_threshold_mpa" in r.getMessage() and ">= 20 MPa" in r.getMessage()
        ]
        assert not matches, (
            "Did not expect a >= 20 MPa warning at threshold=5.0; "
            f"got: {[r.getMessage() for r in matches]}"
        )
