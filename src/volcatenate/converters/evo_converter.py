"""Convert raw EVo *dgs_output* CSV to the standardized column format.

EVo outputs columns like ``P``, ``FMQ``, ``mH2O``, ``fo2``, ``Gas_wt``,
``H2O_melt``, ``CO2_melt``, ``Stot_melt``, ``S6+_melt``, etc.

This converter renames / derives them into the canonical names defined
in :mod:`volcatenate.columns`.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from volcatenate import columns as col


# ── Molecular weights (from evo.constants) ──────────────────────────
_MW: dict[str, float] = {
    "sio2":  60.0843,
    "tio2":  79.8658,
    "al2o3": 101.961278,
    "feo":   71.8444,
    "mno":   70.937445,
    "mgo":   40.3044,
    "cao":   56.0774,
    "na2o":  61.978938,
    "k2o":   94.196,
    "p2o5":  141.944524,
}

# ── Direct column renames ───────────────────────────────────────────
_RENAME: dict[str, str] = {
    "P":   col.P_BARS,
    "FMQ": col.DFMQ,
}

# Vapor mole-fraction columns: m* prefix → *_v_mf
_VAPOR_MF_MAP: dict[str, str] = {
    "mH2O": col.H2O_V_MF,
    "mH2":  col.H2_V_MF,
    "mO2":  col.O2_V_MF,
    "mCO2": col.CO2_V_MF,
    "mCO":  col.CO_V_MF,
    "mCH4": col.CH4_V_MF,
    "mSO2": col.SO2_V_MF,
    "mH2S": col.H2S_V_MF,
    "mS2":  col.S2_V_MF,
}


# ── Helpers ─────────────────────────────────────────────────────────

def _wt_to_molfrac(composition: dict[str, float]) -> dict[str, float]:
    """Convert oxide wt% dict → mole-fraction dict with lowercase keys.

    The output format is what EVo's :func:`kc91_fo2` expects.
    """
    key_map = {
        "SiO2": "sio2", "TiO2": "tio2", "Al2O3": "al2o3",
        "FeOT": "feo",  "MnO": "mno",   "MgO": "mgo",
        "CaO": "cao",   "Na2O": "na2o",  "K2O": "k2o",
        "P2O5": "p2o5",
    }
    moles: dict[str, float] = {}
    for src_key, evo_key in key_map.items():
        wt = composition.get(src_key, 0.0)
        moles[evo_key] = wt / _MW[evo_key]

    total = sum(moles.values())
    return {k: v / total for k, v in moles.items()} if total > 0 else moles


# ── Public API ──────────────────────────────────────────────────────

def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* looks like an unconverted EVo dgs_output file."""
    return "P" in df.columns and col.P_BARS not in df.columns


def convert(
    df: pd.DataFrame,
    composition: Optional[dict[str, float]] = None,
    T_K: Optional[float] = None,
) -> pd.DataFrame:
    """Convert a raw EVo DataFrame to the standardized column format.

    Parameters
    ----------
    df : pd.DataFrame
        Raw EVo output (as read from a dgs_output CSV).
    composition : dict, optional
        Starting melt composition in wt% with keys like ``SiO2``,
        ``Al2O3``, ``FeOT``, etc.  Required for Fe3+/FeT calculation
        via EVo's Kress & Carmichael (1991) model.  If *None*,
        ``Fe3Fet_m`` is set to NaN.
    T_K : float, optional
        Temperature in Kelvin.  Required for Fe3+/FeT calculation.

    Returns
    -------
    pd.DataFrame
        Copy with standardized column names and derived columns.
    """
    out = df.copy()

    # 1. Direct renames (pressure, dFMQ, vapor mole fractions)
    out.rename(columns={**_RENAME, **_VAPOR_MF_MAP}, inplace=True)

    # 2. logfO2 from linear fO2 (raw column is lowercase "fo2")
    if "fo2" in out.columns:
        out[col.LOGFO2] = np.log10(out["fo2"])

    # 3. vapor_wt: Gas_wt is a percentage → convert to mass fraction
    if "Gas_wt" in out.columns:
        out[col.VAPOR_WT] = out["Gas_wt"] / 100.0

    # 4. Melt volatile concentrations
    #    H2O_melt is already wt%
    if "H2O_melt" in out.columns:
        out[col.H2OT_M_WTPC] = out["H2O_melt"]
    #    CO2_melt is wt% → ppm (× 10 000)
    if "CO2_melt" in out.columns:
        out[col.CO2T_M_PPMW] = out["CO2_melt"] * 10_000.0
    #    Stot_melt is wt% → ppm (× 10 000)
    if "Stot_melt" in out.columns:
        out[col.ST_M_PPMW] = out["Stot_melt"] * 10_000.0

    # 5. Sulfur speciation ratio: S6+ / Stotal
    if "S6+_melt" in out.columns and "Stot_melt" in out.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            out[col.S6ST_M] = np.where(
                out["Stot_melt"] > 0,
                out["S6+_melt"] / out["Stot_melt"],
                np.nan,
            )

    # 6. Fe speciation via EVo's Kress & Carmichael (1991) model
    if "Fe3FeT" in out.columns:
        # Newer EVo versions output Fe3FeT directly
        out.rename(columns={"Fe3FeT": col.FE3FET_M}, inplace=True)
    elif composition is not None and T_K is not None and "fo2" in out.columns:
        try:
            from evo.ferric import kc91_fo2

            mol = _wt_to_molfrac(composition)
            fe3fet_vals = np.empty(len(out))
            for idx, (_, row) in enumerate(out.iterrows()):
                P_pa = row[col.P_BARS] * 1e5       # bar → Pa
                lnfo2 = np.log(row["fo2"])          # natural log
                F = kc91_fo2(mol, T_K, P_pa, lnfo2)  # Fe2O3/FeO mole ratio
                fe3fet_vals[idx] = 2.0 * F / (1.0 + 2.0 * F)
            out[col.FE3FET_M] = fe3fet_vals
        except ImportError:
            out[col.FE3FET_M] = np.nan
    else:
        out[col.FE3FET_M] = np.nan

    # 7. OCS — EVo does not model OCS
    if col.OCS_V_MF not in out.columns:
        out[col.OCS_V_MF] = 0.0

    # 8. C/S vapor mole-fraction ratio
    if (all(c in out.columns for c in col.C_SPECIES) and
            all(s in out.columns for s in col.S_SPECIES)):
        c_sum = out[col.C_SPECIES].sum(axis=1)
        s_sum = out[col.S_SPECIES].sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[col.CS_V_MF] = np.where(s_sum > 0, c_sum / s_sum, np.nan)

    return out
