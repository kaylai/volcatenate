"""Structured result containers for volcatenate calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcatenate import columns as col


class SaturationResult:
    """Saturation pressure results with full equilibrium state.

    Behaves like a ``pd.DataFrame`` (the pressure-only table with
    ``<Model>_SatP_bars`` columns) for backward compatibility.  Use
    ``.equilibrium_state`` for the complete thermodynamic state at
    saturation for each model.

    Attributes
    ----------
    pressure : pd.DataFrame
        Flat table with columns ``Sample``, ``Reservoir``, and one
        ``<Model>_SatP_bars`` column per model.  This is the same
        format returned by the old ``calculate_saturation_pressure``.
    equilibrium_state : dict[str, pd.DataFrame]
        Full equilibrium state per model.  Keys are model names
        (``"EVo"``, ``"VolFe"``, etc.), values are DataFrames with one
        row per sample and all standard columns (``P_bars``,
        ``H2OT_m_wtpc``, ``CO2T_m_ppmw``, ``Fe3Fet_m``, ``S6St_m``,
        ``CS_v_mf``, vapor mole fractions, etc.).
    """

    def __init__(
        self,
        equilibrium_state: dict[str, pd.DataFrame],
        samples: list[str],
        reservoirs: list,
    ) -> None:
        self._equilibrium_state = equilibrium_state
        self._samples = samples
        self._reservoirs = reservoirs
        self._pressure: pd.DataFrame | None = None  # lazy

    # ── Public properties ──────────────────────────────────────────

    @property
    def pressure(self) -> pd.DataFrame:
        """Flat backward-compatible table: Sample, Reservoir, <Model>_SatP_bars."""
        if self._pressure is None:
            self._pressure = self._build_pressure()
        return self._pressure

    @property
    def equilibrium_state(self) -> dict[str, pd.DataFrame]:
        """Full equilibrium state per model.

        Returns
        -------
        dict[str, pd.DataFrame]
            Keyed by model name.  Each DataFrame has one row per sample
            with all standard columns from :mod:`volcatenate.columns`.
        """
        return self._equilibrium_state

    # ── Private helpers ────────────────────────────────────────────

    def _build_pressure(self) -> pd.DataFrame:
        rows: list[dict] = []
        for i, sample in enumerate(self._samples):
            row: dict = {"Sample": sample, "Reservoir": self._reservoirs[i]}
            for model, df in self._equilibrium_state.items():
                mask = df["Sample"] == sample
                if mask.any() and col.P_BARS in df.columns:
                    val = df.loc[mask, col.P_BARS].iloc[0]
                    row[f"{model}_SatP_bars"] = val
                else:
                    row[f"{model}_SatP_bars"] = np.nan
            rows.append(row)
        return pd.DataFrame(rows)

    # ── DataFrame delegation (backward compatibility) ──────────────

    def __getattr__(self, name: str):
        # Avoid infinite recursion for attributes accessed during init
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.pressure, name)

    def __getitem__(self, key):
        return self.pressure[key]

    def __len__(self) -> int:
        return len(self.pressure)

    def __iter__(self):
        return iter(self.pressure)

    def __repr__(self) -> str:
        return repr(self.pressure)

    def __str__(self) -> str:
        return str(self.pressure)

    def to_csv(self, *args, **kwargs):
        """Write the pressure-summary table to CSV."""
        return self.pressure.to_csv(*args, **kwargs)
