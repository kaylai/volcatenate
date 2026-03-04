"""Convert D-Compress output to the standardized column format.

D-Compress output CSVs are already in the standard column format
(P_bars, H2OT_m_wtpc, CO2T_m_ppmw, etc.).  The only extra column
is ``Validity`` (1 = converged, 0 = solver failure).

This converter is essentially a pass-through with minor cleanup.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* looks like a D-Compress output file.

    D-Compress files already use standard column names and include a
    ``Validity`` column.
    """
    return "Validity" in df.columns and col.P_BARS in df.columns


def convert(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a D-Compress output DataFrame to the standardized format.

    Filters out invalid rows (Validity != 1) and ensures all standard
    columns are present.

    Parameters
    ----------
    df : pd.DataFrame
        D-Compress output.

    Returns
    -------
    pd.DataFrame
        Copy with invalid rows removed and all standard columns present.
    """
    out = df.copy()

    # Filter to valid rows only (where Validity == 1)
    if "Validity" in out.columns:
        out = out[out["Validity"] == 1].copy()
        out.drop(columns=["Validity"], inplace=True)
        out.reset_index(drop=True, inplace=True)

    # Ensure all standard columns exist (fill missing with NaN)
    for c in col.STANDARD_COLUMNS:
        if c not in out.columns:
            out[c] = np.nan

    # Recompute CS_v_mf if species are present but ratio is missing/zero
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
