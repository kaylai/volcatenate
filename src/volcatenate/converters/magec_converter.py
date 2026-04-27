"""Convert raw MAGEC output (xlsx or CSV) to the standardized column format.

MAGEC (Sun & Yao, 2024) produces Excel files with columns like:

* ``P_degas (kbar)``         — pressure in kilobars
* ``Mass (wt%)``             — total vapor mass fraction (wt%)
* ``H2O (ppm)``              — dissolved H2O in melt (ppm)
* ``CO2T_m_ppmw``            — dissolved CO2 in melt (ppm, already standard)
* ``S_T (ppm)``              — total dissolved S in melt (ppm)
* ``Fe3+/FeT_degas``         — melt Fe3+/FeT at each degassing step
* ``logfO2_degas``           — log10(fO2) at each step
* ``d_QFM_degas``            — delta-FMQ at each step
* ``S6+/S_T``                — sulfur speciation ratio
* Vapor species as ``H2O (mol%)``, ``CO2 (mol%)``, etc.

The already-converted MAGEC files from the Sulfur Comparison Paper use
the standard column names directly (P_bars, H2OT_m_wtpc, etc.).  This
converter handles both.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


# ── Flexible column mapping ─────────────────────────────────────────
# raw MAGEC name candidates → standardized name
# The first match wins.

_P_CANDIDATES = ["P_degas (kbar)", "P (kbar)", "P_kbar"]
_VAPOR_WT_CANDIDATES = ["Mass (wt%)", "Gas_wt", "Vapor_wt"]

# Direct renames for the already-converted files (identity mapping)
# plus any known raw → standard mappings
_RENAME: dict[str, str] = {
    # Already standard names (no-op but harmless)
    col.P_BARS: col.P_BARS,
    col.H2OT_M_WTPC: col.H2OT_M_WTPC,
    col.CO2T_M_PPMW: col.CO2T_M_PPMW,
    col.ST_M_PPMW: col.ST_M_PPMW,
    col.FE3FET_M: col.FE3FET_M,
    col.S6ST_M: col.S6ST_M,
    col.LOGFO2: col.LOGFO2,
    col.DFMQ: col.DFMQ,
    col.VAPOR_WT: col.VAPOR_WT,
    # Raw MAGEC names — older solver variants
    "H2O (wt%)": col.H2OT_M_WTPC,
    "CO2 (ppm)": col.CO2T_M_PPMW,
    "S (ppm)": col.ST_M_PPMW,
    "logfO2": col.LOGFO2,
    "fO2_FMQ": col.DFMQ,
    "dFMQ": col.DFMQ,
    "Fe3+/FeT": col.FE3FET_M,
    "Fe3Fet": col.FE3FET_M,
    "S6+/ST": col.S6ST_M,
    "S6St": col.S6ST_M,
    # Raw MAGEC names — current solver (v1b) with _degas/_initial suffixes
    "S_T (ppm)": col.ST_M_PPMW,
    "S6+/S_T": col.S6ST_M,
    "Fe3+/FeT_degas": col.FE3FET_M,
    "logfO2_degas": col.LOGFO2,
    "d_QFM_degas": col.DFMQ,
}

# Vapor mole fraction mappings for raw MAGEC names
_VAPOR_RENAME: dict[str, str] = {
    # X-prefix form (older/alternative MAGEC output)
    "XH2O": col.H2O_V_MF,
    "XH2":  col.H2_V_MF,
    "XO2":  col.O2_V_MF,
    "XCO2": col.CO2_V_MF,
    "XCO":  col.CO_V_MF,
    "XCH4": col.CH4_V_MF,
    "XSO2": col.SO2_V_MF,
    "XH2S": col.H2S_V_MF,
    "XS2":  col.S2_V_MF,
    "XOCS": col.OCS_V_MF,
    # Already standard names
    col.H2O_V_MF: col.H2O_V_MF,
    col.H2_V_MF:  col.H2_V_MF,
    col.O2_V_MF:  col.O2_V_MF,
    col.CO2_V_MF: col.CO2_V_MF,
    col.CO_V_MF:  col.CO_V_MF,
    col.CH4_V_MF: col.CH4_V_MF,
    col.SO2_V_MF: col.SO2_V_MF,
    col.H2S_V_MF: col.H2S_V_MF,
    col.S2_V_MF:  col.S2_V_MF,
    col.OCS_V_MF: col.OCS_V_MF,
}

# Vapor species in mol% form (current MAGEC v1b output) → standard name.
# Values need to be divided by 100 to convert from mol% to mole fraction.
_VAPOR_MOLPCT: dict[str, str] = {
    "H2O (mol%)": col.H2O_V_MF,
    "H2 (mol%)":  col.H2_V_MF,
    "O2 (mol%)":  col.O2_V_MF,
    "CO2 (mol%)": col.CO2_V_MF,
    "CO (mol%)":  col.CO_V_MF,
    "CH4 (mol%)": col.CH4_V_MF,
    "SO2 (mol%)": col.SO2_V_MF,
    "H2S (mol%)": col.H2S_V_MF,
    "S2 (mol%)":  col.S2_V_MF,
    "COS (mol%)": col.OCS_V_MF,
}


def is_raw(df: pd.DataFrame) -> bool:
    """Return *True* if *df* uses raw MAGEC column names (not yet standardized).

    Checks for ``P_degas (kbar)`` or other non-standard pressure columns.
    """
    if col.P_BARS in df.columns:
        return False  # already standardized
    return any(c in df.columns for c in _P_CANDIDATES)


def convert(df: pd.DataFrame) -> pd.DataFrame:
    """Convert a MAGEC output DataFrame to the standardized column format.

    Handles both raw MAGEC xlsx output and already-converted files.
    For raw output, converts pressure from kbar to bar, H2O from ppm
    to wt%, vapor mol% to mole fractions, and renames columns.

    Parameters
    ----------
    df : pd.DataFrame
        MAGEC output (raw xlsx or already-converted CSV).

    Returns
    -------
    pd.DataFrame
        Copy with standardized column names and derived columns.
    """
    out = df.copy()

    # --- Handle pressure column ---
    if col.P_BARS not in out.columns:
        for candidate in _P_CANDIDATES:
            if candidate in out.columns:
                if "kbar" in candidate.lower():
                    out[col.P_BARS] = out[candidate] * 1000.0
                else:
                    out[col.P_BARS] = out[candidate]
                break

    # --- Handle vapor weight column ---
    if col.VAPOR_WT not in out.columns:
        for candidate in _VAPOR_WT_CANDIDATES:
            if candidate in out.columns:
                # MAGEC gives wt% — convert to fraction (0–1)
                out[col.VAPOR_WT] = out[candidate] / 100.0
                break

    # --- Handle H2O in ppm (MAGEC v1b gives melt H2O in ppm, not wt%) ---
    if col.H2OT_M_WTPC not in out.columns and "H2O (ppm)" in out.columns:
        out[col.H2OT_M_WTPC] = out["H2O (ppm)"] / 10000.0

    # --- Handle vapor species in mol% (MAGEC v1b output) ---
    for molpct_col, std_col in _VAPOR_MOLPCT.items():
        if molpct_col in out.columns and std_col not in out.columns:
            out[std_col] = out[molpct_col] / 100.0

    # --- Rename scalar and volatile columns ---
    rename_map = {}
    for raw_name, std_name in {**_RENAME, **_VAPOR_RENAME}.items():
        if raw_name in out.columns and raw_name != std_name:
            # Don't overwrite a column we already created above
            if std_name not in out.columns:
                rename_map[raw_name] = std_name
    out.rename(columns=rename_map, inplace=True)

    # --- Drop MAGEC section-header columns (non-data noise) ---
    _SECTION_HEADERS = {"Vapor:", "Melt:", "Track phases:", "fugacity:"}
    out.drop(columns=[c for c in _SECTION_HEADERS if c in out.columns],
             inplace=True, errors="ignore")

    # --- Drop non-standard columns (e.g. MAGEC metadata: T_initial, P_initial, etc.) ---
    _keep = set(col.STANDARD_COLUMNS) | {"Run_ID"}
    out.drop(columns=[c for c in out.columns if c not in _keep],
             inplace=True, errors="ignore")

    return out


def read_magec_xlsx(xlsx_path: str) -> pd.DataFrame:
    """Read a MAGEC output xlsx (or CSV fallback) and return a standardized DataFrame.

    Parameters
    ----------
    xlsx_path : str
        Path to the MAGEC output .xlsx file.

    Returns
    -------
    pd.DataFrame
        Standardized DataFrame.
    """
    import os

    try:
        df = pd.read_excel(xlsx_path)
    except Exception:
        csv_path = xlsx_path.replace(".xlsx", ".csv")
        if os.path.isfile(csv_path):
            df = pd.read_csv(csv_path)
        else:
            raise

    return convert(df)


def parse_saturation_pressure(xlsx_path: str) -> float:
    """Read a MAGEC output and return the saturation pressure in bars.

    Scans for the first row where vapor weight > 0.

    Parameters
    ----------
    xlsx_path : str
        Path to the MAGEC output file.

    Returns
    -------
    float
        Saturation pressure in bars, or ``np.nan`` if saturation was
        not reached within the pressure range.
    """
    import os

    try:
        df = pd.read_excel(xlsx_path)
    except Exception:
        csv_path = xlsx_path.replace(".xlsx", ".csv")
        if os.path.isfile(csv_path):
            df = pd.read_csv(csv_path)
        else:
            raise

    # Identify pressure column
    p_col = None
    for candidate in [*_P_CANDIDATES, col.P_BARS, "P (bars)", "P (bar)", "P_bar", "P"]:
        if candidate in df.columns:
            p_col = candidate
            break
    if p_col is None:
        raise KeyError(
            f"No pressure column found in {xlsx_path}. "
            f"Columns: {list(df.columns)}"
        )

    # Identify vapor weight column
    v_col = None
    for candidate in [*_VAPOR_WT_CANDIDATES, col.VAPOR_WT, "gas_wt"]:
        if candidate in df.columns:
            v_col = candidate
            break
    if v_col is None:
        raise KeyError(
            f"No vapor weight column found in {xlsx_path}. "
            f"Columns: {list(df.columns)}"
        )

    # Find saturation pressure: first row where vapor > 0
    saturated = df[df[v_col] > 0]
    if saturated.empty:
        return np.nan

    p_val = float(saturated.iloc[0][p_col])
    if "kbar" in p_col.lower():
        p_val *= 1000.0

    return p_val
