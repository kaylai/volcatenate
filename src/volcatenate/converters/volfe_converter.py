"""Convert raw VolFe output CSV to the standardized column format.

VolFe outputs columns like ``P_bar``, ``xgO2_mf``, ``xgCO2_mf``,
``H2OT-eq_wtpc``, ``CO2T-eq_ppmw``, ``ST_ppmw``, ``Fe3+/FeT``,
``fO2_bar``, ``fO2_DFMQ``, ``wt_g_wtpc``, etc.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


# ── Column rename mapping ───────────────────────────────────────────
# Raw VolFe column → Standardized column
_RENAME: dict[str, str] = {
    "P_bar":          col.P_BARS,
    "xgO2_mf":       col.O2_V_MF,
    "xgCO2_mf":      col.CO2_V_MF,
    "xgCO_mf":       col.CO_V_MF,
    "xgH2O_mf":      col.H2O_V_MF,
    "xgH2_mf":       col.H2_V_MF,
    "xgS2_mf":       col.S2_V_MF,
    "xgSO2_mf":      col.SO2_V_MF,
    "xgH2S_mf":      col.H2S_V_MF,
    "xgCH4_mf":      col.CH4_V_MF,
    "xgOCS_mf":      col.OCS_V_MF,
    "xgC_S_mf":      col.CS_V_MF,
    "H2OT-eq_wtpc":  col.H2OT_M_WTPC,
    "CO2T-eq_ppmw":  col.CO2T_M_PPMW,
    "ST_ppmw":        col.ST_M_PPMW,
    "Fe3+/FeT":       col.FE3FET_M,
    "S6+/ST":         col.S6ST_M,
    "fO2_DFMQ":      col.DFMQ,
    "wt_g_wtpc":     col.VAPOR_WT,
}


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* looks like an unconverted VolFe file."""
    return "P_bar" in df.columns and col.P_BARS not in df.columns


def convert(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a raw VolFe DataFrame to the standardized column format.

    Parameters
    ----------
    df : pd.DataFrame
        Raw VolFe output (181-column format from recent VolFe runs).

    Returns
    -------
    pd.DataFrame
        Copy with standardized column names and derived columns.
    """
    out = df.copy()

    # 0. Coerce numeric columns from object → float64.
    #    VolFe uses gmpy2 internally and stores results as Python-native
    #    floats (dtype=object).  numpy ufuncs (log10, etc.) choke on
    #    object-dtype Series, so convert everything numeric up front.
    for c in out.columns:
        if out[c].dtype == object:
            try:
                out[c] = pd.to_numeric(out[c])
            except (ValueError, TypeError):
                pass  # genuinely non-numeric column (e.g. sample names)

    # Defragment after 181-column type coercion; VolFe's internal
    # construction leaves the DataFrame heavily fragmented and any
    # subsequent column insertion triggers PerformanceWarning.
    out = out.copy()

    # 1. Rename columns
    out.rename(columns=_RENAME, inplace=True)

    # 2. Compute logfO2 = log10(fO2) from the raw linear column
    #    fO2 can be 0 at the tail of a degassing path → log10(0) = -inf.
    #    Suppress the numpy warning; rows with 0 get NaN.
    if "fO2_bar" in out.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            vals = np.log10(out["fO2_bar"])
        out[col.LOGFO2] = vals.replace(-np.inf, np.nan)
    elif "fO2" in out.columns:
        with np.errstate(divide="ignore", invalid="ignore"):
            vals = np.log10(out["fO2"])
        out[col.LOGFO2] = vals.replace(-np.inf, np.nan)

    # 3. Recompute CS_v_mf if species are present but ratio is missing/zero
    if (all(c in out.columns for c in col.C_SPECIES) and
            all(s in out.columns for s in col.S_SPECIES)):
        needs_cs = (col.CS_V_MF not in out.columns or
                    (out[col.CS_V_MF] == 0).all() or
                    out[col.CS_V_MF].isna().all())
        if needs_cs:
            c_sum = out[col.C_SPECIES].sum(axis=1)
            s_sum = out[col.S_SPECIES].sum(axis=1)
            with np.errstate(divide="ignore", invalid="ignore"):
                out[col.CS_V_MF] = np.where(s_sum > 0, c_sum / s_sum, np.nan)

    return out
