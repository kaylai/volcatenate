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

    return out
