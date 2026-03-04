"""Convert VESIcal output to the standardized column format.

VESIcal outputs are mostly in standard form already, but the column
names vary by solubility model:

* ``MagmaSat`` (MS) uses ``XH2O_fl`` / ``XCO2_fl`` for fluid fractions
* Other models (Dixon, Iacono, Liu, Shishkina) use ``H2O_v_mf`` /
  ``CO2_v_mf`` directly

VESIcal is an H2O–CO2 model and does not track sulfur species,
so all S-related columns are filled with NaN.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


# Columns already in standard form (no rename needed)
_STANDARD_PRESENT = {col.P_BARS, col.H2OT_M_WTPC, col.CO2T_M_PPMW, col.VAPOR_WT}


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* uses VESIcal-specific column names.

    Detects the ``XCO2_fl`` / ``XH2O_fl`` naming used by MagmaSat
    output, which needs conversion.  Files with standard ``H2O_v_mf``
    / ``CO2_v_mf`` names are considered already-converted.
    """
    return "XCO2_fl" in df.columns or "XH2O_fl" in df.columns


def convert(df: pd.DataFrame, model_variant: str = "") -> pd.DataFrame:
    """Convert a VESIcal output DataFrame to the standardized column format.

    Parameters
    ----------
    df : pd.DataFrame
        VESIcal output (any solubility model variant).
    model_variant : str, optional
        The VESIcal model name (e.g. ``"VESIcal_MS"``).  Not currently
        used for logic but reserved for future per-model handling.

    Returns
    -------
    pd.DataFrame
        Copy with standardized column names and missing columns filled.
    """
    out = df.copy()

    # --- Map fluid mole fractions ---
    # MagmaSat uses XCO2_fl / XH2O_fl; other models may already have
    # H2O_v_mf / CO2_v_mf.
    if "XCO2_fl" in out.columns:
        out[col.CO2_V_MF] = out["XCO2_fl"]
    if "XH2O_fl" in out.columns:
        out[col.H2O_V_MF] = out["XH2O_fl"]

    # --- Fill sulfur-related columns with NaN ---
    # VESIcal is an H2O–CO2 model; sulfur is not modeled
    out[col.ST_M_PPMW] = np.nan

    # --- Fill missing vapor mole fraction columns ---
    # VESIcal only outputs H2O and CO2 vapor fractions
    for vapor_col in col.VAPOR_MF_COLUMNS:
        if vapor_col not in out.columns:
            out[vapor_col] = np.nan

    # --- Fill missing redox / derived columns ---
    for missing_col in [col.FE3FET_M, col.S6ST_M, col.LOGFO2, col.DFMQ]:
        if missing_col not in out.columns:
            out[missing_col] = np.nan

    # --- CS_v_mf is undefined for VESIcal (no S species) ---
    out[col.CS_V_MF] = np.nan

    return out
