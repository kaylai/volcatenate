"""Convert VESIcal output to the standardized column format.

VESIcal's ``calculate_degassing_path()`` returns columns in VESIcal's
own naming convention:

* ``Pressure_bars`` — pressure in bars
* ``H2O_liq`` — dissolved H₂O in wt%
* ``CO2_liq`` — dissolved CO₂ in **wt%** (must be converted to ppm)
* ``FluidProportion_wt`` — exsolved fluid weight fraction
* ``H2O_fl`` / ``CO2_fl`` — fluid mole fractions (most models)
* ``XH2O_fl`` / ``XCO2_fl`` — fluid mole fractions (MagmaSat)

VESIcal is an H₂O–CO₂ model and does not track sulfur species,
so all S-related columns are filled with NaN.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


# ── Column rename mapping ───────────────────────────────────────────
# Raw VESIcal column → Standardized column
_RENAME: dict[str, str] = {
    "Pressure_bars":      col.P_BARS,
    "H2O_liq":            col.H2OT_M_WTPC,       # already wt%
    "FluidProportion_wt": col.VAPOR_WT,           # already weight fraction
}


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* uses VESIcal-specific column names.

    Detects columns like ``Pressure_bars``, ``H2O_liq``, ``CO2_liq``
    that come from VESIcal's native output.  Files already using
    volcatenate standard names (``P_bars``, ``H2OT_m_wtpc``) are
    considered already-converted.
    """
    vesical_markers = {"Pressure_bars", "H2O_liq", "CO2_liq"}
    return bool(vesical_markers & set(df.columns))


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

    # --- Rename VESIcal columns to standard names ---
    out.rename(columns=_RENAME, inplace=True)

    # --- CO2: VESIcal outputs wt% → convert to ppm ---
    if "CO2_liq" in out.columns:
        out[col.CO2T_M_PPMW] = out["CO2_liq"] * 10_000.0

    # --- Map fluid mole fractions ---
    # MagmaSat uses XCO2_fl / XH2O_fl; other models use CO2_fl / H2O_fl.
    if "XCO2_fl" in out.columns:
        out[col.CO2_V_MF] = out["XCO2_fl"]
    elif "CO2_fl" in out.columns:
        out[col.CO2_V_MF] = out["CO2_fl"]

    if "XH2O_fl" in out.columns:
        out[col.H2O_V_MF] = out["XH2O_fl"]
    elif "H2O_fl" in out.columns:
        out[col.H2O_V_MF] = out["H2O_fl"]

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
