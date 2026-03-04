"""Post-processing utilities for standardized model output.

Includes C/S ratio computation, volatile normalization, and
column completeness checks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


def compute_cs_v_mf(df: pd.DataFrame) -> pd.DataFrame:
    """Compute C/S vapor mole fraction ratio.

    CS_v_mf = (CO2_v_mf + CO_v_mf + CH4_v_mf) /
              (SO2_v_mf + H2S_v_mf + S2_v_mf)

    Sets CS_v_mf = NaN where the sulfur denominator is zero.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain the 6 vapor species columns (C and S groups).

    Returns
    -------
    pd.DataFrame
        Same DataFrame with CS_v_mf column added/overwritten.
    """
    has_c = all(c in df.columns for c in col.C_SPECIES)
    has_s = all(s in df.columns for s in col.S_SPECIES)

    if has_c and has_s:
        c_sum = df[col.C_SPECIES].sum(axis=1)
        s_sum = df[col.S_SPECIES].sum(axis=1)
        df[col.CS_V_MF] = np.where(s_sum > 0, c_sum / s_sum, np.nan)
    elif col.CS_V_MF not in df.columns:
        df[col.CS_V_MF] = np.nan

    return df


def normalize_volatiles(df: pd.DataFrame) -> pd.DataFrame:
    """Add *_norm columns for H2O, CO2, S relative to initial (row 0) values.

    Parameters
    ----------
    df : pd.DataFrame
        Degassing path DataFrame with at least one row.

    Returns
    -------
    pd.DataFrame
        Same DataFrame with _norm columns added.
    """
    pairs = [
        (col.H2OT_M_WTPC, col.H2OT_M_WTPC_NORM),
        (col.CO2T_M_PPMW, col.CO2T_M_PPMW_NORM),
        (col.ST_M_PPMW, col.ST_M_PPMW_NORM),
    ]
    for src, dst in pairs:
        if src in df.columns and len(df) > 0:
            init_val = df[src].iloc[0]
            if init_val != 0 and not np.isnan(init_val):
                df[dst] = df[src] / init_val
            else:
                df[dst] = np.nan

    return df


def ensure_standard_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all standard columns exist, filling missing ones with NaN.

    Parameters
    ----------
    df : pd.DataFrame
        Model output DataFrame (may be missing some columns).

    Returns
    -------
    pd.DataFrame
        DataFrame with all STANDARD_COLUMNS present.
    """
    for c in col.STANDARD_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    return df
