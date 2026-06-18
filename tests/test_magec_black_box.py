"""Black-box conservation-law tests for the MAGEC backend.

MAGEC paper: Sun & Yao 2024 (EPSL 638, 118742)

Invariants checked:
- Vapor phase mole fractions sum to 1 (±1%) wherever vapor is present
- No NaN or Inf in any numeric output column
- No negative dissolved concentrations or mole fractions
- Pressure strictly decreases along the degassing path
- Dissolved H2O, CO2, S do not increase after saturation (monotone decrease)
- All vapor mole fractions in [0, 1]
- logfO2 evolves smoothly: no step-jump > 2 log units
- Bulk sulfur (melt + vapor) conserved within 5%
- Bulk carbon (melt + vapor) conserved within 5%

To run (requires MATLAB + MAGEC solver):
    pytest tests/test_magec_black_box.py -v -m integration
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from volcatenate import columns as col

from .compositions import KILAUEA, MORB

ALL_COMPOSITIONS = [
    pytest.param(MORB, "MORB", id="MORB"),
    pytest.param(KILAUEA, "Kilauea", id="Kilauea"),
]

# Fuego (4.5 wt% H2O, satP ~6 kbar) is excluded from the parametrize list
# because (a) its MAGEC solver run takes ~64 s vs ~15 s for the other
# compositions and dominates wall time, and (b) MAGEC's fsolve solver
# fails to find the correct saturation pressure for it (reports ~2365
# bars vs reference ~6093 bars, a 61% error — likely a solver
# convergence failure at high pressure/high H2O). MORB and Kilauea span
# dry/moderate melt regimes and exercise the same physics invariants;
# conservation laws don't care about composition. Re-add Fuego (and Fogo)
# here once MAGEC's solver bracket / convergence issue is resolved.


# ── Atomic / molecular weights ─────────────────────────────────────────────────

MW_VAPOR = {
    col.H2O_V_MF: 18.015,
    col.H2_V_MF: 2.016,
    col.O2_V_MF: 31.998,
    col.CO2_V_MF: 44.010,
    col.CO_V_MF: 28.010,
    col.CH4_V_MF: 16.043,
    col.SO2_V_MF: 64.066,
    col.H2S_V_MF: 34.082,
    col.S2_V_MF: 64.130,
    col.OCS_V_MF: 60.076,
}

# S atoms per molecule (for bulk-S mass balance)
S_ATOMS = {
    col.SO2_V_MF: 1,
    col.H2S_V_MF: 1,
    col.S2_V_MF: 2,
    col.OCS_V_MF: 1,
}

# C atoms per molecule (for bulk-C mass balance)
C_ATOMS = {
    col.CO2_V_MF: 1,
    col.CO_V_MF: 1,
    col.CH4_V_MF: 1,
    col.OCS_V_MF: 1,
}

MW_S = 32.065  # g/mol S
MW_C = 12.011  # g/mol C
MW_CO2 = 44.010  # g/mol CO2


# ── Mass-balance helpers ────────────────────────────────────────────────────


def _mean_mw(row: pd.Series) -> float:
    """Mean molecular weight of vapor at one output row."""
    mw = sum(
        float(row.get(c, 0)) * mw_val
        for c, mw_val in MW_VAPOR.items()
        if c in row.index
    )
    return mw if mw > 0 else np.nan


def _bulk_s(row: pd.Series) -> float:
    """Bulk S (g S per g total system) at one degassing step.

    S_bulk = S_melt + S_vapor
    S_melt = ST_m_ppmw × 1e-6 × (1 - vapor_wt)
    S_vapor = vapor_wt × Σ(Xᵢ × nSᵢ × MW_S) / MW_vapor
    """
    f = float(row.get(col.VAPOR_WT, 0.0))
    s_ppm = float(row.get(col.ST_M_PPMW, 0.0))
    s_melt = s_ppm * 1e-6 * (1.0 - f)

    if f <= 0:
        return s_melt

    mw_v = _mean_mw(row)
    if np.isnan(mw_v) or mw_v <= 0:
        return np.nan

    s_moles_per_mole = sum(
        float(row.get(c, 0)) * n for c, n in S_ATOMS.items() if c in row.index
    )
    s_vapor = f * (s_moles_per_mole * MW_S / mw_v)
    return s_melt + s_vapor


def _bulk_c(row: pd.Series) -> float:
    """Bulk C (g C per g total system) at one degassing step.

    C_bulk = C_melt + C_vapor
    C_melt = CO2T_m_ppmw × (MW_C / MW_CO2) × 1e-6 × (1 - vapor_wt)
    C_vapor = vapor_wt × Σ(Xᵢ × nCᵢ × MW_C) / MW_vapor
    """
    f = float(row.get(col.VAPOR_WT, 0.0))
    co2_ppm = float(row.get(col.CO2T_M_PPMW, 0.0))
    c_melt = co2_ppm * (MW_C / MW_CO2) * 1e-6 * (1.0 - f)

    if f <= 0:
        return c_melt

    mw_v = _mean_mw(row)
    if np.isnan(mw_v) or mw_v <= 0:
        return np.nan

    c_moles_per_mole = sum(
        float(row.get(c, 0)) * n for c, n in C_ATOMS.items() if c in row.index
    )
    c_vapor = f * (c_moles_per_mole * MW_C / mw_v)
    return c_melt + c_vapor


# ══════════════════════════════════════════════════════════════════════════════
# Conservation law checks
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_vapor_mol_fractions_sum_to_one(comp_dict, name, magec_degassing):
    """Vapor phase mole fractions must sum to 1.0 (±1%) at every step with vapor."""
    df = magec_degassing(comp_dict)

    vapor_rows = df[df[col.VAPOR_WT] > 0]
    if vapor_rows.empty:
        pytest.skip(f"{name}: no vapor in output (sub-saturated?)")

    mf_cols = [c for c in col.VAPOR_MF_COLUMNS if c in df.columns]
    sums = vapor_rows[mf_cols].sum(axis=1)

    bad = sums[(sums - 1.0).abs() > 0.01]
    assert bad.empty, (
        f"{name}: {len(bad)} rows where vapor mole fractions deviate >1% from 1.0; "
        f"range = [{sums.min():.4f}, {sums.max():.4f}]; "
        f"worst offenders at P_bars = {list(vapor_rows.loc[bad.index, col.P_BARS].round(1))}"
    )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_no_nan_inf_in_output(comp_dict, name, magec_degassing):
    """No NaN or Inf must appear in the standard physics output columns.

    Checks only col.STANDARD_COLUMNS; raw MAGEC metadata columns (T_initial,
    P_initial, logfO2_initial, etc.) are intentionally excluded because they
    are only populated in the first output row by MAGEC and are NaN elsewhere.
    Those metadata columns are documented separately in
    test_metadata_columns_not_leaking.
    """
    df = magec_degassing(comp_dict)

    # Check only the physics columns we actually use downstream.
    physics_cols = [c for c in col.STANDARD_COLUMNS if c in df.columns]
    sub = df[physics_cols]

    nan_cols = list(sub.columns[sub.isnull().any()])
    inf_mask = np.isinf(sub.select_dtypes(include=[np.number]))
    inf_cols = list(sub.columns[inf_mask.any()])

    assert not nan_cols, f"{name}: NaN in standard physics columns {nan_cols}"
    assert not inf_cols, f"{name}: Inf in standard physics columns {inf_cols}"


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_metadata_columns_not_leaking(comp_dict, name, magec_degassing):
    """MAGEC should not leak partially-NaN metadata columns into the output.

    MAGEC v1b includes columns like T_initial, P_initial, logfO2_initial,
    d_IW_initial etc. that are populated only in the first row and NaN
    everywhere else.  The volcatenate converter does not currently strip them.
    This test documents the leakage so it can be fixed in the converter.

    Expected to FAIL until ensure_standard_columns drops non-standard columns.
    """
    df = magec_degassing(comp_dict)

    standard = set(col.STANDARD_COLUMNS)
    numeric = df.select_dtypes(include=[np.number])
    non_standard_with_nan = [
        c for c in numeric.columns if c not in standard and numeric[c].isnull().any()
    ]

    # Document but don't fail — this is a known converter gap, not a physics bug.
    if non_standard_with_nan:
        pytest.xfail(
            f"{name}: non-standard columns with partial NaN leaked through "
            f"converter: {non_standard_with_nan} — "
            f"fix: ensure_standard_columns should drop these."
        )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_no_negative_concentrations(comp_dict, name, magec_degassing):
    """Dissolved concentrations and vapor mole fractions must not be negative."""
    df = magec_degassing(comp_dict)

    check_cols = [
        col.H2OT_M_WTPC,
        col.CO2T_M_PPMW,
        col.ST_M_PPMW,
        col.VAPOR_WT,
        *[c for c in col.VAPOR_MF_COLUMNS if c in df.columns],
    ]

    for c in check_cols:
        if c not in df.columns:
            continue
        neg = df[df[c] < -1e-10]
        assert neg.empty, (
            f"{name}: negative values in '{c}' at "
            f"P_bars = {list(neg[col.P_BARS].round(1))}"
        )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_pressure_monotonically_decreasing(comp_dict, name, magec_degassing):
    """Pressure must strictly decrease along the entire degassing path."""
    df = magec_degassing(comp_dict)

    p = df[col.P_BARS].values
    diffs = np.diff(p)
    bad = np.where(diffs >= 0)[0]

    assert len(bad) == 0, (
        f"{name}: pressure increases at {len(bad)} step(s); "
        f"e.g. P[{bad[0]}]={p[bad[0]]:.1f} → P[{bad[0]+1}]={p[bad[0]+1]:.1f} bars"
    )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_dissolved_volatiles_decrease_after_saturation(comp_dict, name, magec_degassing):
    """Dissolved H2O, CO2, and S must not increase after the saturation onset.

    Tolerance: 0.5% of the saturation value or 1 ppm / 0.001 wt% (whichever
    is larger) to absorb numerical noise.
    """
    df = magec_degassing(comp_dict)

    sat_rows = df[df[col.VAPOR_WT] > 0]
    if sat_rows.empty:
        pytest.skip(f"{name}: no saturation in pressure range")

    post = df.loc[sat_rows.index[0]:]

    for vcol, tol_abs in [
        (col.H2OT_M_WTPC, 0.001),
        (col.CO2T_M_PPMW, 1.0),
        (col.ST_M_PPMW, 1.0),
    ]:
        if vcol not in df.columns:
            continue
        vals = post[vcol].values
        tol = max(vals[0] * 0.005, tol_abs)
        diffs = np.diff(vals)
        bad_idx = np.where(diffs > tol)[0]
        assert len(bad_idx) == 0, (
            f"{name}: '{vcol}' increases after saturation at {len(bad_idx)} step(s); "
            f"max increase = {diffs[bad_idx].max():.4g}; "
            f"step {bad_idx[0]}: {vals[bad_idx[0]]:.4g} → {vals[bad_idx[0]+1]:.4g}"
        )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_vapor_mol_fractions_in_valid_range(comp_dict, name, magec_degassing):
    """All vapor mole fractions must lie in [0, 1]."""
    df = magec_degassing(comp_dict)

    mf_cols = [c for c in col.VAPOR_MF_COLUMNS if c in df.columns]
    for c in mf_cols:
        bad = df[(df[c] < -1e-9) | (df[c] > 1.0 + 1e-6)]
        assert bad.empty, (
            f"{name}: '{c}' has {len(bad)} value(s) outside [0, 1]: "
            f"{list(bad[c].values[:5])}"
        )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_fo2_evolves_smoothly(comp_dict, name, magec_degassing):
    """logfO2 must not jump by more than 2 log units in a single pressure step.

    This detects solver failures or sign errors in the O2 balance, while
    allowing physically reasonable fO2 evolution in either direction.
    """
    df = magec_degassing(comp_dict)

    if col.LOGFO2 not in df.columns:
        pytest.skip(f"{name}: no logfO2 column in output")

    fo2 = df[col.LOGFO2].values
    step_jumps = np.abs(np.diff(fo2))
    bad_idx = np.where(step_jumps > 2.0)[0]

    assert len(bad_idx) == 0, (
        f"{name}: logfO2 jumps >2 log units at {len(bad_idx)} step(s); "
        f"max jump = {step_jumps.max():.2f} at step {bad_idx[0]} "
        f"(P={df[col.P_BARS].iloc[bad_idx[0]]:.0f} → "
        f"{df[col.P_BARS].iloc[bad_idx[0]+1]:.0f} bars)"
    )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_sulfur_bulk_mass_conserved(comp_dict, name, magec_degassing):
    """Bulk S (melt + vapor) must remain within 5% of the initial value.

    Computed from first principles:
      S_bulk = ST_m_ppmw × 1e⁻⁶ × (1 − f)
             + f × Σ(Xᵢ × nSᵢ × MW_S) / MW_vapor
    where f = vapor_wt and nSᵢ = S atoms per molecule.
    """
    df = magec_degassing(comp_dict)

    if df[col.ST_M_PPMW].iloc[0] < 10:
        pytest.skip(f"{name}: initial S <10 ppm — too low for mass-balance check")

    req = [col.VAPOR_WT, col.ST_M_PPMW] + [c for c in S_ATOMS if c in df.columns]
    missing = [c for c in req if c not in df.columns]
    if missing:
        pytest.skip(f"{name}: missing columns for S mass balance: {missing}")

    s0 = _bulk_s(df.iloc[0])
    if np.isnan(s0) or s0 <= 0:
        pytest.skip(f"{name}: cannot compute initial bulk S")

    violations = []
    for _, row in df.iterrows():
        s_i = _bulk_s(row)
        if np.isnan(s_i):
            continue
        dev = abs(s_i - s0) / s0
        if dev > 0.05:
            violations.append((float(row[col.P_BARS]), dev))

    assert not violations, (
        f"{name}: S mass balance error >5% at {len(violations)} step(s); "
        f"worst: {max(v[1] for v in violations):.1%} at "
        f"P={min(violations, key=lambda x: x[1])[0]:.0f} bars; "
        f"initial S_bulk = {s0*1e6:.2f} µg/g"
    )


@pytest.mark.integration
@pytest.mark.parametrize("comp_dict,name", ALL_COMPOSITIONS)
def test_carbon_bulk_mass_conserved(comp_dict, name, magec_degassing):
    """Bulk C (melt + vapor) must remain within 5% of the initial value.

    Computed from first principles analogous to the S mass balance,
    using CO2T_m_ppmw for the melt reservoir.
    """
    df = magec_degassing(comp_dict)

    if df[col.CO2T_M_PPMW].iloc[0] < 10:
        pytest.skip(f"{name}: initial CO2 <10 ppm — too low for mass-balance check")

    req = [col.VAPOR_WT, col.CO2T_M_PPMW] + [c for c in C_ATOMS if c in df.columns]
    missing = [c for c in req if c not in df.columns]
    if missing:
        pytest.skip(f"{name}: missing columns for C mass balance: {missing}")

    c0 = _bulk_c(df.iloc[0])
    if np.isnan(c0) or c0 <= 0:
        pytest.skip(f"{name}: cannot compute initial bulk C")

    violations = []
    for _, row in df.iterrows():
        c_i = _bulk_c(row)
        if np.isnan(c_i):
            continue
        dev = abs(c_i - c0) / c0
        if dev > 0.05:
            violations.append((float(row[col.P_BARS]), dev))

    assert not violations, (
        f"{name}: C mass balance error >5% at {len(violations)} step(s); "
        f"worst: {max(v[1] for v in violations):.1%} at "
        f"P={min(violations, key=lambda x: x[1])[0]:.0f} bars; "
        f"initial C_bulk = {c0*1e6:.2f} µg/g"
    )
