"""SulfurX backend — sulfur-bearing COH degassing model.

Wraps the SulfurX code (Iacono-Marziano / VolatileCalc COH models
with sulfur speciation).  SulfurX is not pip-installable, so its
path must be provided via ``config.sulfurx.path``.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.sulfurx_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


class Backend(ModelBackend):

    @property
    def name(self) -> str:
        return "SulfurX"

    def is_available(self) -> bool:
        # SulfurX requires a local path — we can't test without config
        return True  # Always register; will fail with clear error if path is wrong

    def _ensure_on_path(self, config: RunConfig) -> None:
        """Add SulfurX to sys.path if not already present."""
        sx_path = config.sulfurx.path
        if not sx_path:
            raise FileNotFoundError(
                "SulfurX path not configured. "
                "Set config.sulfurx.path to the SulfurX source directory."
            )
        if not os.path.isdir(sx_path):
            raise FileNotFoundError(
                f"SulfurX directory not found at '{sx_path}'."
            )
        if sx_path not in sys.path:
            sys.path.insert(0, sx_path)

    # ----------------------------------------------------------------
    # Saturation pressure
    # ----------------------------------------------------------------
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> float:
        self._ensure_on_path(config)
        cfg = config.sulfurx

        tk = comp.T_C + 273.15
        h2o_wt = comp.H2O
        co2_ppm = comp.CO2 * 10_000  # wt% → ppm

        # Oxide composition dict
        composition = {
            "SiO2": comp.SiO2, "TiO2": comp.TiO2, "Al2O3": comp.Al2O3,
            "FeOT": comp.FeOT, "MnO": comp.MnO, "MgO": comp.MgO,
            "CaO": comp.CaO, "Na2O": comp.Na2O, "K2O": comp.K2O,
            "P2O5": comp.P2O5,
        }

        try:
            if cfg.coh_model == 0:  # Iacono-Marziano
                from Iacono_Marziano_COH import IaconoMarziano

                rough_p_mpa = max(10, h2o_wt * 30 + co2_ppm * 0.05)
                coh = IaconoMarziano(
                    pressure=rough_p_mpa,
                    temperature_k=tk,
                    composition=composition,
                    a=cfg.slope_h2o,
                    b=cfg.constant_h2o,
                )
                P_sat, _XH2O_f = coh.saturation_pressure(co2_ppm, h2o_wt)
                return float(P_sat)
            else:  # VolatileCalc
                from VC_COH import VolatileCalc

                vc = VolatileCalc(
                    TK=tk,
                    sio2=composition["SiO2"],
                    a=cfg.slope_h2o,
                    b=cfg.constant_h2o,
                )
                result = vc.SatPress(WtH2O=h2o_wt, PPMCO2=co2_ppm)
                return float(result[0])
        except Exception:
            return np.nan

    # ----------------------------------------------------------------
    # Degassing path
    # ----------------------------------------------------------------
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        self._ensure_on_path(config)
        cfg = config.sulfurx

        tk = comp.T_C + 273.15
        h2o_wt = comp.H2O
        co2_ppm = comp.CO2 * 10_000
        s_ppm = comp.S * 10_000

        composition = {
            "SiO2": comp.SiO2, "TiO2": comp.TiO2, "Al2O3": comp.Al2O3,
            "FeOT": comp.FeOT, "MnO": comp.MnO, "MgO": comp.MgO,
            "CaO": comp.CaO, "Na2O": comp.Na2O, "K2O": comp.K2O,
            "P2O5": comp.P2O5,
        }

        fe3fet = comp.fe3fet_computed

        if cfg.coh_model == 0:
            from Iacono_Marziano_COH import IaconoMarziano
            from SulfurX_main import run_degassing as sx_run

            # SulfurX degassing: requires saturation pressure first
            rough_p_mpa = max(10, h2o_wt * 30 + co2_ppm * 0.05)
            coh = IaconoMarziano(
                pressure=rough_p_mpa,
                temperature_k=tk,
                composition=composition,
                a=cfg.slope_h2o,
                b=cfg.constant_h2o,
            )

            df = sx_run(
                temperature_k=tk,
                composition=composition,
                h2o_wt=h2o_wt,
                co2_ppm=co2_ppm,
                s_ppm=s_ppm,
                fe3fet=fe3fet if not np.isnan(fe3fet) else None,
                coh_model=coh,
                slope=cfg.slope_h2o,
                constant=cfg.constant_h2o,
            )
        else:
            raise NotImplementedError(
                "SulfurX degassing with VolatileCalc COH model "
                "is not yet implemented in volcatenate."
            )

        # Standardize
        df = convert(df)
        df = compute_cs_v_mf(df)
        df = normalize_volatiles(df)
        df = ensure_standard_columns(df)

        return df
