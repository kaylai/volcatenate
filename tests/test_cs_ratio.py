"""Tests for the elemental C/S vapor ratio computation.

Tests are organized by concern:
  - Stoichiometric correctness (S₂ × 2, OCS dual contribution)
  - NaN propagation for models with partial species
  - Edge cases (zero denominator, empty DataFrames, missing columns)
  - Realistic per-model scenarios matching actual backend outputs
  - Function contract (mutation, overwrite, return value)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from volcatenate import columns as col
from volcatenate.convert import compute_cs_v_mf


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def all_species_zero() -> pd.DataFrame:
    """DataFrame with all 10 vapor species present, all zero."""
    return pd.DataFrame({c: [0.0] for c in col.VAPOR_MF_COLUMNS})


@pytest.fixture
def all_species_nan() -> pd.DataFrame:
    """DataFrame with all 10 vapor species present, all NaN."""
    return pd.DataFrame({c: [np.nan] for c in col.VAPOR_MF_COLUMNS})


# ── Helpers ──────────────────────────────────────────────────────────

# Short aliases for column constants — used only in test parameters
_CO2 = col.CO2_V_MF
_CO = col.CO_V_MF
_CH4 = col.CH4_V_MF
_OCS = col.OCS_V_MF
_SO2 = col.SO2_V_MF
_H2S = col.H2S_V_MF
_S2 = col.S2_V_MF
_H2O = col.H2O_V_MF


def _full_row(**overrides: float) -> pd.DataFrame:
    """Single-row DataFrame with all 10 vapor species defaulting to 0.0.

    Accepts both column constants (``col.CO2_V_MF``) and short aliases
    (``CO2``, ``SO2``, etc.) as keyword argument keys.
    """
    row = {c: 0.0 for c in col.VAPOR_MF_COLUMNS}
    _alias = {
        "CO2": _CO2, "CO": _CO, "CH4": _CH4, "OCS": _OCS,
        "SO2": _SO2, "H2S": _H2S, "S2": _S2,
        "H2O": _H2O, "H2": col.H2_V_MF, "O2": col.O2_V_MF,
    }
    for k, v in overrides.items():
        row[_alias.get(k, k)] = v
    return pd.DataFrame({k: [v] for k, v in row.items()})


def _partial_row(**species: float) -> pd.DataFrame:
    """Single-row DataFrame with ONLY the specified species columns.

    Use when testing behavior with missing columns.
    """
    _alias = {
        "CO2": _CO2, "CO": _CO, "CH4": _CH4, "OCS": _OCS,
        "SO2": _SO2, "H2S": _H2S, "S2": _S2,
        "H2O": _H2O, "H2": col.H2_V_MF, "O2": col.O2_V_MF,
    }
    return pd.DataFrame({_alias.get(k, k): [v] for k, v in species.items()})


def _expect(df: pd.DataFrame, expected: float) -> None:
    """Run ``compute_cs_v_mf`` on a COPY and assert the scalar result."""
    result = compute_cs_v_mf(df.copy())
    actual = float(result[col.CS_V_MF].iloc[0])
    if np.isnan(expected):
        assert np.isnan(actual), f"expected NaN, got {actual}"
    else:
        assert actual == pytest.approx(expected), f"expected {expected}, got {actual}"


# ── 1. Stoichiometric correctness ────────────────────────────────────

class TestStoichiometry:
    """Each species must contribute the correct number of C or S atoms."""

    @pytest.mark.parametrize(
        "c_col, c_val, s_col, s_val, expected",
        [
            ("CO2", 0.6, "SO2", 0.3, 2.0),   # 1C : 1S
            ("CO",  0.4, "SO2", 0.2, 2.0),   # 1C : 1S
            ("CH4", 0.1, "SO2", 0.05, 2.0),  # 1C : 1S
            ("CO2", 0.6, "H2S", 0.3, 2.0),   # 1C : 1S
            ("CO2", 0.5, "S2",  0.25, 1.0),  # 1C : 2S → 0.5 / (2×0.25)
        ],
        ids=["CO2:SO2", "CO:SO2", "CH4:SO2", "CO2:H2S", "CO2:S2"],
    )
    def test_individual_species_pairs(self, c_col, c_val, s_col, s_val, expected):
        _expect(_full_row(**{c_col: c_val, s_col: s_val}), expected)

    def test_s2_weighted_by_two(self):
        """S₂ contains 2 sulfur atoms: C/S = CO₂ / (SO₂ + 2·S₂)."""
        df = _full_row(CO2=0.5, SO2=0.25, S2=0.125)
        # S = 0.25 + 2×0.125 = 0.5
        _expect(df, 1.0)

    def test_ocs_in_both_numerator_and_denominator(self):
        """OCS contributes 1 C to numerator and 1 S to denominator."""
        df = _full_row(CO2=0.3, OCS=0.1, SO2=0.2)
        # C = 0.3 + 0.1 = 0.4, S = 0.2 + 0.1 = 0.3
        _expect(df, 4.0 / 3.0)

    def test_full_formula_all_species(self):
        """Hand-verified calculation with every species populated."""
        df = _full_row(CO2=0.20, CO=0.05, CH4=0.02, OCS=0.03,
                       SO2=0.10, H2S=0.04, S2=0.01)
        c = 0.20 + 0.05 + 0.02 + 0.03            # = 0.30
        s = 0.10 + 0.04 + 2 * 0.01 + 0.03        # = 0.19
        _expect(df, c / s)

    def test_s2_as_sole_sulfur_species(self):
        """When S₂ is the only S species, denominator = 2·X_S₂."""
        _expect(_full_row(CO2=0.5, S2=0.25), 0.5 / (2 * 0.25))


# ── 2. NaN handling ──────────────────────────────────────────────────

class TestNaNHandling:
    """NaN in a species column means that model doesn't track it → 0."""

    @pytest.mark.parametrize("nan_col", [_S2, _OCS, _CO, _CH4],
                             ids=["S2", "OCS", "CO", "CH4"])
    def test_single_nan_species_ignored(self, nan_col):
        """A NaN in one species doesn't poison the ratio."""
        df = _full_row(CO2=0.6, SO2=0.3)
        df[nan_col] = np.nan
        _expect(df, 2.0)

    def test_all_c_nan_gives_zero_numerator(self):
        """All C species NaN → numerator = 0 → C/S = 0."""
        df = _full_row(SO2=0.5)
        for c in col.C_SPECIES:
            df[c] = np.nan
        _expect(df, 0.0)

    def test_all_s_nan_gives_nan(self):
        """All S species NaN → denominator = 0 → NaN."""
        df = _full_row(CO2=0.5)
        for s in col.S_SPECIES:
            df[s] = np.nan
        _expect(df, np.nan)

    def test_everything_nan(self, all_species_nan):
        """All species NaN → NaN."""
        _expect(all_species_nan, np.nan)

    def test_nan_per_row_independence(self):
        """NaN in one row doesn't affect another row's result."""
        df = pd.DataFrame({
            _CO2: [0.5, 0.5],
            _SO2: [0.25, 0.25],
            _S2:  [np.nan, 0.125],
            **{c: [0.0, 0.0] for c in col.VAPOR_MF_COLUMNS
               if c not in (_CO2, _SO2, _S2)},
        })
        result = compute_cs_v_mf(df.copy())
        # Row 0: S₂ NaN→0 → S=0.25 → C/S=2.0
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(2.0)
        # Row 1: S₂=0.125 → S=0.25+2×0.125=0.5 → C/S=1.0
        assert result[col.CS_V_MF].iloc[1] == pytest.approx(1.0)


# ── 3. Zero denominator ─────────────────────────────────────────────

class TestZeroDenominator:
    """C/S must be NaN when total sulfur atoms = 0."""

    def test_carbon_present_but_no_sulfur(self, all_species_zero):
        """C > 0, S = 0 → NaN (not inf)."""
        all_species_zero[_CO2] = 0.5
        _expect(all_species_zero, np.nan)

    def test_all_zero(self, all_species_zero):
        """C = 0, S = 0 → NaN."""
        _expect(all_species_zero, np.nan)


# ── 4. Missing columns ──────────────────────────────────────────────

class TestMissingColumns:
    """DataFrames that lack some or all species columns entirely."""

    def test_partial_columns_still_computes(self):
        """Only CO₂ and SO₂ columns exist — other species skipped."""
        _expect(_partial_row(CO2=0.6, SO2=0.3), 2.0)

    def test_no_c_columns(self):
        """No carbon species at all → NaN."""
        df = _partial_row(SO2=0.5, H2S=0.2)
        result = compute_cs_v_mf(df.copy())
        assert col.CS_V_MF in result.columns
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_no_s_columns(self):
        """No sulfur species at all → NaN."""
        df = _partial_row(CO2=0.5, CO=0.1)
        result = compute_cs_v_mf(df.copy())
        assert col.CS_V_MF in result.columns
        assert np.isnan(result[col.CS_V_MF].iloc[0])

    def test_no_species_columns_at_all(self):
        """No recognized species → CS_v_mf added as NaN."""
        df = pd.DataFrame({col.P_BARS: [1000.0]})
        result = compute_cs_v_mf(df.copy())
        assert col.CS_V_MF in result.columns
        assert np.isnan(result[col.CS_V_MF].iloc[0])


# ── 5. Per-model scenarios ───────────────────────────────────────────

class TestModelScenarios:
    """Realistic species availability for each volcanic model backend."""

    def test_evo(self):
        """EVo: 9 gas species, OCS = 0.0 (not modeled)."""
        df = _full_row(CO2=0.30, CO=0.02, CH4=0.001,
                       SO2=0.05, H2S=0.01, S2=0.005)
        c = 0.30 + 0.02 + 0.001       # OCS=0
        s = 0.05 + 0.01 + 2 * 0.005   # OCS=0
        _expect(df, c / s)

    def test_volfe(self):
        """VolFe: all species including OCS with real values."""
        df = _full_row(CO2=0.25, CO=0.01, CH4=0.001, OCS=0.005,
                       SO2=0.04, H2S=0.008, S2=0.003)
        c = 0.25 + 0.01 + 0.001 + 0.005
        s = 0.04 + 0.008 + 2 * 0.003 + 0.005
        _expect(df, c / s)

    def test_magec(self):
        """MAGEC: all species, COS mapped to OCS column."""
        df = _full_row(CO2=0.20, CO=0.005, OCS=0.002,
                       SO2=0.03, H2S=0.01, S2=0.001)
        c = 0.20 + 0.005 + 0.002      # CH4=0
        s = 0.03 + 0.01 + 2 * 0.001 + 0.002
        _expect(df, c / s)

    def test_sulfurx(self):
        """SulfurX: only CO₂, SO₂, H₂S real; S₂/CO/CH₄/OCS are NaN."""
        df = _full_row(CO2=0.80, SO2=0.10, H2S=0.05, H2O=0.05)
        for nan_col in [_S2, _CO, _CH4, _OCS]:
            df[nan_col] = np.nan
        _expect(df, 0.80 / (0.10 + 0.05))

    def test_vesical(self):
        """VESIcal: H₂O-CO₂ only, all S species NaN → NaN."""
        df = _full_row(CO2=0.05, H2O=0.95)
        for s in col.S_SPECIES:
            df[s] = np.nan
        for c in [_CO, _CH4, _OCS]:
            df[c] = np.nan
        _expect(df, np.nan)


# ── 6. Multi-row / degassing path ───────────────────────────────────

class TestMultiRow:
    """Element-wise computation across rows in a degassing path."""

    def test_each_row_independent(self):
        """Two rows with different compositions get different C/S."""
        df = pd.DataFrame({
            _CO2: [0.6, 0.3],
            _SO2: [0.3, 0.1],
            **{c: [0.0, 0.0] for c in col.VAPOR_MF_COLUMNS
               if c not in (_CO2, _SO2)},
        })
        result = compute_cs_v_mf(df.copy())
        assert result[col.CS_V_MF].iloc[0] == pytest.approx(2.0)
        assert result[col.CS_V_MF].iloc[1] == pytest.approx(3.0)

    def test_degassing_path_monotonic_decrease(self):
        """C/S decreases as sulfur species increase during degassing."""
        df = pd.DataFrame({
            col.P_BARS: [1000, 500, 100],
            _CO2: [0.50, 0.40, 0.20],
            _SO2: [0.01, 0.05, 0.15],
            **{c: [0.0, 0.0, 0.0] for c in col.VAPOR_MF_COLUMNS
               if c not in (_CO2, _SO2)},
        })
        result = compute_cs_v_mf(df.copy())
        cs = result[col.CS_V_MF].values
        assert cs[0] == pytest.approx(50.0)
        assert cs[1] == pytest.approx(8.0)
        assert cs[2] == pytest.approx(20.0 / 15.0)
        assert cs[0] > cs[1] > cs[2]


# ── 7. Function contract ────────────────────────────────────────────

class TestFunctionContract:
    """Verify API behavior: mutation, return value, overwrite."""

    def test_returns_same_dataframe_object(self):
        """Return value is the same object that was passed in."""
        df = _full_row(CO2=0.5, SO2=0.25)
        returned = compute_cs_v_mf(df)
        assert returned is df

    def test_modifies_in_place(self):
        """CS_v_mf column is added directly to the input DataFrame."""
        df = _full_row(CO2=0.5, SO2=0.25)
        assert col.CS_V_MF not in df.columns
        compute_cs_v_mf(df)
        assert col.CS_V_MF in df.columns
        assert df[col.CS_V_MF].iloc[0] == pytest.approx(2.0)

    def test_overwrites_preexisting_value(self):
        """A pre-existing CS_v_mf (e.g. VolFe native) is overwritten."""
        df = _full_row(CO2=0.6, SO2=0.3)
        df[col.CS_V_MF] = 999.0
        compute_cs_v_mf(df)
        assert df[col.CS_V_MF].iloc[0] == pytest.approx(2.0)

    def test_preserves_existing_when_no_species_present(self):
        """If no species columns exist, an existing CS_v_mf is kept."""
        df = pd.DataFrame({col.P_BARS: [1000.0], col.CS_V_MF: [42.0]})
        compute_cs_v_mf(df)
        assert df[col.CS_V_MF].iloc[0] == pytest.approx(42.0)

    def test_only_adds_cs_column(self):
        """Only CS_v_mf is added; no other columns are created."""
        df = _full_row(CO2=0.5, SO2=0.25)
        original_cols = set(df.columns)
        compute_cs_v_mf(df)
        new_cols = set(df.columns) - original_cols
        assert new_cols == {col.CS_V_MF}


# ── 8. Empty DataFrame ──────────────────────────────────────────────

class TestEmptyDataFrame:

    def test_empty_with_species_columns(self):
        """Zero rows, species columns present → empty CS_v_mf column."""
        df = pd.DataFrame({c: pd.Series(dtype=float) for c in col.VAPOR_MF_COLUMNS})
        result = compute_cs_v_mf(df.copy())
        assert col.CS_V_MF in result.columns
        assert len(result) == 0

    def test_empty_without_species_columns(self):
        """Zero rows, no species → CS_v_mf column still added."""
        df = pd.DataFrame({col.P_BARS: pd.Series(dtype=float)})
        result = compute_cs_v_mf(df.copy())
        assert col.CS_V_MF in result.columns
        assert len(result) == 0


# ── 9. Column definitions ───────────────────────────────────────────

class TestColumnDefinitions:
    """Verify columns.py definitions are self-consistent."""

    def test_c_species_and_s_species_are_dicts(self):
        assert isinstance(col.C_SPECIES, dict)
        assert isinstance(col.S_SPECIES, dict)

    def test_all_species_in_vapor_mf_columns(self):
        for species in {*col.C_SPECIES, *col.S_SPECIES}:
            assert species in col.VAPOR_MF_COLUMNS, (
                f"{species} in C/S dicts but not in VAPOR_MF_COLUMNS"
            )

    def test_stoichiometric_coefficients(self):
        """Pin the exact coefficients that define the formula."""
        assert col.C_SPECIES == {_CO2: 1.0, _CO: 1.0, _CH4: 1.0, _OCS: 1.0}
        assert col.S_SPECIES == {_SO2: 1.0, _H2S: 1.0, _S2: 2.0, _OCS: 1.0}

    def test_ocs_appears_in_both_dicts(self):
        assert _OCS in col.C_SPECIES
        assert _OCS in col.S_SPECIES

    def test_all_coefficients_positive(self):
        for d in (col.C_SPECIES, col.S_SPECIES):
            for species, coeff in d.items():
                assert coeff > 0, f"{species} has coefficient {coeff}"
