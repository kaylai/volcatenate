"""Post-processing utilities for standardized model output.

Includes C/S ratio computation, volatile normalization, and
column completeness checks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


def compute_cs_v_mf(df: pd.DataFrame) -> pd.DataFrame:
    """Compute elemental C/S ratio in the vapor phase.

    Uses stoichiometric coefficients from :data:`columns.C_SPECIES` and
    :data:`columns.S_SPECIES` to count carbon and sulfur **atoms**::

        C/S = (1·X_CO₂ + 1·X_CO + 1·X_CH₄ + 1·X_OCS)
            / (1·X_SO₂ + 1·X_H₂S + 2·X_S₂ + 1·X_OCS)

    Species columns missing from *df* or containing NaN are treated as
    zero.  Sets ``CS_v_mf = NaN`` where the sulfur denominator is zero.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain at least some of the vapor species columns
        (gas-phase mole fractions).

    Returns
    -------
    pd.DataFrame
        Same DataFrame with ``CS_v_mf`` column added or overwritten.
    """
    c_cols = {c: coeff for c, coeff in col.C_SPECIES.items() if c in df.columns}
    s_cols = {s: coeff for s, coeff in col.S_SPECIES.items() if s in df.columns}

    if c_cols and s_cols:
        c_sum = sum(df[c].fillna(0.0) * coeff for c, coeff in c_cols.items())
        s_sum = sum(df[s].fillna(0.0) * coeff for s, coeff in s_cols.items())
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
    # Collect new columns in a dict and add all at once to avoid
    # DataFrame fragmentation (PerformanceWarning on repeated insert).
    new_cols: dict[str, pd.Series | float] = {}
    for src, dst in pairs:
        if src in df.columns and len(df) > 0:
            init_val = df[src].iloc[0]
            if init_val != 0 and not np.isnan(init_val):
                new_cols[dst] = df[src] / init_val
            else:
                new_cols[dst] = np.nan

    if new_cols:
        df = pd.concat(
            [df, pd.DataFrame(new_cols, index=df.index)],
            axis=1,
        )

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
    missing = [c for c in col.STANDARD_COLUMNS if c not in df.columns]
    if missing:
        # Add all missing columns at once to avoid DataFrame fragmentation
        # (repeated df[c] = val triggers PerformanceWarning).
        df = pd.concat(
            [df, pd.DataFrame({c: np.nan for c in missing}, index=df.index)],
            axis=1,
        )
    return df
