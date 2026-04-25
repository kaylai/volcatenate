"""Gotcha tests — standard failure modes and edge cases.

These probe the places most likely to break silently:
  - Empty DataFrames and empty composition lists
  - NaN and zero volatile values
  - Hydrous vs anhydrous compositions (zero vs positive H2O)
  - Column name mismatches / extra columns in converter input
  - SaturationResult with all-None or mixed results
  - loadData with nonexistent directory (no crash)
  - O2 mass balance with a DataFrame that has no vapor columns
  - normalize_volatiles on a single row, empty DataFrame, NaN initial
  - compute_cs_v_mf: only C species, only S species, empty, NaN rows, S2 coefficient
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from volcatenate import columns as col
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns
from volcatenate.composition import composition_from_dict
from volcatenate.result import SaturationResult


# ── compute_cs_v_mf edge cases ────────────────────────────────────────────────

class TestComputeCSEdgeCases:
    def test_no_sulfur_species_gives_nan(self):
        df = pd.DataFrame({col.CO2_V_MF: [0.5], col.CO_V_MF: [0.1]})
        result = compute_cs_v_mf(df)
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_no_carbon_species_gives_nan(self):
        df = pd.DataFrame({col.SO2_V_MF: [0.5], col.H2S_V_MF: [0.1]})
        result = compute_cs_v_mf(df)
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_zero_sulfur_denominator_gives_nan(self):
        df = pd.DataFrame({
            col.CO2_V_MF: [0.5],
            col.SO2_V_MF: [0.0],
            col.H2S_V_MF: [0.0],
        })
        result = compute_cs_v_mf(df)
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_empty_dataframe_no_crash(self):
        df = pd.DataFrame(columns=[col.CO2_V_MF, col.SO2_V_MF])
        result = compute_cs_v_mf(df)
        assert col.CS_V_MF in result.columns
        assert len(result) == 0

    def test_ocs_counted_in_both_c_and_s(self):
        # OCS contributes 1 C atom and 1 S atom → C/S = 1.0
        df = pd.DataFrame({col.OCS_V_MF: [1.0]})
        result = compute_cs_v_mf(df)
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(1.0)

    def test_s2_coefficient_is_two(self):
        # 1 CO2 (C=1), 1 S2 (S=2) → C/S = 0.5
        df = pd.DataFrame({col.CO2_V_MF: [1.0], col.S2_V_MF: [1.0]})
        result = compute_cs_v_mf(df)
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(0.5)

    def test_nan_treated_as_zero_in_carbon_sum(self):
        # NaN carbon species → C=0, S=0.1 → C/S = 0
        df = pd.DataFrame({col.CO2_V_MF: [np.nan], col.SO2_V_MF: [0.1]})
        result = compute_cs_v_mf(df)
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(0.0)

    def test_nan_treated_as_zero_in_sulfur_sum(self):
        # C=0.5, S=NaN → S=0 → NaN
        df = pd.DataFrame({col.CO2_V_MF: [0.5], col.SO2_V_MF: [np.nan]})
        result = compute_cs_v_mf(df)
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_multirow_mixed(self):
        df = pd.DataFrame({
            col.CO2_V_MF: [0.5, np.nan, 0.3],
            col.SO2_V_MF: [0.2, 0.1, 0.0],
        })
        result = compute_cs_v_mf(df)
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(0.5 / 0.2)
        assert result[col.CS_V_MF].iloc[1] == pytest.approx(0.0)  # nan→0 / 0.1
        assert np.isnan(result[col.CS_V_MF].iloc[2])  # C=0.3, S=0

    def test_all_nan_species_gives_nan(self):
        df = pd.DataFrame({c: [np.nan] for c in col.VAPOR_MF_COLUMNS})
        result = compute_cs_v_mf(df)
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_all_zero_species_gives_nan(self):
        df = pd.DataFrame({c: [0.0] for c in col.VAPOR_MF_COLUMNS})
        result = compute_cs_v_mf(df)
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_no_vapor_columns_at_all(self):
        df = pd.DataFrame({"P_bars": [1000.0]})
        result = compute_cs_v_mf(df)
        assert col.CS_V_MF in result.columns
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_does_not_raise_on_existing_cs_column(self):
        df = pd.DataFrame({
            col.CO2_V_MF: [0.5],
            col.SO2_V_MF: [0.2],
            col.CS_V_MF: [99.0],  # pre-existing; should be overwritten
        })
        result = compute_cs_v_mf(df)
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(0.5 / 0.2)


# ── normalize_volatiles edge cases ────────────────────────────────────────────

class TestNormalizeVolatilesEdgeCases:
    def test_single_row_all_ones(self):
        df = pd.DataFrame({
            col.H2OT_M_WTPC: [0.5],
            col.CO2T_M_PPMW: [300.0],
            col.ST_M_PPMW: [1000.0],
        })
        result = normalize_volatiles(df)
        for norm_col in (col.H2OT_M_WTPC_NORM, col.CO2T_M_PPMW_NORM, col.ST_M_PPMW_NORM):
            assert result[norm_col].iloc[0] == pytest.approx(1.0)

    def test_zero_initial_gives_nan_norm(self):
        df = pd.DataFrame({col.H2OT_M_WTPC: [0.0, 0.3]})
        result = normalize_volatiles(df)
        assert np.isnan(result[col.H2OT_M_WTPC_NORM].iloc[0])

    def test_nan_initial_gives_nan_norm(self):
        df = pd.DataFrame({col.H2OT_M_WTPC: [np.nan, 0.3]})
        result = normalize_volatiles(df)
        assert np.isnan(result[col.H2OT_M_WTPC_NORM].iloc[0])

    def test_empty_dataframe_no_crash(self):
        df = pd.DataFrame(columns=[col.H2OT_M_WTPC, col.CO2T_M_PPMW])
        normalize_volatiles(df)  # must not raise

    def test_only_partial_volatile_columns(self):
        df = pd.DataFrame({col.H2OT_M_WTPC: [0.5, 0.3]})
        result = normalize_volatiles(df)
        assert col.H2OT_M_WTPC_NORM in result.columns
        assert col.CO2T_M_PPMW_NORM not in result.columns


# ── composition_from_dict edge cases ──────────────────────────────────────────

class TestCompositionEdgeCases:
    def test_dry_composition(self):
        comp = composition_from_dict({
            "Sample": "DryMelt", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.0, "CO2": 0.0, "S": 0.0,
        })
        assert comp.H2O == pytest.approx(0.0)
        assert comp.CO2 == pytest.approx(0.0)
        assert comp.S == pytest.approx(0.0)

    def test_high_h2o_hydrous_composition(self):
        comp = composition_from_dict({
            "Sample": "WetMelt", "T_C": 900,
            "SiO2": 55, "TiO2": 0.5, "Al2O3": 18, "FeOT": 5,
            "MnO": 0.1, "MgO": 3, "CaO": 8, "Na2O": 3, "K2O": 1,
            "P2O5": 0.1, "H2O": 6.0, "CO2": 0.05, "S": 0.02,
        })
        assert comp.H2O == pytest.approx(6.0)

    def test_dnno_with_no_fe3fet(self):
        comp = composition_from_dict({
            "Sample": "NNOOnly", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
            "dNNO": 0.5,
        })
        assert comp.dNNO == pytest.approx(0.5)
        assert comp.Fe3FeT is None  # not set

    def test_unknown_keys_silently_ignored(self):
        comp = composition_from_dict({
            "Sample": "X", "T_C": 1200,
            "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
            "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
            "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1,
            "MYSTERY_COLUMN": 42.0,  # should be silently ignored
        })
        assert comp.sample == "X"


# ── SaturationResult edge cases ───────────────────────────────────────────────

class TestSaturationResultEdgeCases:
    def test_empty_equilibrium_state(self):
        result = SaturationResult(
            equilibrium_state={},
            samples=["A"],
            reservoirs=[""],
        )
        df = result.pressure
        assert "Sample" in df.columns
        assert list(df["Sample"]) == ["A"]

    def test_all_nan_pressures(self):
        eq_state = {
            "EVo": pd.DataFrame({
                "Sample": ["A"],
                "Reservoir": [""],
                col.P_BARS: [np.nan],
            }),
        }
        result = SaturationResult(
            equilibrium_state=eq_state,
            samples=["A"],
            reservoirs=[""],
        )
        df = result.pressure
        assert np.isnan(df["EVo_SatP_bars"].iloc[0])

    def test_mixed_valid_and_nan(self):
        eq_state = {
            "EVo": pd.DataFrame({
                "Sample": ["A", "B"],
                "Reservoir": ["", ""],
                col.P_BARS: [1000.0, np.nan],
            }),
        }
        result = SaturationResult(
            equilibrium_state=eq_state,
            samples=["A", "B"],
            reservoirs=["", ""],
        )
        df = result.pressure
        row_a = df.loc[df["Sample"] == "A", "EVo_SatP_bars"].iloc[0]
        row_b = df.loc[df["Sample"] == "B", "EVo_SatP_bars"].iloc[0]
        assert row_a == pytest.approx(1000.0)
        assert np.isnan(row_b)

    def test_sample_not_in_equilibrium_state(self):
        eq_state = {
            "EVo": pd.DataFrame({
                "Sample": ["A"],
                "Reservoir": [""],
                col.P_BARS: [1000.0],
            }),
        }
        result = SaturationResult(
            equilibrium_state=eq_state,
            samples=["A", "B"],  # B is not in EVo results
            reservoirs=["", ""],
        )
        df = result.pressure
        row_b = df.loc[df["Sample"] == "B", "EVo_SatP_bars"].iloc[0]
        assert np.isnan(row_b), "Sample not in equilibrium state should produce NaN pressure"


# ── loadData edge cases ────────────────────────────────────────────────────────

def test_load_data_missing_directory_no_crash(tmp_path):
    """loadData should not crash when model directories do not exist."""
    from volcatenate.compat import loadData

    data_morb, data_kil, data_fuego, data_fogo = loadData(
        model_names=["EVo", "VolFe"],
        topdirectory_name=str(tmp_path / "nonexistent"),
    )
    assert data_morb == {"Name": "MORB"}
    assert data_kil == {"Name": "Kilauea"}


def test_load_data_empty_directory_no_crash(tmp_path):
    """loadData should not crash when model directory exists but is empty."""
    from volcatenate.compat import loadData

    (tmp_path / "EVo").mkdir()
    data_morb, data_kil, data_fuego, data_fogo = loadData(
        model_names=["EVo"],
        topdirectory_name=str(tmp_path),
    )
    assert data_kil == {"Name": "Kilauea"}


def test_load_data_o2_masbal_no_vapor_columns(tmp_path):
    """O2_mass_bal=True must not crash when a DataFrame has no vapor columns."""
    from volcatenate.compat import loadData

    model_dir = tmp_path / "EVo"
    model_dir.mkdir()
    df_out = pd.DataFrame({
        "P_bars": [1000.0],
        "H2OT_m_wtpc": [0.30],
    })
    (model_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    data_morb, data_kil, data_fuego, data_fogo = loadData(
        model_names=["EVo"],
        topdirectory_name=str(tmp_path),
        O2_mass_bal=True,
    )
    assert "EVo" in data_kil


def test_load_data_o2_masbal_with_vapor_columns(tmp_path):
    """O2_mass_bal=True must add SUM_v_mf and XO2_BYDIFF_v_mf columns."""
    from volcatenate.compat import loadData

    model_dir = tmp_path / "EVo"
    model_dir.mkdir()
    df_out = pd.DataFrame({
        "P_bars": [1000.0, 500.0],
        "H2OT_m_wtpc": [0.30, 0.20],
        "H2O_v_mf": [0.70, 0.75],
        "CO2_v_mf": [0.10, 0.08],
        "SO2_v_mf": [0.05, 0.04],
        "O2_v_mf": [0.10, 0.09],
        "H2_v_mf": [0.05, 0.04],
    })
    (model_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    _, data_kil, _, _ = loadData(
        model_names=["EVo"],
        topdirectory_name=str(tmp_path),
        O2_mass_bal=True,
    )
    assert "SUM_v_mf" in data_kil["EVo"].columns
    assert "XO2_BYDIFF_v_mf" in data_kil["EVo"].columns


def test_load_data_simplify_with_o2_mass_bal_true(tmp_path):
    """simplify=True with O2_mass_bal=True must also work (not a regression)."""
    from volcatenate.compat import loadData

    model_dir = tmp_path / "EVo"
    model_dir.mkdir()
    df_out = pd.DataFrame({
        "P_bars": [1000.0],
        "H2OT_m_wtpc": [0.30],
        "EXTRA_COL": [99.0],
    })
    (model_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    _, data_kil, _, _ = loadData(
        model_names=["EVo"],
        topdirectory_name=str(tmp_path),
        O2_mass_bal=True,
        simplify=True,
    )
    assert "EXTRA_COL" not in data_kil["EVo"].columns


# ── ensure_standard_columns with empty DataFrame ─────────────────────────────

def test_ensure_standard_columns_completely_empty_df():
    """ensure_standard_columns must add all standard cols to an empty DataFrame."""
    df = pd.DataFrame()
    result = ensure_standard_columns(df)
    for c in col.STANDARD_COLUMNS:
        assert c in result.columns


def test_ensure_standard_columns_no_matching_columns():
    """ensure_standard_columns adds ALL standard columns when none are present."""
    df = pd.DataFrame({"unexpected_col": [1.0, 2.0]})
    result = ensure_standard_columns(df)
    for c in col.STANDARD_COLUMNS:
        assert c in result.columns
        assert result[c].isna().all()
