"""Monte Carlo behavior tests for the SulfurX backend.

Tests run against the SulfurX version recorded in
``volcatenate.versions.TESTED_SULFURX_VERSION``, materialized via the
``sulfurx_tested_path`` session fixture in ``tests/conftest.py`` —
NOT against whatever the developer's local SulfurX checkout has
progressed to. Skips cleanly if SulfurX is not installed locally or if
the tested-version tag is missing from the local checkout.

- File-shape contract: when ``monte_carlo=1`` the wrapper writes
  ``<sample>_montecarlo_S.csv`` and ``_CS.csv`` with the expected columns.
- Silent-when-off contract: ``monte_carlo=0`` produces no MC files.
- Failure-mode checks:
    * Per-iteration columns must actually differ (proves ``monte_c=1``
      is wired through and PartitionCoefficient is sampling).
    * Enabling MC must not pollute the deterministic ``df_results``
      returned to the caller.

Config-shape tests (does the field exist, accept the right type, load
from YAML) live in ``test_sulfurx_config.py`` — no SulfurX needed
there.
"""
from __future__ import annotations

import pandas as pd
import pytest

from volcatenate.backends.sulfurx import Backend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig


def _basalt_sample(name: str) -> MeltComposition:
    """Standard MORB-like fixture used by every test below."""
    return MeltComposition(
        sample=name,
        SiO2=50.0, TiO2=1.5, Al2O3=15.0, FeOT=10.0, MnO=0.2, MgO=8.0,
        CaO=11.0, Na2O=2.5, K2O=0.3, P2O5=0.2,
        T_C=1200.0, H2O=2.0, CO2=0.05, S=0.15, dFMQ=0.0,
    )


def _smoke_config(tmp_path, sulfurx_path: str, *,
                  monte_carlo: int, n_iter: int) -> RunConfig:
    """Tiny config: 10 steps, 4 MC iterations → runs in a few seconds.

    Sets ``use_tested_version=False`` so the wrapper honors the
    fixture's worktree path instead of materializing its own.  The
    fixture is the source of truth for the tested-version source in
    these tests.
    """
    config = RunConfig()
    config.output_dir = str(tmp_path)
    config.sulfurx.path = sulfurx_path
    config.sulfurx.use_tested_version = False
    config.sulfurx.n_steps = 10
    config.sulfurx.monte_carlo = monte_carlo
    config.sulfurx.monte_carlo_n_iter = n_iter
    return config


def test_monte_carlo_writes_expected_csvs(tmp_path, sulfurx_tested_path):
    """File-shape contract: monte_carlo=1 produces both summary CSVs
    with columns ``pressure, 0, 1, ..., N-1, mean, std, variance``.
    """
    comp = _basalt_sample("MC_Smoke")
    config = _smoke_config(tmp_path, sulfurx_tested_path,
                           monte_carlo=1, n_iter=4)

    Backend().calculate_degassing(comp, config)

    s_csv = tmp_path / "SulfurX" / "MC_Smoke_montecarlo_S.csv"
    cs_csv = tmp_path / "SulfurX" / "MC_Smoke_montecarlo_CS.csv"
    assert s_csv.exists(), f"Expected {s_csv} to be written"
    assert cs_csv.exists(), f"Expected {cs_csv} to be written"

    s_df = pd.read_csv(s_csv)
    expected_cols = ["pressure", "0", "1", "2", "3", "mean", "std", "variance"]
    assert list(s_df.columns) == expected_cols, (
        f"Got columns {list(s_df.columns)}"
    )


def test_monte_carlo_off_writes_no_csvs(tmp_path, sulfurx_tested_path):
    """Silent-when-off contract: monte_carlo=0 produces no MC files."""
    comp = _basalt_sample("MC_Off")
    config = _smoke_config(tmp_path, sulfurx_tested_path,
                           monte_carlo=0, n_iter=0)

    Backend().calculate_degassing(comp, config)

    s_csv = tmp_path / "SulfurX" / "MC_Off_montecarlo_S.csv"
    cs_csv = tmp_path / "SulfurX" / "MC_Off_montecarlo_CS.csv"
    assert not s_csv.exists(), f"{s_csv} should not exist when monte_carlo=0"
    assert not cs_csv.exists(), f"{cs_csv} should not exist when monte_carlo=0"


def test_monte_carlo_iterations_actually_differ(tmp_path, sulfurx_tested_path):
    """Failure-mode check: per-iteration columns must differ.

    If monte_c were silently wired to 0, every iteration would hit the
    same Kd values and produce identical columns.  Asserting that the
    summed across-iteration std is positive catches that class of bug
    without claiming anything about the magnitude of the variation.
    """
    comp = _basalt_sample("MC_Diff")
    config = _smoke_config(tmp_path, sulfurx_tested_path,
                           monte_carlo=1, n_iter=4)

    Backend().calculate_degassing(comp, config)

    s_df = pd.read_csv(tmp_path / "SulfurX" / "MC_Diff_montecarlo_S.csv")
    iter_cols = ["0", "1", "2", "3"]
    cross_iter_std = s_df[iter_cols].std(axis=1).sum()
    assert cross_iter_std > 0, (
        "All MC iterations produced identical wS_melt columns — "
        "monte_c=1 may not be reaching PartitionCoefficient."
    )


def test_monte_carlo_does_not_pollute_deterministic_output(
    tmp_path, sulfurx_tested_path,
):
    """Failure-mode check: enabling MC must not change ``df_results``.

    Run the same config twice (MC off, then MC on) and assert the
    returned deterministic DataFrame is identical.  A copy-paste bug
    where the MC loop overwrites ``df_results`` rows would silently
    corrupt the main output, and only this test would catch it.
    """
    comp_off = _basalt_sample("MC_Iso_Off")
    comp_on = _basalt_sample("MC_Iso_On")

    df_off = Backend().calculate_degassing(
        comp_off,
        _smoke_config(tmp_path, sulfurx_tested_path,
                      monte_carlo=0, n_iter=0),
    )
    df_on = Backend().calculate_degassing(
        comp_on,
        _smoke_config(tmp_path, sulfurx_tested_path,
                      monte_carlo=1, n_iter=4),
    )

    pd.testing.assert_frame_equal(
        df_off.reset_index(drop=True),
        df_on.reset_index(drop=True),
        check_exact=False,            # SulfurX has tiny step-by-step rounding noise
        rtol=1e-9, atol=1e-12,
    )
