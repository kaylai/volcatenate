from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_add_trace_to_subplot_p_norm_zero_p_init():
    """add_trace_to_subplot must not raise when P_bars.iloc[0] == 0."""
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots
    from volcatenate.plotting import add_trace_to_subplot

    fig = make_subplots(rows=1, cols=1)
    data = pd.DataFrame(
        {
            "P_bars": [0.0, 100.0, 200.0],
            "H2OT_m_wtpc": [0.30, 0.25, 0.20],
        }
    )
    # Should not raise ZeroDivisionError
    add_trace_to_subplot(
        fig,
        data,
        "TestModel",
        "H2Om",
        l_c="blue",
        l_w=2,
        l_d="solid",
        row=1,
        col=1,
        p_norm=True,
    )
    # Falls back to absolute pressure — trace should still be added
    assert len(fig.data) == 1


def test_add_trace_to_subplot_p_norm_nan_p_init():
    """add_trace_to_subplot must not produce all-NaN x-axis when P_bars.iloc[0] is NaN."""
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots
    from volcatenate.plotting import add_trace_to_subplot

    fig = make_subplots(rows=1, cols=1)
    data = pd.DataFrame(
        {
            "P_bars": [np.nan, 100.0, 200.0],
            "H2OT_m_wtpc": [0.30, 0.25, 0.20],
        }
    )
    add_trace_to_subplot(
        fig,
        data,
        "TestModel",
        "H2Om",
        l_c="blue",
        l_w=2,
        l_d="solid",
        row=1,
        col=1,
        p_norm=True,
    )
    assert len(fig.data) == 1


def test_add_trace_to_subplot_p_norm_normal():
    """add_trace_to_subplot with valid P_bars.iloc[0] must normalize correctly."""
    pytest.importorskip("plotly")
    from plotly.subplots import make_subplots
    from volcatenate.plotting import add_trace_to_subplot

    fig = make_subplots(rows=1, cols=1)
    data = pd.DataFrame(
        {
            "P_bars": [1000.0, 500.0, 100.0],
            "H2OT_m_wtpc": [0.30, 0.25, 0.10],
        }
    )
    add_trace_to_subplot(
        fig,
        data,
        "TestModel",
        "H2Om",
        l_c="blue",
        l_w=2,
        l_d="solid",
        row=1,
        col=1,
        p_norm=True,
    )
    assert len(fig.data) == 1
    # x values should be [1.0, 0.5, 0.1]
    x = fig.data[0].x
    assert float(x[0]) == pytest.approx(1.0)
    assert float(x[1]) == pytest.approx(0.5)
