"""Convert SulfurX output to the standardized column format.

SulfurX's raw output from ``results_dic()`` uses columns like:

* ``pressure``          — pressure in megapascals
* ``wS_melt``           — dissolved S in melt (ppm)
* ``wH2O_melt``         — dissolved H2O in melt (wt%)
* ``wCO2_melt``         — dissolved CO2 in melt (ppm)
* ``S6+/ST``            — sulfur speciation ratio
* ``ferric_ratio``      — Fe3+/FeT in melt
* ``fO2``               — log10(fO2)
* ``FMQ``               — log10(fO2) along FMQ buffer
* ``vapor_fraction``    — vapor mass fraction
* ``XH2O_fluid``, ``XCO2_fluid``, ``XSO2_fluid``, ``XH2S_fluid``
                        — vapor mole fractions

This converter normalises these into the standard column names.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


# ── Raw SulfurX column → standard column mapping ──────────────────
_RENAME: dict[str, str] = {
    # Melt volatile concentrations
    "wS_melt":        col.ST_M_PPMW,
    "wH2O_melt":      col.H2OT_M_WTPC,
    "wCO2_melt":      col.CO2T_M_PPMW,
    # Redox
    "S6+/ST":         col.S6ST_M,
    "ferric_ratio":   col.FE3FET_M,
    "fO2":            col.LOGFO2,
    # Vapor
    "vapor_fraction": col.VAPOR_WT,
    "XH2O_fluid":     col.H2O_V_MF,
    "XCO2_fluid":     col.CO2_V_MF,
    "XSO2_fluid":     col.SO2_V_MF,
    "XH2S_fluid":     col.H2S_V_MF,
    # Already-standard names (identity, harmless)
    col.P_BARS:       col.P_BARS,
    col.H2OT_M_WTPC:  col.H2OT_M_WTPC,
    col.CO2T_M_PPMW:  col.CO2T_M_PPMW,
    col.ST_M_PPMW:    col.ST_M_PPMW,
    col.FE3FET_M:     col.FE3FET_M,
    col.S6ST_M:       col.S6ST_M,
    col.LOGFO2:       col.LOGFO2,
    col.DFMQ:         col.DFMQ,
    col.VAPOR_WT:     col.VAPOR_WT,
}


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* uses SulfurX-specific column names.

    Detects the ``pressure`` or ``P Mpa`` column as a sign of
    unconverted output.
    """
    if col.P_BARS in df.columns:
        return False
    return "pressure" in df.columns or "P Mpa" in df.columns


def convert(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a SulfurX output DataFrame to the standardized column format.

    Parameters
    ----------
    df : pd.DataFrame
        SulfurX output (raw from degassing loop or already-converted).

    Returns
    -------
    pd.DataFrame
        Copy with standardized column names and missing columns filled.
    """
    out = df.copy()

    # --- Pressure: raw SulfurX uses "pressure" in MPa ---
    if col.P_BARS not in out.columns:
        if "pressure" in out.columns:
            out[col.P_BARS] = out["pressure"] * 10.0  # MPa → bar
        elif "P Mpa" in out.columns:
            out[col.P_BARS] = out["P Mpa"] * 10.0

    # --- dFMQ: compute from fO2 and FMQ columns if both present ---
    if col.DFMQ not in out.columns:
        if "fO2" in out.columns and "FMQ" in out.columns:
            out[col.DFMQ] = out["fO2"] - out["FMQ"]

    # --- Rename columns ---
    rename_map = {}
    for raw_name, std_name in _RENAME.items():
        if raw_name in out.columns and raw_name != std_name:
            if std_name not in out.columns:
                rename_map[raw_name] = std_name
    out.rename(columns=rename_map, inplace=True)

    # --- Ensure missing vapor species columns exist ---
    for vapor_col in col.VAPOR_MF_COLUMNS:
        if vapor_col not in out.columns:
            out[vapor_col] = np.nan

    return out
