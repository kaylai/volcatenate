"""Black-box tests for the MAGEC converter pipeline."""

import numpy as np
import pandas as pd

from volcatenate import columns as col
from volcatenate.converters.magec_converter import convert

_METADATA_COLS = [
    "T_initial (C)",
    "P_initial (kbar)",
    "logfO2_initial",
    "d_IW_initial",
    "d_QFM_initial",
    "d_NNO_initial",
]


def _make_raw_magec_df(n_rows: int = 5) -> pd.DataFrame:
    data: dict[str, object] = {
        "P_degas (kbar)": np.linspace(2.0, 0.5, n_rows),
        "Mass (wt%)": np.linspace(0.0, 5.0, n_rows),
        "H2O (ppm)": np.linspace(40000, 30000, n_rows),
        "CO2T_m_ppmw": np.linspace(1000, 100, n_rows),
        "S_T (ppm)": np.linspace(2000, 1500, n_rows),
        "Fe3+/FeT_degas": np.full(n_rows, 0.2),
        "logfO2_degas": np.full(n_rows, -10.0),
        "d_QFM_degas": np.full(n_rows, 0.5),
        "S6+/S_T": np.full(n_rows, 0.3),
    }
    for meta in _METADATA_COLS:
        data[meta] = [1200.0] + [np.nan] * (n_rows - 1)
    return pd.DataFrame(data)


def test_metadata_columns_not_leaking():
    """Metadata _initial columns must not appear in converted output."""
    raw = _make_raw_magec_df()
    result = convert(raw)
    leaked = [c for c in _METADATA_COLS if c in result.columns]
    assert leaked == [], f"Metadata columns leaked into output: {leaked}"


def test_run_id_preserved():
    """Run_ID must survive conversion (used for batch splitting)."""
    raw = _make_raw_magec_df()
    raw["Run_ID"] = [f"sample_A_{i+1}" for i in range(len(raw))]
    result = convert(raw)
    assert "Run_ID" in result.columns


def test_standard_columns_present():
    """Standard columns that have data must be present after conversion."""
    raw = _make_raw_magec_df()
    result = convert(raw)
    assert col.P_BARS in result.columns
    assert col.ST_M_PPMW in result.columns
    assert col.VAPOR_WT in result.columns
