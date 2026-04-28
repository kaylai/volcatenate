"""Melt composition data model and CSV reader."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from volcatenate.iron import fe3fet_from_speciated, feot_from_speciated


@dataclass
class MeltComposition:
    """A single melt inclusion / sample composition.

    All oxide and volatile values are in wt%.
    """

    sample: str
    T_C: float

    # Major oxides (wt%)
    SiO2: float = 0.0
    TiO2: float = 0.0
    Al2O3: float = 0.0
    Cr2O3: float = 0.0     # only used by MAGEC; default 0
    FeOT: float = 0.0      # total iron as FeO
    MnO: float = 0.0
    MgO: float = 0.0
    CaO: float = 0.0
    Na2O: float = 0.0
    K2O: float = 0.0
    P2O5: float = 0.0

    # Volatiles (wt%)
    H2O: float = 0.0
    CO2: float = 0.0
    S: float = 0.0

    # Nitrogen (ppm — petrological convention; concentrations are
    # typically too low for wt% to be a natural unit). Currently
    # consumed only by EVo when ``EVoConfig.nitrogen_set`` is True.
    N_ppm: float = 0.0

    # Speciated iron (optional; FeOT is used if these are absent)
    FeO: Optional[float] = None
    Fe2O3: Optional[float] = None

    # Redox indicators (optional)
    Fe3FeT: Optional[float] = None
    dNNO: Optional[float] = None
    dFMQ: Optional[float] = None

    # Other
    Xppm: float = 0.0
    reservoir: str = ""

    @property
    def fe3fet_computed(self) -> float:
        """Fe3+/FeT: from speciated iron, explicit value, or NaN."""
        if self.FeO is not None and self.Fe2O3 is not None:
            val = fe3fet_from_speciated(self.FeO, self.Fe2O3)
            if not np.isnan(val):
                return val
        if self.Fe3FeT is not None:
            return self.Fe3FeT
        return np.nan

    @property
    def oxide_dict(self) -> dict[str, float]:
        """Return major oxides as a dict (excluding volatiles and iron speciation)."""
        return {
            "SiO2": self.SiO2,
            "TiO2": self.TiO2,
            "Al2O3": self.Al2O3,
            "Cr2O3": self.Cr2O3,
            "FeOT": self.FeOT,
            "MnO": self.MnO,
            "MgO": self.MgO,
            "CaO": self.CaO,
            "Na2O": self.Na2O,
            "K2O": self.K2O,
            "P2O5": self.P2O5,
        }

    def to_dict(self) -> dict:
        """Full composition as a flat dict."""
        d = {
            "Sample": self.sample,
            "T_C": self.T_C,
            **self.oxide_dict,
            "H2O": self.H2O,
            "CO2": self.CO2,
            "S": self.S,
        }
        if self.Fe3FeT is not None:
            d["Fe3FeT"] = self.Fe3FeT
        if self.dNNO is not None:
            d["dNNO"] = self.dNNO
        if self.dFMQ is not None:
            d["dFMQ"] = self.dFMQ
        if self.FeO is not None:
            d["FeO"] = self.FeO
        if self.Fe2O3 is not None:
            d["Fe2O3"] = self.Fe2O3
        return d


# ---------------------------------------------------------------------------
# CSV Reader
# ---------------------------------------------------------------------------

# Mapping of alternative CSV column names → canonical field names
_COLUMN_ALIASES: dict[str, str] = {
    "Label": "sample",
    "Sample": "sample",
    "sample": "sample",
    "T_C": "T_C",
    "Temp": "T_C",
    "Temperature": "T_C",
    "Reservoir": "reservoir",
    # Oxides
    "SiO2": "SiO2",
    "TiO2": "TiO2",
    "Al2O3": "Al2O3",
    "Cr2O3": "Cr2O3",
    "MnO": "MnO",
    "MgO": "MgO",
    "CaO": "CaO",
    "Na2O": "Na2O",
    "K2O": "K2O",
    "P2O5": "P2O5",
    # Iron variants
    "FeOT": "FeOT",
    "FeO*": "FeOT",
    "_feototal_": "FeOT",
    "FeO": "_FeO_speciated",
    "_feo_": "_FeO_speciated",
    "Fe2O3": "_Fe2O3_speciated",
    "_fe2o3_": "_Fe2O3_speciated",
    # Volatiles
    "H2O": "H2O",
    "CO2": "CO2",
    "S": "S",
    # Nitrogen — accept several common spellings; canonical is N_ppm.
    "N_ppm": "N_ppm",
    "Nppm": "N_ppm",
    "N (ppm)": "N_ppm",
    "Nitrogen": "N_ppm",
    # Redox
    "Fe3FeT": "Fe3FeT",
    "dNNO": "dNNO",
    "dFMQ": "dFMQ",
    "DNNO": "dNNO",
    "DFMQ": "dFMQ",
    # Other
    "Xppm": "Xppm",
}


def _mapped_to_composition(mapped: dict[str, object], fallback_name: str = "unknown") -> MeltComposition:
    """Build a MeltComposition from an alias-mapped dict.

    This is the shared logic used by both :func:`read_compositions`
    (CSV rows) and :func:`composition_from_dict` (user-supplied dicts).
    """
    sample = str(mapped.get("sample", fallback_name))
    t_c = float(mapped.get("T_C", 1200.0))

    # Speciated iron
    feo_spec = mapped.get("_FeO_speciated")
    fe2o3_spec = mapped.get("_Fe2O3_speciated")
    feo_spec = float(feo_spec) if feo_spec is not None else None
    fe2o3_spec = float(fe2o3_spec) if fe2o3_spec is not None else None

    # Total iron as FeO
    feot = mapped.get("FeOT")
    if feot is not None:
        feot = float(feot)
    elif feo_spec is not None and fe2o3_spec is not None:
        feot = feot_from_speciated(feo_spec, fe2o3_spec)
    else:
        feot = float(feo_spec) if feo_spec is not None else 0.0

    fe3fet = mapped.get("Fe3FeT")
    fe3fet = float(fe3fet) if fe3fet is not None else None

    return MeltComposition(
        sample=sample,
        T_C=t_c,
        SiO2=float(mapped.get("SiO2", 0)),
        TiO2=float(mapped.get("TiO2", 0)),
        Al2O3=float(mapped.get("Al2O3", 0)),
        Cr2O3=float(mapped.get("Cr2O3", 0)),
        FeOT=feot,
        MnO=float(mapped.get("MnO", 0)),
        MgO=float(mapped.get("MgO", 0)),
        CaO=float(mapped.get("CaO", 0)),
        Na2O=float(mapped.get("Na2O", 0)),
        K2O=float(mapped.get("K2O", 0)),
        P2O5=float(mapped.get("P2O5", 0)),
        H2O=float(mapped.get("H2O", 0)),
        CO2=float(mapped.get("CO2", 0)),
        S=float(mapped.get("S", 0)),
        N_ppm=float(mapped.get("N_ppm", 0)),
        FeO=feo_spec,
        Fe2O3=fe2o3_spec,
        Fe3FeT=fe3fet,
        dNNO=float(mapped["dNNO"]) if "dNNO" in mapped else None,
        dFMQ=float(mapped["dFMQ"]) if "dFMQ" in mapped else None,
        Xppm=float(mapped.get("Xppm", 0)),
        reservoir=str(mapped.get("reservoir", "")),
    )


def _apply_aliases(raw: dict) -> dict[str, object]:
    """Map a raw dict's keys through ``_COLUMN_ALIASES``.

    Keys that don't match any alias are silently ignored (same
    behaviour as the CSV reader).
    """
    mapped: dict[str, object] = {}
    for key, val in raw.items():
        canon = _COLUMN_ALIASES.get(key)
        if canon is not None and val is not None:
            # Skip NaN-like float values (from pandas or numpy)
            try:
                if isinstance(val, float) and pd.isna(val):
                    continue
            except (TypeError, ValueError):
                pass
            mapped[canon] = val
    return mapped


def composition_from_dict(d: dict, fallback_name: str = "unknown") -> MeltComposition:
    """Create a :class:`MeltComposition` from a dict with flexible keys.

    Accepts the same key aliases as the CSV reader — ``Sample`` or
    ``sample``, ``FeO`` or ``FeOT``, ``DNNO`` or ``dNNO``, etc.

    Parameters
    ----------
    d : dict
        Composition as a flat dict.
    fallback_name : str
        Name to use if neither ``Sample`` nor ``sample`` is present.
    """
    mapped = _apply_aliases(d)
    return _mapped_to_composition(mapped, fallback_name=fallback_name)


def read_compositions(csv_path: str) -> list[MeltComposition]:
    """Read a CSV of melt compositions.

    Handles flexible column naming (Label vs Sample, FeO vs FeOT, etc.)
    and computes FeOT from speciated iron when needed.

    Parameters
    ----------
    csv_path : str
        Path to CSV file.

    Returns
    -------
    list[MeltComposition]
        One composition per row.
    """
    df = pd.read_csv(csv_path)
    compositions = []

    for idx, row in df.iterrows():
        mapped: dict[str, object] = {}
        for csv_col in df.columns:
            canon = _COLUMN_ALIASES.get(csv_col)
            if canon is not None:
                val = row[csv_col]
                if pd.notna(val):
                    mapped[canon] = val

        comp = _mapped_to_composition(mapped, fallback_name=f"row_{idx}")
        compositions.append(comp)

    return compositions


def compositions_to_dataframe(comps: list[MeltComposition]) -> pd.DataFrame:
    """Convert a list of MeltCompositions to a DataFrame."""
    return pd.DataFrame([c.to_dict() for c in comps])
