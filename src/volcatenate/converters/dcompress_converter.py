"""Convert D-Compress output to the standardized column format.

D-Compress output CSVs are already in the standard column format
(P_bars, H2OT_m_wtpc, CO2T_m_ppmw, etc.).  The only extra column
is ``Validity`` (1 = converged, 0 = solver failure on a given step).

This converter is essentially a pass-through: it drops the
``Validity`` column and ensures the full standard schema is present.
All rows are preserved — including ``Validity == 0`` rows that may
still carry a meaningful ``P_bars`` (e.g. the initial saturation
pressure at the top of a decompression path, where the solver hasn't
found a stable vapor phase yet).  Filtering those out would discard
the true initial pressure and shift downstream ``max(P_bars)``
summaries.  Per volcatenate's wrapper-fidelity policy, that decision
belongs to the consumer, not to the wrapper.
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

    Drops the ``Validity`` column and ensures every standard column is
    present (missing ones filled with NaN).  Rows are not filtered.

    Parameters
    ----------
    df : pd.DataFrame
        D-Compress output.

    Returns
    -------
    pd.DataFrame
        Copy with ``Validity`` removed and all standard columns present.
    """
    out = df.copy()

    if "Validity" in out.columns:
        out.drop(columns=["Validity"], inplace=True)

    out.reset_index(drop=True, inplace=True)

    for c in col.STANDARD_COLUMNS:
        if c not in out.columns:
            out[c] = np.nan

    return out
