"""VolFe backend — C-O-H-S-Fe degassing model.

Wraps the VolFe library (https://github.com/eryhughes/VolFe).
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import sys

import numpy as np
import pandas as pd

from volcatenate.log import logger

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig, resolve_sample_config
from volcatenate.converters.volfe_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


@contextlib.contextmanager
def _quiet_volfe(work_dir: str | None = None):
    """Suppress VolFe's tqdm progress bars and stdout, increase recursion limit.

    VolFe uses ``tqdm.tqdm`` for pressure-step progress (writes to stderr)
    and its degassing solver can exceed Python's default 1000-recursion limit
    on compositions with many pressure steps.

    VolFe's ``jac_newton3()`` writes debug CSV files
    (``results_jacnewton2.csv``, ``results_jacnewton3.csv``) to the CWD.
    If *work_dir* is provided, the CWD is temporarily changed so these
    files land there instead of cluttering the user's project directory.
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    old_tqdm = os.environ.get("TQDM_DISABLE")
    old_limit = sys.getrecursionlimit()
    old_cwd = os.getcwd()
    os.environ["TQDM_DISABLE"] = "1"
    sys.setrecursionlimit(max(old_limit, 10_000))
    try:
        if work_dir:
            os.makedirs(work_dir, exist_ok=True)
            os.chdir(work_dir)
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            yield
    finally:
        os.chdir(old_cwd)
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
    ) -> pd.Series | None:
        import VolFe as vf

        cfg = resolve_sample_config(config.volfe, comp.sample)
        setup_df = _build_setup_df(comp, cfg)
        models_df = _build_models_df(cfg)
        work_dir = os.path.join(config.output_dir, config.raw_output_dir, f"{comp.sample}_volfe_satp")

        try:
            with _quiet_volfe(work_dir):
                result = vf.calc_Pvsat(setup_df, models=models_df)

            # Run through the same converter pipeline as degassing
            result = convert(result)
            result = compute_cs_v_mf(result)
            # Skip normalize_volatiles — meaningless for a single point
            result = ensure_standard_columns(result)

            if len(result) == 0:
                return None

            state = result.iloc[0].copy()
        except Exception as exc:
            logger.warning("[VolFe] satP failed for %s: %s", comp.sample, exc)
            return None

        if not config.keep_raw_output:
            shutil.rmtree(work_dir, ignore_errors=True)

        return state

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        import VolFe as vf

        cfg = resolve_sample_config(config.volfe, comp.sample)
        setup_df = _build_setup_df(comp, cfg)
        models_df = _build_models_df(cfg)
        work_dir = os.path.join(config.output_dir, config.raw_output_dir, f"{comp.sample}_volfe_degas")

        with _quiet_volfe(work_dir):
            result = vf.calc_gassing(setup_df, models=models_df, suppress_warnings=True)

        # Standardize output
        result = convert(result)
        result = compute_cs_v_mf(result)
        result = normalize_volatiles(result)
        result = ensure_standard_columns(result)

        if not config.keep_raw_output:
            shutil.rmtree(work_dir, ignore_errors=True)

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

    redox_col, redox_val = _resolve_volfe_redox(comp, cfg)
    setup_dict[redox_col] = [redox_val]

    return pd.DataFrame(setup_dict)


def _resolve_volfe_redox(comp: MeltComposition, cfg) -> tuple[str, float]:
    """Pick the VolFe redox column + value from the sample.

    Returns a (column_name, value) pair where ``column_name`` is one of
    ``"DNNO"``, ``"Fe3FeT"``, ``"DFMQ"`` (matching VolFe's setup_df
    column names exactly).

    Behavior is controlled by :class:`~volcatenate.config.VolFeConfig.fo2_source`:

    - ``"auto"`` (default): try the column requested by ``fo2_column``
      first, then fall back through Fe3+/FeT → dNNO → dFMQ. Logs the
      choice at INFO so the user can see what actually got used.
    - ``"fe3fet"`` / ``"dnno"`` / ``"dfmq"``: require that exact source
      on the comp; raises ``ValueError`` if missing.

    Raises ``ValueError`` if no usable redox indicator is available.
    """
    fe3fet = comp.fe3fet_computed
    src = cfg.fo2_source

    # Strict mode — user demanded a specific column.
    if src == "fe3fet":
        if np.isnan(fe3fet):
            raise ValueError(
                f"[VolFe] fo2_source='fe3fet' requires Fe3+/FeT on sample "
                f"{comp.sample!r}, but none was provided."
            )
        return "Fe3FeT", float(fe3fet)
    if src == "dnno":
        if comp.dNNO is None:
            raise ValueError(
                f"[VolFe] fo2_source='dnno' requires dNNO on sample "
                f"{comp.sample!r}, but it is missing."
            )
        return "DNNO", float(comp.dNNO)
    if src == "dfmq":
        if comp.dFMQ is None:
            raise ValueError(
                f"[VolFe] fo2_source='dfmq' requires dFMQ on sample "
                f"{comp.sample!r}, but it is missing."
            )
        return "DFMQ", float(comp.dFMQ)

    # Auto mode — try the requested column, then fall back.
    fo2_col = cfg.fo2_column
    if fo2_col == "DNNO" and comp.dNNO is not None:
        logger.info("[VolFe] %s: redox=DNNO (%.3f)", comp.sample, comp.dNNO)
        return "DNNO", float(comp.dNNO)
    if fo2_col == "DFMQ" and comp.dFMQ is not None:
        logger.info("[VolFe] %s: redox=DFMQ (%.3f)", comp.sample, comp.dFMQ)
        return "DFMQ", float(comp.dFMQ)
    if fo2_col == "Fe3FeT" and not np.isnan(fe3fet):
        logger.info("[VolFe] %s: redox=Fe3FeT (%.4f)", comp.sample, fe3fet)
        return "Fe3FeT", float(fe3fet)

    # Fallback chain when the requested column is missing.
    if not np.isnan(fe3fet):
        logger.info(
            "[VolFe] %s: fo2_column=%s missing on comp; falling back to Fe3FeT (%.4f)",
            comp.sample, fo2_col, fe3fet,
        )
        return "Fe3FeT", float(fe3fet)
    if comp.dNNO is not None:
        logger.info(
            "[VolFe] %s: fo2_column=%s missing on comp; falling back to DNNO (%.3f)",
            comp.sample, fo2_col, comp.dNNO,
        )
        return "DNNO", float(comp.dNNO)
    if comp.dFMQ is not None:
        logger.info(
            "[VolFe] %s: fo2_column=%s missing on comp; falling back to DFMQ (%.3f)",
            comp.sample, fo2_col, comp.dFMQ,
        )
        return "DFMQ", float(comp.dFMQ)

    raise ValueError(
        f"[VolFe] No usable redox indicator on sample {comp.sample!r}. "
        f"Need one of: Fe3+/FeT (or speciated FeO+Fe2O3), dNNO, dFMQ."
    )


def _build_models_df(cfg):
    """Build the VolFe model-options DataFrame.

    Maps volcatenate's VolFeConfig fields to the exact option names
    that VolFe expects.  Options not listed here (volcatenate-managed
    or VolFe-internal) are left to VolFe's built-in defaults via
    ``make_df_and_add_model_defaults``.
    """
    import VolFe as vf

    model_opts = [
        # ── Saturation ──
        ["sulfur_saturation", str(cfg.sulfur_saturation)],
        ["sulfur_is_sat", cfg.sulfur_is_sat],
        ["graphite_saturation", str(cfg.graphite_saturation)],
        ["SCSS", cfg.scss],
        ["SCAS", cfg.scas],

        # ── Degassing geometry ──
        ["gassing_style", cfg.gassing_style],
        ["gassing_direction", cfg.gassing_direction],
        ["bulk_composition", cfg.bulk_composition],
        ["starting_P", cfg.starting_p],
        ["P_variation", cfg.p_variation],
        ["T_variation", cfg.t_variation],
        ["crystallisation", cfg.crystallisation],

        # ── Iron / oxygen redox ──
        ["eq_Fe", cfg.eq_fe],
        ["bulk_O", cfg.bulk_o],
        ["calc_sat", cfg.calc_sat],

        # ── Species ──
        ["COH_species", cfg.coh_species],
        ["H2S_m", str(cfg.h2s_melt)],
        ["species X", cfg.species_x],
        ["Hspeciation", cfg.h_speciation],

        # ── Oxygen fugacity ──
        ["fO2", cfg.fo2_model],
        ["FMQbuffer", cfg.fmq_buffer],
        ["NNObuffer", cfg.nno_buffer],

        # ── Bulk physical model ──
        ["density", cfg.density],
        ["melt composition", cfg.melt_composition],

        # ── Solubility constants ──
        ["carbon dioxide", cfg.co2_sol],
        ["water", cfg.h2o_sol],
        ["hydrogen", cfg.h2_sol],
        ["sulfide", cfg.sulfide_sol],
        ["sulfate", cfg.sulfate_sol],
        ["hydrogen sulfide", cfg.h2s_sol],
        ["methane", cfg.ch4_sol],
        ["carbon monoxide", cfg.co_sol],
        ["species X solubility", cfg.x_sol],
        ["Cspeccomp", cfg.c_spec_comp],
        ["Hspeccomp", cfg.h_spec_comp],

        # ── Fugacity coefficients ──
        ["ideal_gas", str(cfg.ideal_gas)],
        ["y_CO2", cfg.y_co2],
        ["y_SO2", cfg.y_so2],
        ["y_H2S", cfg.y_h2s],
        ["y_H2", cfg.y_h2],
        ["y_O2", cfg.y_o2],
        ["y_S2", cfg.y_s2],
        ["y_CO", cfg.y_co],
        ["y_CH4", cfg.y_ch4],
        ["y_H2O", cfg.y_h2o],
        ["y_OCS", cfg.y_ocs],
        ["y_X", cfg.y_x],

        # ── Equilibrium constants ──
        ["KHOg", cfg.k_hog],
        ["KHOSg", cfg.k_hosg],
        ["KOSg", cfg.k_osg],
        ["KOSg2", cfg.k_osg2],
        ["KCOg", cfg.k_cog],
        ["KCOHg", cfg.k_cohg],
        ["KOCSg", cfg.k_ocsg],
        ["KCOs", cfg.k_cos],
        ["carbonylsulfide", cfg.carbonylsulfide],

        # ── Isotopes ──
        ["isotopes", cfg.isotopes],
        ["beta_factors", cfg.beta_factors],
        ["alpha_H_CH4v_CH4m", cfg.alpha_h_ch4v_ch4m],
        ["alpha_H_H2v_H2m", cfg.alpha_h_h2v_h2m],
        ["alpha_H_H2Ov_OHmm", cfg.alpha_h_h2ov_ohmm],
        ["alpha_H_H2Ov_H2Om", cfg.alpha_h_h2ov_h2om],
        ["alpha_H_H2Sv_H2Sm", cfg.alpha_h_h2sv_h2sm],
        ["alpha_C_CH4v_CH4m", cfg.alpha_c_ch4v_ch4m],
        ["alpha_C_COv_COm", cfg.alpha_c_cov_com],
        ["alpha_C_CO2v_CO2T", cfg.alpha_c_co2v_co2t],
        ["alpha_C_CO2v_CO2m", cfg.alpha_c_co2v_co2m],
        ["alpha_C_CO2v_CO32mm", cfg.alpha_c_co2v_co32mm],
        ["alpha_S_H2Sv_H2Sm", cfg.alpha_s_h2sv_h2sm],
        ["alpha_SO2_SO4", cfg.alpha_so2_so4],
        ["alpha_H2S_S", cfg.alpha_h2s_s],

        # ── Numerical / runtime ──
        ["error", cfg.error],
        ["high precision", str(cfg.high_precision)],

        # ── Volcatenate-managed (not configurable) ──
        ["output csv", "False"],
        ["print status", "False"],
    ]
    return vf.make_df_and_add_model_defaults(model_opts)
