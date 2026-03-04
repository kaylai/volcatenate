"""VESIcal backend — H2O–CO2 degassing model.

Wraps the VESIcal library (https://github.com/kaylai/VESIcal).
VESIcal does not model sulfur, so S-related output columns are NaN.

Supports named variants so that users can request specific VESIcal
solubility models directly (e.g. ``"VESIcal_Iacono"``,
``"VESIcal_Dixon"``) without changing the config file::

    volcatenate.calculate_degassing(comp, models=["VESIcal_Iacono", "VESIcal_Dixon"])
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig
from volcatenate.converters.vesical_converter import convert
from volcatenate.convert import compute_cs_v_mf, normalize_volatiles, ensure_standard_columns


# Display name → VESIcal internal model name
VARIANT_MAP: dict[str, str] = {
    "VESIcal_MS":                   "MagmaSat",
    "VESIcal_Dixon":                "Dixon",
    "VESIcal_Iacono":               "IaconoMarziano",
    "VESIcal_IaconoMarziano":       "IaconoMarziano",
    "VESIcal_Liu":                  "Liu",
    "VESIcal_ShishkinaIdealMixing": "ShishkinaIdealMixing",
}


class Backend(ModelBackend):

    def __init__(self, variant: str | None = None) -> None:
        # variant is the VESIcal internal model name (e.g. "IaconoMarziano")
        # or None to use the config default.
        self._variant = variant
        if variant is None:
            self._name = "VESIcal"
        else:
            # Find the canonical short display name
            for display, internal in VARIANT_MAP.items():
                if internal == variant:
                    self._name = display
                    break
            else:
                self._name = f"VESIcal_{variant}"

    @property
    def name(self) -> str:
        return self._name

    def is_available(self) -> bool:
        try:
            import VESIcal  # noqa: F401
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
        import VESIcal as v

        sample_dict = _build_sample_dict(comp)
        sample = v.Sample(sample_dict)
        model_name = self._variant or config.vesical.model
        model = v.models.default_models[model_name]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                result = model.calculate_saturation_pressure(
                    sample=sample,
                    temperature=comp.T_C,
                )
                # VESIcal returns a dict with 'SaturationPressure_bars'
                if isinstance(result, dict):
                    return float(result.get("SaturationPressure_bars", np.nan))
                # Or a DataFrame / scalar depending on version
                return float(result)
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
        import VESIcal as v

        cfg = config.vesical
        model_name = self._variant or cfg.model
        sample_dict = _build_sample_dict(comp)
        sample = v.Sample(sample_dict)
        model = v.models.default_models[model_name]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = model.calculate_degassing_path(
                sample=sample,
                temperature=comp.T_C,
                pressure="saturation",
                fractionate_vapor=cfg.fractionate_vapor,
                final_pressure=cfg.final_pressure,
                steps=cfg.steps,
            )

        # Standardize output
        df = convert(df, model_variant=model_name)
        df = compute_cs_v_mf(df)
        df = normalize_volatiles(df)
        df = ensure_standard_columns(df)

        return df


# ── Helpers ─────────────────────────────────────────────────────────

def _build_sample_dict(comp: MeltComposition) -> dict:
    """Build the VESIcal sample dictionary from a MeltComposition."""
    d = {}

    # Major oxides
    for key in ["SiO2", "TiO2", "Al2O3", "MnO", "MgO", "CaO",
                "Na2O", "K2O", "P2O5"]:
        val = getattr(comp, key, 0.0)
        if val > 0:
            d[key] = val

    # VESIcal uses 'FeO' not 'FeOT'
    if comp.FeO is not None and comp.Fe2O3 is not None:
        d["FeO"] = comp.FeO
        d["Fe2O3"] = comp.Fe2O3
    else:
        d["FeO"] = comp.FeOT

    # Volatiles
    d["H2O"] = comp.H2O
    d["CO2"] = comp.CO2

    return d
