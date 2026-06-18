"""Redox handling / fallthrough tests.

These check that a redox value supplied on a ``MeltComposition``, a Python dict,
or an input CSV is passed to each backend's redox resolver as expected:

  - the correct value is passed through for each acceptable redox format;
  - the resolver raises when no acceptable redox format is provided;
  - the auto-mode fallthrough order is the documented per-backend order.

The resolvers under test are pure ``(comp[, cfg])`` functions, so this file runs
without EVo / MATLAB / SulfurX installed — it exercises the wrapper's redox
dispatch, not the underlying models.

Contract after the redox-conversion removal (volcatenate passes the chosen
indicator through unchanged; it never converts one indicator into another):

  - VolFe  — accepts Fe3FeT / dNNO / dFMQ; auto falls back fo2_column → Fe3FeT
             → dNNO → dFMQ.
  - EVo    — accepts Fe3FeT / dNNO / dFMQ; auto uses Fe3FeT else a buffer.
  - MAGEC  — accepts Fe3FeT / dFMQ (not dNNO); auto honors redox_option then
             Fe3+/FeT, else raises.
  - SulfurX — accepts dFMQ only; raises otherwise.
"""

from __future__ import annotations

import numpy as np
import pytest

from volcatenate.composition import (
    MeltComposition,
    composition_from_dict,
    read_compositions,
)
from volcatenate.config import EVoConfig, MAGECConfig, VolFeConfig
from volcatenate.backends.volfe import _resolve_volfe_redox
from volcatenate.backends.evo import _resolve_fo2_source
from volcatenate.backends.magec import _resolve_magec_redox
from volcatenate.backends.sulfurx import _resolve_sulfurx_redox


# A redox-free basalt base. Tests add whichever redox indicator(s) they need.
BASE = {
    "Sample": "TestBasalt",
    "T_C": 1100.0,
    "SiO2": 50.0,
    "TiO2": 1.5,
    "Al2O3": 15.0,
    "FeOT": 10.0,
    "MnO": 0.18,
    "MgO": 7.5,
    "CaO": 11.0,
    "Na2O": 2.8,
    "K2O": 0.2,
    "P2O5": 0.2,
    "H2O": 0.5,
    "CO2": 0.04,
    "S": 0.12,
}


def comp(**redox) -> MeltComposition:
    """Basalt composition carrying only the given redox indicator(s)."""
    return composition_from_dict({**BASE, **redox})


# ── Layer 1: composition-level — fe3fet_computed precedence ──────────────────


class TestFe3fetComputedPrecedence:
    def test_speciated_iron_yields_ratio(self):
        c = comp(FeO=8.0, Fe2O3=2.0)
        # Fe3+/FeT from speciated FeO + Fe2O3, a positive ratio < 1.
        assert 0.0 < c.fe3fet_computed < 1.0

    def test_explicit_fe3fet_used_when_no_speciation(self):
        c = comp(Fe3FeT=0.18)
        assert c.fe3fet_computed == pytest.approx(0.18)

    def test_speciated_iron_wins_over_explicit_fe3fet(self):
        # Speciated FeO/Fe2O3 takes precedence over an explicit Fe3FeT value.
        c = comp(FeO=8.0, Fe2O3=2.0, Fe3FeT=0.99)
        assert c.fe3fet_computed != pytest.approx(0.99)

    def test_nan_when_no_iron_speciation_or_ratio(self):
        c = comp()  # FeOT only, no Fe3FeT and no speciated iron
        assert np.isnan(c.fe3fet_computed)


# ── Layer 1: ingestion parity — MeltComposition vs dict vs CSV ───────────────


class TestIngestionParity:
    """The same sample, supplied three ways, must resolve identically."""

    def test_three_formats_resolve_identically(self, tmp_path):
        cfg = VolFeConfig()  # defaults: fo2_column=Fe3FeT, fo2_source=auto

        direct = MeltComposition(
            sample="S",
            T_C=1100.0,
            SiO2=50.0,
            FeOT=10.0,
            Fe3FeT=0.18,
            dNNO=-0.3,
            dFMQ=0.25,
        )

        as_dict = composition_from_dict(
            {
                "Sample": "S",
                "T_C": 1100.0,
                "SiO2": 50.0,
                "FeOT": 10.0,
                "Fe3FeT": 0.18,
                "dNNO": -0.3,
                "dFMQ": 0.25,
            }
        )

        csv = tmp_path / "one.csv"
        csv.write_text(
            "Sample,T_C,SiO2,FeOT,Fe3FeT,dNNO,dFMQ\n"
            "S,1100.0,50.0,10.0,0.18,-0.3,0.25\n"
        )
        from_csv = read_compositions(str(csv))[0]

        results = [_resolve_volfe_redox(c, cfg) for c in (direct, as_dict, from_csv)]
        assert results[0] == results[1] == results[2]
        assert results[0] == ("Fe3FeT", pytest.approx(0.18))


# ── Layer 2: VolFe fallthrough ───────────────────────────────────────────────


class TestVolFeAuto:
    def test_prefers_fo2_column_fe3fet(self):
        col, val = _resolve_volfe_redox(comp(Fe3FeT=0.18), VolFeConfig())
        assert col == "Fe3FeT"
        assert val == pytest.approx(0.18)

    def test_falls_back_to_dnno_when_fe3fet_missing(self):
        col, val = _resolve_volfe_redox(comp(dNNO=-0.4), VolFeConfig())
        assert col == "DNNO"
        assert val == pytest.approx(-0.4)

    def test_falls_back_to_dfmq_when_only_dfmq(self):
        col, val = _resolve_volfe_redox(comp(dFMQ=0.7), VolFeConfig())
        assert col == "DFMQ"
        assert val == pytest.approx(0.7)

    def test_fallback_order_dnno_beats_dfmq(self):
        # fo2_column=Fe3FeT is missing; the chain is Fe3FeT → dNNO → dFMQ,
        # so dNNO is chosen over dFMQ when both buffer indicators are present.
        col, _ = _resolve_volfe_redox(comp(dNNO=-0.4, dFMQ=0.7), VolFeConfig())
        assert col == "DNNO"

    def test_fo2_column_dfmq_selected_when_present(self):
        cfg = VolFeConfig(fo2_column="DFMQ")
        col, val = _resolve_volfe_redox(comp(Fe3FeT=0.18, dFMQ=0.7), cfg)
        assert col == "DFMQ"
        assert val == pytest.approx(0.7)


class TestVolFeStrict:
    def test_strict_fe3fet_returns_value(self):
        col, val = _resolve_volfe_redox(
            comp(Fe3FeT=0.18, dNNO=-0.4), VolFeConfig(fo2_source="fe3fet")
        )
        assert col == "Fe3FeT"
        assert val == pytest.approx(0.18)

    def test_strict_fe3fet_raises_when_missing(self):
        with pytest.raises(ValueError):
            _resolve_volfe_redox(comp(dNNO=-0.4), VolFeConfig(fo2_source="fe3fet"))

    def test_strict_dnno_raises_when_missing(self):
        with pytest.raises(ValueError):
            _resolve_volfe_redox(comp(Fe3FeT=0.18), VolFeConfig(fo2_source="dnno"))

    def test_strict_dfmq_raises_when_missing(self):
        with pytest.raises(ValueError):
            _resolve_volfe_redox(comp(Fe3FeT=0.18), VolFeConfig(fo2_source="dfmq"))

    def test_no_redox_raises(self):
        with pytest.raises(ValueError):
            _resolve_volfe_redox(comp(), VolFeConfig())


# ── Layer 2: EVo fallthrough ─────────────────────────────────────────────────


class TestEVoAuto:
    def test_fe3fet_drives_model_path(self):
        block = _resolve_fo2_source(comp(Fe3FeT=0.18), EVoConfig())
        # Fe3+/FeT path: neither absolute-set nor buffer-set.
        assert block["FO2_SET"] is False
        assert block["FO2_buffer_SET"] is False

    def test_dnno_picks_nno_buffer(self):
        block = _resolve_fo2_source(comp(dNNO=-0.4), EVoConfig())
        assert block["FO2_buffer_SET"] is True
        assert block["FO2_buffer"] == "NNO"
        assert block["FO2_buffer_START"] == pytest.approx(-0.4)

    def test_dfmq_picks_fmq_buffer(self):
        block = _resolve_fo2_source(comp(dFMQ=0.7), EVoConfig())
        assert block["FO2_buffer_SET"] is True
        assert block["FO2_buffer"] == "FMQ"
        assert block["FO2_buffer_START"] == pytest.approx(0.7)

    def test_buffer_order_dnno_beats_dfmq(self):
        block = _resolve_fo2_source(comp(dNNO=-0.4, dFMQ=0.7), EVoConfig())
        assert block["FO2_buffer"] == "NNO"


class TestEVoStrict:
    def test_absolute_sets_fo2(self):
        cfg = EVoConfig(fo2_source="absolute", fo2_set=True, fo2_start=1.0e-9)
        block = _resolve_fo2_source(comp(Fe3FeT=0.18), cfg)
        assert block["FO2_SET"] is True
        assert block["FO2_START"] == pytest.approx(1.0e-9)

    def test_absolute_raises_without_fo2_start(self):
        cfg = EVoConfig(fo2_source="absolute", fo2_set=False, fo2_start=0.0)
        with pytest.raises(ValueError):
            _resolve_fo2_source(comp(Fe3FeT=0.18), cfg)

    def test_strict_fe3fet_raises_when_missing(self):
        with pytest.raises(ValueError):
            _resolve_fo2_source(comp(dNNO=-0.4), EVoConfig(fo2_source="fe3fet"))

    def test_buffer_nno_requires_dnno(self):
        cfg = EVoConfig(fo2_source="buffer", fo2_buffer="NNO")
        with pytest.raises(ValueError):
            _resolve_fo2_source(comp(Fe3FeT=0.18), cfg)

    def test_buffer_fmq_uses_dfmq(self):
        cfg = EVoConfig(fo2_source="buffer", fo2_buffer="FMQ")
        block = _resolve_fo2_source(comp(dFMQ=0.7), cfg)
        assert block["FO2_buffer"] == "FMQ"
        assert block["FO2_buffer_START"] == pytest.approx(0.7)


# ── Layer 2: MAGEC fallthrough (no dNNO, no conversion) ──────────────────────


class TestMAGECAuto:
    def test_fe3fet_passed_through(self):
        opt, val = _resolve_magec_redox(comp(Fe3FeT=0.18), MAGECConfig())
        assert opt == "Fe3+/FeT"
        assert val == pytest.approx(0.18)

    def test_fe3fet_preferred_over_dfmq_by_default_option(self):
        # Default redox_option is 'Fe3+/FeT', so Fe3FeT wins when both present.
        opt, val = _resolve_magec_redox(comp(Fe3FeT=0.18, dFMQ=0.7), MAGECConfig())
        assert opt == "Fe3+/FeT"
        assert val == pytest.approx(0.18)

    def test_dfmq_used_when_option_is_dfmq(self):
        cfg = MAGECConfig(redox_option="dFMQ")
        opt, val = _resolve_magec_redox(comp(dFMQ=0.7), cfg)
        assert opt == "dFMQ"
        assert val == pytest.approx(0.7)

    def test_auto_falls_through_to_dfmq(self):
        # redox_option defaults to 'Fe3+/FeT'; with only dFMQ present (a native
        # MAGEC indicator) and no Fe3FeT, auto falls through to dFMQ rather than
        # raising. This selects a native indicator that is on the sample — it is
        # not a conversion.
        opt, val = _resolve_magec_redox(comp(dFMQ=0.7), MAGECConfig())
        assert opt == "dFMQ"
        assert val == pytest.approx(0.7)

    def test_dnno_only_raises(self):
        # MAGEC never accepts dNNO and the wrapper does not convert it.
        with pytest.raises(ValueError):
            _resolve_magec_redox(comp(dNNO=-0.4), MAGECConfig())


class TestMAGECStrict:
    def test_strict_fe3fet_raises_when_missing(self):
        with pytest.raises(ValueError):
            _resolve_magec_redox(comp(dFMQ=0.7), MAGECConfig(redox_source="fe3fet"))

    def test_strict_dfmq_raises_when_missing(self):
        with pytest.raises(ValueError):
            _resolve_magec_redox(comp(Fe3FeT=0.18), MAGECConfig(redox_source="dfmq"))

    def test_strict_dfmq_returns_value(self):
        opt, val = _resolve_magec_redox(
            comp(dFMQ=0.7), MAGECConfig(redox_source="dfmq")
        )
        assert opt == "dFMQ"
        assert val == pytest.approx(0.7)


# ── Layer 2: SulfurX (dFMQ only) ─────────────────────────────────────────────


class TestSulfurX:
    def test_dfmq_passed_through(self):
        assert _resolve_sulfurx_redox(comp(dFMQ=0.55)) == pytest.approx(0.55)

    def test_dfmq_used_even_when_fe3fet_present(self):
        assert _resolve_sulfurx_redox(comp(Fe3FeT=0.18, dFMQ=0.55)) == pytest.approx(
            0.55
        )

    def test_fe3fet_only_raises(self):
        with pytest.raises(ValueError):
            _resolve_sulfurx_redox(comp(Fe3FeT=0.18))

    def test_dnno_only_raises(self):
        with pytest.raises(ValueError):
            _resolve_sulfurx_redox(comp(dNNO=-0.4))

    def test_no_redox_raises(self):
        with pytest.raises(ValueError):
            _resolve_sulfurx_redox(comp())


# ── Layer 4: cross-backend divergence on one sample ──────────────────────────


class TestCrossBackendDivergence:
    def test_fe3fet_and_dfmq_diverge(self):
        # One sample carrying both indicators: three backends key off Fe3FeT,
        # SulfurX keys off dFMQ.
        c = comp(Fe3FeT=0.18, dFMQ=1.0)

        volfe_col, volfe_val = _resolve_volfe_redox(c, VolFeConfig())
        assert (volfe_col, volfe_val) == ("Fe3FeT", pytest.approx(0.18))

        evo_block = _resolve_fo2_source(c, EVoConfig())
        assert evo_block["FO2_buffer_SET"] is False  # Fe3+/FeT path

        magec_opt, magec_val = _resolve_magec_redox(c, MAGECConfig())
        assert (magec_opt, magec_val) == ("Fe3+/FeT", pytest.approx(0.18))

        assert _resolve_sulfurx_redox(c) == pytest.approx(1.0)

    def test_fe3fet_only_runs_three_raises_sulfurx(self):
        c = comp(Fe3FeT=0.18)

        # EVo / VolFe / MAGEC all resolve cleanly.
        assert _resolve_volfe_redox(c, VolFeConfig())[0] == "Fe3FeT"
        assert _resolve_fo2_source(c, EVoConfig())["FO2_SET"] is False
        assert _resolve_magec_redox(c, MAGECConfig())[0] == "Fe3+/FeT"

        # SulfurX cannot run an Fe3FeT-only sample.
        with pytest.raises(ValueError):
            _resolve_sulfurx_redox(c)
