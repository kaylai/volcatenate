"""Convert SulfurX output to the standardized column format.

SulfurX outputs are *nearly* standard already.  The main differences:

* Pressure may appear as ``P Mpa`` (megapascals) in addition to ``P_bars``
* Some early SulfurX runs may use slightly different column names

This converter normalises these small differences and ensures all
standard columns are present.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* uses SulfurX-specific column names.

    Detects the ``P Mpa`` column as a sign of unconverted output.
    """
    return "P Mpa" in df.columns


def convert(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a SulfurX output DataFrame to the standardized column format.

    Parameters
    ----------
    df : pd.DataFrame
        SulfurX output.

    Returns
    -------
    pd.DataFrame
        Copy with standardized column names and missing columns filled.
    """
    out = df.copy()

    # --- Pressure ---
    # SulfurX may output both "P Mpa" and "P_bars"; ensure P_bars exists
    if col.P_BARS not in out.columns and "P Mpa" in out.columns:
        out[col.P_BARS] = out["P Mpa"] * 10.0   # 1 MPa = 10 bar

    # --- Column renames for any non-standard names ---
    _rename = {
        "P Mpa": "P_Mpa_orig",  # keep original but don't overwrite
    }
    # Only rename columns that actually exist
    rename_actual = {k: v for k, v in _rename.items() if k in out.columns}
    if rename_actual:
        out.rename(columns=rename_actual, inplace=True)

    # --- Ensure missing vapor species columns exist ---
    # SulfurX may not output all 10 vapor species
    for vapor_col in col.VAPOR_MF_COLUMNS:
        if vapor_col not in out.columns:
            out[vapor_col] = np.nan

    # --- CS_v_mf: recompute if species are present but ratio is missing ---
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
