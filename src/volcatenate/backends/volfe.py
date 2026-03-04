"""VolFe backend — C-O-H-S-Fe degassing model.

Wraps the VolFe library (https://github.com/eryhughes/VolFe).
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

import numpy as np
import pandas as pd

from volcatenate.log import logger

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.volfe_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


@contextlib.contextmanager
def _quiet_volfe():
    """Suppress VolFe's tqdm progress bars and stdout, increase recursion limit.

    VolFe uses ``tqdm.tqdm`` for pressure-step progress (writes to stderr)
    and its degassing solver can exceed Python's default 1000-recursion limit
    on compositions with many pressure steps.
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    old_tqdm = os.environ.get("TQDM_DISABLE")
    old_limit = sys.getrecursionlimit()
    os.environ["TQDM_DISABLE"] = "1"
    sys.setrecursionlimit(max(old_limit, 10_000))
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            yield
    finally:
        if old_tqdm is None:
            os.environ.pop("TQDM_DISABLE", None)
        else:
            os.environ["TQDM_DISABLE"] = old_tqdm
        sys.setrecursionlimit(old_limit)
    for buf in (buf_out, buf_err):
        captured = buf.getvalue()
        if captured.strip():
            for line in captured.strip().splitlines():
                logger.debug("[VolFe] %s", line)


class Backend(ModelBackend):

    @property
    def name(self) -> str:
        return "VolFe"

    def is_available(self) -> bool:
        try:
            import VolFe  # noqa: F401
            return True
        except ImportError:
            return False

    # ----------------------------------------------------------------
    # Saturation pressure
    # ----------------------------------------------------------------
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> float:
        import VolFe as vf

        cfg = config.volfe
        setup_df = _build_setup_df(comp, cfg)
        models_df = _build_models_df(cfg)

        try:
            with _quiet_volfe():
                result = vf.calc_Pvsat(setup_df, models=models_df)
            # Result is a DataFrame; extract pressure from first row
            if "P_bar" in result.columns:
                return float(result["P_bar"].iloc[0])
            elif "P_bars" in result.columns:
                return float(result["P_bars"].iloc[0])
            # Fall back to first numeric column that looks like pressure
            for col_name in result.columns:
                if "p" in col_name.lower() and "bar" in col_name.lower():
                    return float(result[col_name].iloc[0])
            return np.nan
        except Exception as exc:
            logger.warning("[VolFe] satP failed for %s: %s", comp.sample, exc)
            return np.nan

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        import VolFe as vf

        cfg = config.volfe
        setup_df = _build_setup_df(comp, cfg)
        models_df = _build_models_df(cfg)

        with _quiet_volfe():
            result = vf.calc_gassing(setup_df, models=models_df, suppress_warnings=True)

        # Standardize output
        result = convert(result)
        result = compute_cs_v_mf(result)
        result = normalize_volatiles(result)
        result = ensure_standard_columns(result)

        return result


# ── Helpers ─────────────────────────────────────────────────────────

def _build_setup_df(comp: MeltComposition, cfg) -> pd.DataFrame:
    """Build the VolFe input DataFrame from a MeltComposition."""
    setup_dict = {
        "Sample": [comp.sample],
        "T_C": [comp.T_C],
        "SiO2": [comp.SiO2],
        "TiO2": [comp.TiO2],
        "Al2O3": [comp.Al2O3],
        "FeOT": [comp.FeOT],
        "MnO": [comp.MnO],
        "MgO": [comp.MgO],
        "CaO": [comp.CaO],
        "Na2O": [comp.Na2O],
        "K2O": [comp.K2O],
        "P2O5": [comp.P2O5],
        "H2O": [comp.H2O],                      # wt%
        "CO2ppm": [comp.CO2 * 10_000],           # wt% → ppm
        "STppm": [comp.S * 10_000],              # wt% → ppm
        "Xppm": [comp.Xppm],
    }

    # Add fO2 column based on config preference
    fo2_col = cfg.fo2_column
    if fo2_col == "DNNO" and comp.dNNO is not None:
        setup_dict["DNNO"] = [comp.dNNO]
    elif fo2_col == "Fe3FeT":
        fe3fet = comp.fe3fet_computed
        if not np.isnan(fe3fet):
            setup_dict["Fe3FeT"] = [fe3fet]
        elif comp.dNNO is not None:
            setup_dict["DNNO"] = [comp.dNNO]
        elif comp.dFMQ is not None:
            setup_dict["DFMQ"] = [comp.dFMQ]
    elif fo2_col == "DFMQ" and comp.dFMQ is not None:
        setup_dict["DFMQ"] = [comp.dFMQ]
    else:
        # Fallback chain
        fe3fet = comp.fe3fet_computed
        if not np.isnan(fe3fet):
            setup_dict["Fe3FeT"] = [fe3fet]
        elif comp.dNNO is not None:
            setup_dict["DNNO"] = [comp.dNNO]
        elif comp.dFMQ is not None:
            setup_dict["DFMQ"] = [comp.dFMQ]

    return pd.DataFrame(setup_dict)


def _build_models_df(cfg):
    """Build the VolFe model-options DataFrame."""
    import VolFe as vf

    model_opts = [
        ["sulfur_saturation", str(cfg.sulfur_saturation)],
        ["graphite_saturation", str(cfg.graphite_saturation)],
        ["output csv", "False"],
        ["print status", "False"],
        ["gassing_style", cfg.gassing_style],
    ]
    return vf.make_df_and_add_model_defaults(model_opts)
