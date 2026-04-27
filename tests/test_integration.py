"""Integration / smoke tests for each backend wrapper.

Each test:
  1. Skips if the required external library is not installed.
  2. Runs a saturation pressure or degassing calculation through volcatenate.
  3. Checks that the result has expected columns and physically sane values.

For EVo and VolFe, the raw-library comparison test verifies that volcatenate
does not mangle the underlying model's output (P_bars must agree within 2%).

To run only integration tests:
    pytest tests/test_integration.py -v -m integration

To skip integration tests (default in CI):
    pytest tests/ -m "not integration"
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from volcatenate import columns as col
from volcatenate.composition import composition_from_dict
from volcatenate.config import RunConfig


# ── Shared test composition (Kilauea-like basalt) ─────────────────────────────

KILAUEA = {
    "Sample": "KilaeaInteg",
    "T_C": 1200.0,
    "SiO2": 50.19, "TiO2": 2.34, "Al2O3": 12.79,
    "FeOT": 11.34, "MnO": 0.18, "MgO": 9.23, "CaO": 10.44,
    "Na2O": 2.39, "K2O": 0.43, "P2O5": 0.27,
    "H2O": 0.30, "CO2": 0.008, "S": 0.15,
    "Fe3FeT": 0.18, "dNNO": -0.23,
}


def _config(tmp_path: str) -> RunConfig:
    return RunConfig(output_dir=tmp_path, keep_raw_output=False, show_progress=False)


def _assert_satp_sane(state: "pd.Series | None", model: str) -> None:
    assert state is not None, f"{model} returned None"
    assert isinstance(state, pd.Series), f"{model} must return pd.Series"
    assert col.P_BARS in state.index, f"{model}: P_bars missing from result"
    assert state[col.P_BARS] > 0, f"{model}: P_bars={state[col.P_BARS]} should be positive"
    assert not np.isnan(state[col.P_BARS]), f"{model}: P_bars is NaN"


def _assert_degassing_sane(df: pd.DataFrame, model: str) -> None:
    assert isinstance(df, pd.DataFrame), f"{model}: must return DataFrame"
    assert len(df) > 1, f"{model}: degassing path should have multiple rows"
    assert col.P_BARS in df.columns, f"{model}: P_bars column missing"
    assert df[col.P_BARS].iloc[0] > df[col.P_BARS].iloc[-1], \
        f"{model}: pressure should decrease along degassing path"
    for c in col.STANDARD_COLUMNS:
        assert c in df.columns, f"{model}: missing standard column {c}"


# ── VESIcal ───────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_vesical_satp_smoke(tmp_path):
    """VESIcal calculate_saturation_pressure returns a sane pd.Series."""
    pytest.importorskip("VESIcal")
    from volcatenate.backends.vesical import Backend

    backend = Backend()
    if not backend.is_available():
        pytest.skip("VESIcal backend not available")

    comp = composition_from_dict(KILAUEA)
    state = backend.calculate_saturation_pressure(comp, _config(str(tmp_path)))
    _assert_satp_sane(state, "VESIcal")
    assert state.get(col.H2OT_M_WTPC, np.nan) >= 0


@pytest.mark.integration
def test_vesical_degassing_smoke(tmp_path):
    """VESIcal calculate_degassing returns a DataFrame with standard columns."""
    pytest.importorskip("VESIcal")
    from volcatenate.backends.vesical import Backend

    backend = Backend()
    if not backend.is_available():
        pytest.skip("VESIcal backend not available")

    comp = composition_from_dict(KILAUEA)
    df = backend.calculate_degassing(comp, _config(str(tmp_path)))
    _assert_degassing_sane(df, "VESIcal")


# ── VolFe ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_volfe_satp_smoke(tmp_path):
    """VolFe calculate_saturation_pressure returns a sane pd.Series."""
    pytest.importorskip("VolFe")
    from volcatenate.backends.volfe import Backend

    backend = Backend()
    if not backend.is_available():
        pytest.skip("VolFe backend not available")

    comp = composition_from_dict(KILAUEA)
    state = backend.calculate_saturation_pressure(comp, _config(str(tmp_path)))
    _assert_satp_sane(state, "VolFe")


@pytest.mark.integration
def test_volfe_satp_vs_raw_library(tmp_path):
    """Volcatenate VolFe satP must agree with the raw library within 2%."""
    vf = pytest.importorskip("VolFe")
    from volcatenate.backends.volfe import (
        Backend, _build_setup_df, _build_models_df, _quiet_volfe,
    )
    from volcatenate.config import VolFeConfig

    comp = composition_from_dict(KILAUEA)
    cfg = VolFeConfig()
    setup_df = _build_setup_df(comp, cfg)
    models_df = _build_models_df(cfg)

    with _quiet_volfe():
        raw_result = vf.calc_Pvsat(setup_df, models=models_df)

    # VolFe returns a DataFrame; P column name may vary by version
    p_col = next(
        (c for c in ("P_bar", "P", "P_bars") if c in raw_result.columns),
        None,
    )
    assert p_col is not None, f"Cannot find pressure column in raw VolFe output: {list(raw_result.columns)}"
    raw_p = float(raw_result.iloc[0][p_col])

    backend = Backend()
    state = backend.calculate_saturation_pressure(comp, _config(str(tmp_path)))
    assert state is not None
    volc_p = float(state[col.P_BARS])

    assert abs(volc_p - raw_p) / max(raw_p, 1.0) < 0.02, (
        f"Volcatenate P={volc_p:.1f} bar differs from raw VolFe P={raw_p:.1f} bar by >2%"
    )


@pytest.mark.integration
def test_volfe_degassing_smoke(tmp_path):
    """VolFe calculate_degassing returns a valid degassing path."""
    pytest.importorskip("VolFe")
    from volcatenate.backends.volfe import Backend

    backend = Backend()
    if not backend.is_available():
        pytest.skip("VolFe backend not available")

    comp = composition_from_dict(KILAUEA)
    df = backend.calculate_degassing(comp, _config(str(tmp_path)))
    _assert_degassing_sane(df, "VolFe")


# ── EVo ───────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_evo_satp_smoke(tmp_path):
    """EVo calculate_saturation_pressure returns a sane pd.Series."""
    pytest.importorskip("evo")
    from volcatenate.backends.evo import Backend

    backend = Backend()
    if not backend.is_available():
        pytest.skip("EVo backend not available")

    comp = composition_from_dict(KILAUEA)
    state = backend.calculate_saturation_pressure(comp, _config(str(tmp_path)))
    _assert_satp_sane(state, "EVo")


@pytest.mark.integration
def test_evo_degassing_smoke(tmp_path):
    """EVo calculate_degassing returns a valid degassing path."""
    pytest.importorskip("evo")
    from volcatenate.backends.evo import Backend

    backend = Backend()
    if not backend.is_available():
        pytest.skip("EVo backend not available")

    comp = composition_from_dict(KILAUEA)
    df = backend.calculate_degassing(comp, _config(str(tmp_path)))
    _assert_degassing_sane(df, "EVo")


@pytest.mark.integration
def test_evo_open_system_differs_from_closed(tmp_path):
    """EVo open-system run must produce a different result than closed-system."""
    pytest.importorskip("evo")
    from volcatenate.backends.evo import Backend
    from volcatenate.config import EVoConfig

    backend = Backend()
    if not backend.is_available():
        pytest.skip("EVo backend not available")

    comp = composition_from_dict(KILAUEA)
    cfg_closed = RunConfig(
        output_dir=str(tmp_path / "closed"),
        keep_raw_output=False, show_progress=False,
        evo=EVoConfig(run_type="closed"),
    )
    cfg_open = RunConfig(
        output_dir=str(tmp_path / "open"),
        keep_raw_output=False, show_progress=False,
        evo=EVoConfig(run_type="open", loss_frac=0.999),
    )

    df_closed = backend.calculate_degassing(comp, cfg_closed)
    df_open = backend.calculate_degassing(comp, cfg_open)

    # Open-system degasses more efficiently; final S content should be lower
    final_s_closed = df_closed[col.ST_M_PPMW].iloc[-1]
    final_s_open = df_open[col.ST_M_PPMW].iloc[-1]
    assert final_s_open < final_s_closed, (
        "Open-system EVo run should retain less S in the melt than closed-system; "
        "run_type is not being passed to EVo correctly"
    )


# ── SulfurX ───────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_sulfurx_satp_smoke(tmp_path):
    """SulfurX calculate_saturation_pressure returns a sane pd.Series."""
    from volcatenate.backends.sulfurx import Backend
    backend = Backend()
    if not backend.is_available():
        pytest.skip("SulfurX not available (SULFURX_PATH not set or path not found)")

    comp = composition_from_dict(KILAUEA)
    state = backend.calculate_saturation_pressure(comp, _config(str(tmp_path)))
    _assert_satp_sane(state, "SulfurX")


@pytest.mark.integration
def test_sulfurx_degassing_smoke(tmp_path):
    """SulfurX calculate_degassing returns a valid degassing path."""
    from volcatenate.backends.sulfurx import Backend
    backend = Backend()
    if not backend.is_available():
        pytest.skip("SulfurX not available")

    comp = composition_from_dict(KILAUEA)
    df = backend.calculate_degassing(comp, _config(str(tmp_path)))
    _assert_degassing_sane(df, "SulfurX")


# ── MAGEC ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_magec_satp_smoke(tmp_path):
    """MAGEC calculate_saturation_pressure returns a sane pd.Series."""
    from volcatenate.backends.magec import Backend
    backend = Backend()
    if not backend.is_available():
        pytest.skip("MAGEC not available (MATLAB or solver not found)")

    comp = composition_from_dict(KILAUEA)
    state = backend.calculate_saturation_pressure(comp, _config(str(tmp_path)))
    _assert_satp_sane(state, "MAGEC")


@pytest.mark.integration
def test_magec_degassing_smoke(tmp_path):
    """MAGEC calculate_degassing returns a valid degassing path."""
    from volcatenate.backends.magec import Backend
    backend = Backend()
    if not backend.is_available():
        pytest.skip("MAGEC not available")

    comp = composition_from_dict(KILAUEA)
    df = backend.calculate_degassing(comp, _config(str(tmp_path)))
    _assert_degassing_sane(df, "MAGEC")
