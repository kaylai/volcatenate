"""Unit tests for volcatenate public API and internal helpers.

Coverage:
  - volcatenate.convert: normalize_volatiles, ensure_standard_columns
  - volcatenate.composition: MeltComposition, composition_from_dict
  - volcatenate.config: RunConfig YAML round-trip, EVoConfig.run_type
  - volcatenate.result: SaturationResult.pressure, .equilibrium_state
  - volcatenate.core: _resolve_models, _resolve_compositions
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from volcatenate import columns as col
from volcatenate.convert import (
    compute_cs_v_mf,
    normalize_volatiles,
    ensure_standard_columns,
)
from volcatenate.composition import MeltComposition, composition_from_dict
from volcatenate.config import RunConfig, EVoConfig, save_config, load_config
from volcatenate.result import SaturationResult
from volcatenate.core import _resolve_models, _resolve_compositions


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_comp() -> MeltComposition:
    return composition_from_dict({
        "Sample": "TestSample",
        "T_C": 1200.0,
        "SiO2": 50.0, "TiO2": 1.0, "Al2O3": 15.0,
        "FeOT": 10.0, "MnO": 0.2, "MgO": 8.0, "CaO": 10.0,
        "Na2O": 2.5, "K2O": 0.5, "P2O5": 0.2,
        "H2O": 0.5, "CO2": 0.05, "S": 0.1,
        "Fe3FeT": 0.15,
    })


@pytest.fixture
def degassing_df() -> pd.DataFrame:
    return pd.DataFrame({
        col.P_BARS: [1000.0, 750.0, 500.0, 250.0, 1.0],
        col.H2OT_M_WTPC: [0.5, 0.45, 0.38, 0.25, 0.05],
        col.CO2T_M_PPMW: [500.0, 380.0, 250.0, 100.0, 5.0],
        col.ST_M_PPMW: [1500.0, 1400.0, 1200.0, 800.0, 100.0],
    })


# ── convert.normalize_volatiles ───────────────────────────────────────────────

class TestNormalizeVolatiles:
    def test_adds_norm_columns(self, degassing_df):
        result = normalize_volatiles(degassing_df)
        assert col.H2OT_M_WTPC_NORM in result.columns
        assert col.CO2T_M_PPMW_NORM in result.columns
        assert col.ST_M_PPMW_NORM in result.columns

    def test_first_row_is_one(self, degassing_df):
        result = normalize_volatiles(degassing_df)
        assert result[col.H2OT_M_WTPC_NORM].iloc[0] == pytest.approx(1.0)
        assert result[col.CO2T_M_PPMW_NORM].iloc[0] == pytest.approx(1.0)
        assert result[col.ST_M_PPMW_NORM].iloc[0] == pytest.approx(1.0)

    def test_monotonically_decreasing(self, degassing_df):
        result = normalize_volatiles(degassing_df)
        norms = result[col.H2OT_M_WTPC_NORM].values
        assert all(norms[i] >= norms[i + 1] for i in range(len(norms) - 1))

    def test_zero_initial_gives_nan(self):
        df = pd.DataFrame({
            col.H2OT_M_WTPC: [0.0, 0.0],
            col.CO2T_M_PPMW: [100.0, 50.0],
            col.ST_M_PPMW: [500.0, 200.0],
        })
        result = normalize_volatiles(df)
        assert np.isnan(result[col.H2OT_M_WTPC_NORM].iloc[0])

    def test_nan_initial_value_gives_nan(self):
        df = pd.DataFrame({col.H2OT_M_WTPC: [np.nan, 0.3]})
        result = normalize_volatiles(df)
        assert np.isnan(result[col.H2OT_M_WTPC_NORM].iloc[0])

    def test_missing_column_not_added(self):
        df = pd.DataFrame({col.H2OT_M_WTPC: [0.5, 0.3]})
        result = normalize_volatiles(df)
        assert col.H2OT_M_WTPC_NORM in result.columns
        assert col.CO2T_M_PPMW_NORM not in result.columns

    def test_returns_same_dataframe(self, degassing_df):
        result = normalize_volatiles(degassing_df)
        assert result is degassing_df  # mutates in place

    def test_single_row_gives_one(self):
        df = pd.DataFrame({
            col.H2OT_M_WTPC: [0.5],
            col.CO2T_M_PPMW: [300.0],
            col.ST_M_PPMW: [1000.0],
        })
        result = normalize_volatiles(df)
        assert result[col.H2OT_M_WTPC_NORM].iloc[0] == pytest.approx(1.0)

    def test_empty_dataframe_no_crash(self):
        df = pd.DataFrame(columns=[col.H2OT_M_WTPC])
        normalize_volatiles(df)  # must not raise


# ── convert.ensure_standard_columns ──────────────────────────────────────────

class TestEnsureStandardColumns:
    def test_adds_all_missing_as_nan(self):
        df = pd.DataFrame({"P_bars": [100.0]})
        result = ensure_standard_columns(df)
        for c in col.STANDARD_COLUMNS:
            assert c in result.columns

    def test_does_not_overwrite_existing(self):
        df = pd.DataFrame({col.P_BARS: [999.0]})
        result = ensure_standard_columns(df)
        assert result[col.P_BARS].iloc[0] == pytest.approx(999.0)

    def test_new_columns_are_nan(self):
        df = pd.DataFrame({col.P_BARS: [100.0]})
        result = ensure_standard_columns(df)
        for c in col.STANDARD_COLUMNS:
            if c != col.P_BARS:
                assert result[c].isna().all(), f"Column {c} should be NaN"

    def test_returns_same_dataframe(self):
        df = pd.DataFrame({col.P_BARS: [100.0]})
        result = ensure_standard_columns(df)
        assert result is df


# ── composition_from_dict ─────────────────────────────────────────────────────

class TestCompositionFromDict:
    def test_basic_creation(self, minimal_comp):
        assert minimal_comp.sample == "TestSample"
        assert minimal_comp.T_C == pytest.approx(1200.0)
        assert minimal_comp.SiO2 == pytest.approx(50.0)

    def test_feot_alias(self):
        comp = composition_from_dict({
            "Sample": "X", "T_C": 1200, "FeOT": 10.0,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "MnO": 0.2,
            "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5, "P2O5": 0.2,
            "H2O": 0.5, "CO2": 0.05, "S": 0.1,
        })
        assert comp.FeOT == pytest.approx(10.0)

    def test_fe3fet_from_field(self, minimal_comp):
        assert minimal_comp.fe3fet_computed == pytest.approx(0.15)

    def test_sample_alias(self):
        comp = composition_from_dict({
            "sample": "lower_s",  # lowercase alias supported
            "T_C": 1200, "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.5, "CO2": 0.05, "S": 0.1,
        })
        assert comp.sample == "lower_s"

    def test_dnno_alias(self):
        comp = composition_from_dict({
            "Sample": "X", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
            "DNNO": 0.5,  # uppercase alias → dNNO
        })
        assert comp.dNNO == pytest.approx(0.5)

    def test_missing_volatiles_default_to_zero(self):
        comp = composition_from_dict({
            "Sample": "NoVols", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2,
        })
        assert comp.H2O == pytest.approx(0.0)
        assert comp.CO2 == pytest.approx(0.0)
        assert comp.S == pytest.approx(0.0)

    def test_speciated_iron_computes_feot(self):
        # If FeO + Fe2O3 are given (not FeOT), FeOT should be computed
        comp = composition_from_dict({
            "Sample": "X", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15,
            "FeO": 8.0, "Fe2O3": 2.5,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
        })
        assert comp.FeOT > 0


# ── MeltComposition.fe3fet_computed ──────────────────────────────────────────

class TestFe3fetComputed:
    def test_from_fe3fet_field(self):
        comp = composition_from_dict({
            "Sample": "X", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
            "Fe3FeT": 0.20,
        })
        assert comp.fe3fet_computed == pytest.approx(0.20)

    def test_no_redox_gives_nan(self):
        comp = composition_from_dict({
            "Sample": "X", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
        })
        assert np.isnan(comp.fe3fet_computed)


# ── config round-trip ─────────────────────────────────────────────────────────

class TestConfigRoundTrip:
    def test_save_and_load(self, tmp_path):
        original = RunConfig(
            output_dir="my_output",
            verbose=True,
            evo=EVoConfig(p_stop=5, run_type="open"),
        )
        path = str(tmp_path / "config.yaml")
        save_config(original, path)
        loaded = load_config(path)
        assert loaded.output_dir == "my_output"
        assert loaded.verbose is True
        assert loaded.evo.p_stop == 5
        assert loaded.evo.run_type == "open"

    def test_partial_yaml_uses_defaults(self, tmp_path):
        path = str(tmp_path / "partial.yaml")
        with open(path, "w") as f:
            f.write("output_dir: partial_output\n")
        loaded = load_config(path)
        assert loaded.output_dir == "partial_output"
        assert loaded.evo.p_stop == RunConfig().evo.p_stop

    def test_run_type_default_in_config(self):
        cfg = RunConfig()
        assert cfg.evo.run_type == "closed"

    def test_save_includes_run_type(self, tmp_path):
        path = str(tmp_path / "config.yaml")
        save_config(RunConfig(evo=EVoConfig(run_type="open")), path)
        content = open(path).read()
        assert "run_type" in content
        assert "open" in content


# ── SaturationResult ─────────────────────────────────────────────────────────

class TestSaturationResult:
    def _make_result(self) -> SaturationResult:
        eq_state = {
            "EVo": pd.DataFrame({
                "Sample": ["A", "B"],
                "Reservoir": ["", ""],
                col.P_BARS: [1000.0, 1500.0],
                col.H2OT_M_WTPC: [0.3, 0.5],
            }),
            "VolFe": pd.DataFrame({
                "Sample": ["A", "B"],
                "Reservoir": ["", ""],
                col.P_BARS: [1050.0, 1480.0],
                col.H2OT_M_WTPC: [0.3, 0.5],
            }),
        }
        return SaturationResult(
            equilibrium_state=eq_state,
            samples=["A", "B"],
            reservoirs=["", ""],
        )

    def test_pressure_has_model_columns(self):
        r = self._make_result()
        assert "EVo_SatP_bars" in r.pressure.columns
        assert "VolFe_SatP_bars" in r.pressure.columns

    def test_pressure_has_sample_column(self):
        r = self._make_result()
        assert "Sample" in r.pressure.columns
        assert list(r.pressure["Sample"]) == ["A", "B"]

    def test_pressure_values_correct(self):
        r = self._make_result()
        evo_p = r.pressure.loc[r.pressure["Sample"] == "A", "EVo_SatP_bars"].iloc[0]
        assert evo_p == pytest.approx(1000.0)

    def test_equilibrium_state_keys(self):
        r = self._make_result()
        assert set(r.equilibrium_state.keys()) == {"EVo", "VolFe"}

    def test_pressure_is_lazy(self):
        r = self._make_result()
        assert r._pressure is None
        _ = r.pressure
        assert r._pressure is not None

    def test_dataframe_delegation(self):
        r = self._make_result()
        # SaturationResult should behave like a DataFrame for backward compat
        assert len(r) == 2
        assert "Sample" in r.columns


# ── core._resolve_models ──────────────────────────────────────────────────────

class TestResolveModels:
    def test_none_returns_all(self):
        from volcatenate.backends import list_backends
        assert _resolve_models(None) == list_backends()

    def test_all_string_returns_all(self):
        from volcatenate.backends import list_backends
        assert _resolve_models("all") == list_backends()

    def test_list_all_returns_all(self):
        from volcatenate.backends import list_backends
        assert _resolve_models(["all"]) == list_backends()

    def test_explicit_list(self):
        assert _resolve_models(["EVo", "VolFe"]) == ["EVo", "VolFe"]

    def test_comma_string(self):
        assert _resolve_models("EVo,VolFe") == ["EVo", "VolFe"]

    def test_comma_string_with_spaces(self):
        assert _resolve_models("EVo, VolFe") == ["EVo", "VolFe"]


# ── core._resolve_compositions ────────────────────────────────────────────────

class TestResolveCompositions:
    def test_single_melt_composition(self, minimal_comp):
        result = _resolve_compositions(minimal_comp)
        assert len(result) == 1
        assert result[0] is minimal_comp

    def test_dict_input(self):
        d = {
            "Sample": "DictComp", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
        }
        result = _resolve_compositions(d)
        assert len(result) == 1
        assert result[0].sample == "DictComp"

    def test_list_of_dicts(self):
        comps = [
            {"Sample": "A", "T_C": 1200, "SiO2": 50, "TiO2": 1, "Al2O3": 15,
             "FeOT": 10, "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5,
             "K2O": 0.5, "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1},
            {"Sample": "B", "T_C": 1100, "SiO2": 48, "TiO2": 1, "Al2O3": 16,
             "FeOT": 9, "MnO": 0.2, "MgO": 9, "CaO": 11, "Na2O": 2.5,
             "K2O": 0.4, "P2O5": 0.2, "H2O": 0.2, "CO2": 0.03, "S": 0.08},
        ]
        result = _resolve_compositions(comps)
        assert len(result) == 2
        assert result[0].sample == "A"
        assert result[1].sample == "B"

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            _resolve_compositions(42)

    def test_csv_file(self, tmp_path):
        csv_content = (
            "Sample,T_C,SiO2,TiO2,Al2O3,FeOT,MnO,MgO,CaO,Na2O,K2O,P2O5,"
            "H2O,CO2,S,Fe3FeT\n"
            "TestComp,1200,50,1,15,10,0.2,8,10,2.5,0.5,0.2,0.3,0.05,0.1,0.15\n"
        )
        csv_path = str(tmp_path / "comps.csv")
        with open(csv_path, "w") as f:
            f.write(csv_content)
        result = _resolve_compositions(csv_path)
        assert len(result) == 1
        assert result[0].sample == "TestComp"
