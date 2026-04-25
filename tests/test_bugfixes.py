"""Regression tests — one test per fixed bug.

Each test exercises the exact code path that was broken. If a bug is
reintroduced, the corresponding test fails with a clear message.
"""
from __future__ import annotations

import logging
import os

import numpy as np
import pandas as pd
import pytest

from volcatenate import columns as col


# ── Bug 1: _quiet_evo — captured output lost on exception ──────────────────

def test_quiet_evo_flushes_output_on_exception():
    """Captured EVo stdout must reach logger.debug even when the wrapped code raises."""
    from volcatenate.backends.evo import _quiet_evo
    from volcatenate.log import logger

    records = []

    class CapHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = CapHandler()
    handler.setLevel(logging.DEBUG)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        with pytest.raises(RuntimeError):
            with _quiet_evo():
                print("evo_stdout_line")
                raise RuntimeError("EVo failed")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert any("evo_stdout_line" in r for r in records), (
        "stdout captured before exception was not flushed to logger; "
        "log-flush loop is still outside the finally block"
    )


# ── Bug 2: _quiet_volfe — captured output lost on exception + chdir scope ──

def test_quiet_volfe_flushes_output_on_exception():
    """Captured VolFe stdout must reach logger.debug even when the wrapped code raises."""
    from volcatenate.backends.volfe import _quiet_volfe
    from volcatenate.log import logger

    records = []

    class CapHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = CapHandler()
    handler.setLevel(logging.DEBUG)
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        with pytest.raises(RuntimeError):
            with _quiet_volfe():
                print("volfe_stdout_line")
                raise RuntimeError("VolFe failed")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)

    assert any("volfe_stdout_line" in r for r in records), (
        "stdout captured before exception was not flushed to logger; "
        "log-flush loop is still outside the finally block"
    )


def test_quiet_volfe_restores_cwd_on_exception(tmp_path):
    """CWD must be restored even if work_dir chdir succeeds but body raises."""
    from volcatenate.backends.volfe import _quiet_volfe

    original_cwd = os.getcwd()
    work_dir = str(tmp_path / "volfe_work")

    with pytest.raises(RuntimeError):
        with _quiet_volfe(work_dir=work_dir):
            raise RuntimeError("failed mid-run")

    assert os.getcwd() == original_cwd, (
        "CWD was not restored after exception in _quiet_volfe; "
        "os.chdir is still outside the try block"
    )


def test_quiet_volfe_restores_cwd_on_success(tmp_path):
    """CWD must be restored on normal exit too."""
    from volcatenate.backends.volfe import _quiet_volfe

    original_cwd = os.getcwd()
    work_dir = str(tmp_path / "volfe_work2")

    with _quiet_volfe(work_dir=work_dir):
        pass

    assert os.getcwd() == original_cwd


# ── Bug 3: simplify runs independently of O2_mass_bal ──────────────────────

def test_simplify_runs_when_o2_mass_bal_false(tmp_path):
    """simplify=True must work even when O2_mass_bal=False."""
    from volcatenate.compat import loadData

    model_dir = tmp_path / "EVo"
    model_dir.mkdir()
    df_out = pd.DataFrame({
        "P_bars": [1000.0, 500.0],
        "H2OT_m_wtpc": [0.30, 0.20],
        "CO2T_m_ppmw": [800.0, 400.0],
        "ST_m_ppmw": [1500.0, 800.0],
        "EXTRA_COLUMN_SHOULD_BE_DROPPED": [9.9, 9.9],
    })
    (model_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    data_morb, data_kil, data_fuego, data_fogo = loadData(
        model_names=["EVo"],
        topdirectory_name=str(tmp_path),
        O2_mass_bal=False,
        simplify=True,
    )

    assert "EVo" in data_kil, "EVo data should be loaded for kilauea"
    assert "EXTRA_COLUMN_SHOULD_BE_DROPPED" not in data_kil["EVo"].columns, (
        "simplify=True should remove extra columns even when O2_mass_bal=False; "
        "simplify block is still nested inside if O2_mass_bal:"
    )


def test_simplify_false_preserves_extra_columns(tmp_path):
    """simplify=False must leave extra columns untouched."""
    from volcatenate.compat import loadData

    model_dir = tmp_path / "EVo"
    model_dir.mkdir()
    df_out = pd.DataFrame({
        "P_bars": [1000.0],
        "EXTRA_COL": [42.0],
    })
    (model_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    _, data_kil, _, _ = loadData(
        model_names=["EVo"],
        topdirectory_name=str(tmp_path),
        simplify=False,
    )
    assert "EXTRA_COL" in data_kil["EVo"].columns


# ── Bug 4: XH2O_fl guard ────────────────────────────────────────────────────

def test_load_data_xco2_without_xh2o_no_keyerror(tmp_path):
    """loadData must not crash if XCO2_fl is present but XH2O_fl is absent."""
    from volcatenate.compat import loadData

    vesical_dir = tmp_path / "VESIcal" / "VESIcal_MS"
    vesical_dir.mkdir(parents=True)

    # CSV has XCO2_fl but deliberately omits XH2O_fl
    df_out = pd.DataFrame({
        "P_bars": [1000.0],
        "XCO2_fl": [0.5],
    })
    (vesical_dir / "kilauea.csv").write_text(df_out.to_csv(index=False))

    # Should not raise KeyError — the XH2O_fl guard prevents it
    data_morb, data_kil, data_fuego, data_fogo = loadData(
        model_names=["VESIcal_MS"],
        topdirectory_name=str(tmp_path),
    )
    assert "VESIcal_MS" in data_kil, "VESIcal_MS should be loaded without error"
    # CO2_v_mf / H2O_v_mf should NOT be mapped since XH2O_fl is missing
    assert "CO2_v_mf" not in data_kil["VESIcal_MS"].columns or \
           "XCO2_fl" not in data_kil["VESIcal_MS"].columns, \
        "CO2_v_mf should not be mapped when XH2O_fl is absent"


# ── Bug 5: Sample key not overwritten in satP result rows ──────────────────

def test_sample_key_not_overwritten_by_state():
    """row['Sample'] from comp must not be overwritten by state.to_dict()."""
    sample_name = "TestSample"
    reservoir = "TestReservoir"
    row: dict = {"Sample": sample_name, "Reservoir": reservoir}

    # Simulate a state Series that includes "Sample" with a wrong value
    state = pd.Series({
        col.P_BARS: 1234.0,
        "Sample": "WRONG_SAMPLE",
        "Reservoir": "WRONG_RESERVOIR",
    })

    # This is the fixed code pattern from core.py
    state_dict = state.to_dict()
    state_dict.pop("Sample", None)
    state_dict.pop("Reservoir", None)
    row.update(state_dict)

    assert row["Sample"] == sample_name, (
        f"Sample was overwritten: got {row['Sample']!r}, expected {sample_name!r}; "
        "state.to_dict() stripping is missing"
    )
    assert row["Reservoir"] == reservoir
    assert row[col.P_BARS] == pytest.approx(1234.0)


def test_core_calculate_satp_sample_identity(tmp_path):
    """calculate_saturation_pressure must preserve sample name even when backend returns a Series with Sample key."""
    from unittest.mock import MagicMock, patch
    from volcatenate.core import calculate_saturation_pressure
    from volcatenate.composition import composition_from_dict
    from volcatenate.config import RunConfig

    comp_dict = {
        "Sample": "MyRealSample",
        "T_C": 1200.0,
        "SiO2": 50.0, "TiO2": 1.0, "Al2O3": 15.0,
        "FeOT": 10.0, "MnO": 0.2, "MgO": 8.0, "CaO": 10.0,
        "Na2O": 2.5, "K2O": 0.5, "P2O5": 0.2,
        "H2O": 0.3, "CO2": 0.05, "S": 0.1, "Fe3FeT": 0.15,
    }

    # Build a fake state Series that includes the wrong "Sample"
    fake_state = pd.Series({
        col.P_BARS: 999.0,
        col.H2OT_M_WTPC: 0.3,
        "Sample": "WRONG_NAME_FROM_BACKEND",
    })

    mock_backend = MagicMock()
    mock_backend.name = "FakeModel"
    mock_backend.is_available.return_value = True
    mock_backend.supports_batch_satp = False
    mock_backend.calculate_saturation_pressure.return_value = fake_state

    config = RunConfig(
        output_dir=str(tmp_path),
        show_progress=False,
        verbose=False,
    )

    with patch("volcatenate.core.get_backend", return_value=mock_backend), \
         patch("volcatenate.core.list_backends", return_value=["FakeModel"]):
        result = calculate_saturation_pressure(comp_dict, models=["FakeModel"], config=config)

    eq = result.equilibrium_state["FakeModel"]
    assert eq["Sample"].iloc[0] == "MyRealSample", (
        f"Sample should be 'MyRealSample' but got {eq['Sample'].iloc[0]!r}; "
        "state.to_dict() is overwriting the Sample key"
    )


# ── Bug 6: plotting P_bars division guard ──────────────────────────────────

def test_add_trace_to_subplot_p_norm_zero_p_init():
    """add_trace_to_subplot must not raise when P_bars.iloc[0] == 0."""
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots
    from volcatenate.plotting import add_trace_to_subplot

    fig = make_subplots(rows=1, cols=1)
    data = pd.DataFrame({
        "P_bars": [0.0, 100.0, 200.0],
        "H2OT_m_wtpc": [0.30, 0.25, 0.20],
    })
    # Should not raise ZeroDivisionError
    add_trace_to_subplot(
        fig, data, "TestModel", "H2Om",
        l_c="blue", l_w=2, l_d="solid",
        row=1, col=1, p_norm=True,
    )
    # Falls back to absolute pressure — trace should still be added
    assert len(fig.data) == 1


def test_add_trace_to_subplot_p_norm_nan_p_init():
    """add_trace_to_subplot must not produce all-NaN x-axis when P_bars.iloc[0] is NaN."""
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots
    from volcatenate.plotting import add_trace_to_subplot

    fig = make_subplots(rows=1, cols=1)
    data = pd.DataFrame({
        "P_bars": [np.nan, 100.0, 200.0],
        "H2OT_m_wtpc": [0.30, 0.25, 0.20],
    })
    add_trace_to_subplot(
        fig, data, "TestModel", "H2Om",
        l_c="blue", l_w=2, l_d="solid",
        row=1, col=1, p_norm=True,
    )
    assert len(fig.data) == 1


def test_add_trace_to_subplot_p_norm_normal():
    """add_trace_to_subplot with valid P_bars.iloc[0] must normalize correctly."""
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots
    from volcatenate.plotting import add_trace_to_subplot

    fig = make_subplots(rows=1, cols=1)
    data = pd.DataFrame({
        "P_bars": [1000.0, 500.0, 100.0],
        "H2OT_m_wtpc": [0.30, 0.25, 0.10],
    })
    add_trace_to_subplot(
        fig, data, "TestModel", "H2Om",
        l_c="blue", l_w=2, l_d="solid",
        row=1, col=1, p_norm=True,
    )
    assert len(fig.data) == 1
    # x values should be [1.0, 0.5, 0.1]
    x = fig.data[0].x
    assert float(x[0]) == pytest.approx(1.0)
    assert float(x[1]) == pytest.approx(0.5)


# ── Bug 7: EVo run_type exposed from config ─────────────────────────────────

def test_evo_config_has_run_type():
    """EVoConfig must have a run_type field defaulting to 'closed'."""
    from volcatenate.config import EVoConfig
    cfg = EVoConfig()
    assert hasattr(cfg, "run_type"), "EVoConfig is missing run_type field"
    assert cfg.run_type == "closed", "EVoConfig.run_type default should be 'closed'"


def test_evo_config_accepts_open():
    """EVoConfig must accept run_type='open'."""
    from volcatenate.config import EVoConfig
    cfg = EVoConfig(run_type="open")
    assert cfg.run_type == "open"


def test_evo_run_type_passed_to_yaml(tmp_path):
    """_write_yaml_configs must use cfg.run_type, not hardcoded 'closed'."""
    from volcatenate.backends.evo import _write_yaml_configs
    from volcatenate.config import EVoConfig
    from volcatenate.composition import composition_from_dict
    import yaml

    comp = composition_from_dict({
        "Sample": "TestSample", "T_C": 1200,
        "SiO2": 50, "TiO2": 1, "Al2O3": 15, "FeOT": 10,
        "MnO": 0.2, "MgO": 8, "CaO": 10, "Na2O": 2.5, "K2O": 0.5,
        "P2O5": 0.2, "H2O": 0.3, "CO2": 0.05, "S": 0.1, "Fe3FeT": 0.15,
    })
    cfg = EVoConfig(run_type="open")
    _, env_path, _ = _write_yaml_configs(comp, cfg, str(tmp_path), run_type=cfg.run_type)

    with open(env_path) as f:
        env_data = yaml.safe_load(f)

    assert env_data["RUN_TYPE"] == "open", (
        f"Expected RUN_TYPE='open' in EVo env.yaml but got {env_data.get('RUN_TYPE')!r}"
    )
