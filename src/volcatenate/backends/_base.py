"""Abstract base class for model backends.

Every degassing model (VESIcal, VolFe, EVo, MAGEC, SulfurX, D-Compress)
implements this interface.  The registry in ``backends/__init__.py``
auto-discovers all concrete implementations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import pandas as pd

from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig


class ModelBackend(ABC):
    """Interface that every model backend must implement."""

    supports_batch_satp: bool = False
    """Override to ``True`` in backends that provide a native
    :meth:`calculate_saturation_pressure_batch` (e.g. MAGEC)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short display name, e.g. ``'EVo'``, ``'VolFe'``."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return *True* if the model's dependencies can be imported.

        Backends with missing packages should return *False* so the
        orchestrator can gracefully skip them.
        """
        ...

    @abstractmethod
    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.Series | None:
        """Return the equilibrium state at volatile saturation.

        The returned Series uses the canonical column names defined in
        :mod:`volcatenate.columns` (``P_bars``, ``H2OT_m_wtpc``,
        ``CO2T_m_ppmw``, ``Fe3Fet_m``, ``S6St_m``, ``CS_v_mf``,
        vapor mole fractions, etc.).  Individual fields may be ``NaN``
        if the model does not compute them.

        Parameters
        ----------
        comp : MeltComposition
            A single melt inclusion / sample composition.
        config : RunConfig
            Full configuration (each backend reads its own sub-config).

        Returns
        -------
        pd.Series or None
            Equilibrium state at saturation with standard column names,
            or *None* on failure.
        """
        ...

    @abstractmethod
    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        """Run a degassing path from saturation and return standardized output.

        The returned DataFrame uses the canonical column names defined in
        :mod:`volcatenate.columns`.  Rows are ordered from high to low
        pressure.

        Parameters
        ----------
        comp : MeltComposition
            Starting melt composition.
        config : RunConfig
            Full configuration.

        Returns
        -------
        pd.DataFrame
            Degassing path with standardized column names.
        """
        ...

    def calculate_saturation_pressure_batch(
        self,
        comps: list[MeltComposition],
        config: RunConfig,
    ) -> list[pd.Series | None]:
        """Run satP for a batch of compositions.

        The default implementation loops over single-sample calls.
        Backends that support true batching (e.g. MAGEC, which can
        avoid repeated MATLAB startup) should override this method
        and set ``supports_batch_satp = True``.

        Parameters
        ----------
        comps : list[MeltComposition]
            One or more melt compositions.
        config : RunConfig
            Full configuration.

        Returns
        -------
        list[pd.Series | None]
            One result per composition (same order as *comps*).
        """
        logger = logging.getLogger("volcatenate")
        results: list[pd.Series | None] = []
        for comp in comps:
            try:
                state = self.calculate_saturation_pressure(comp, config)
            except Exception as exc:
                logger.debug(
                    "%s batch satP failed for %s: %s",
                    self.name, comp.sample, exc,
                )
                state = None
            results.append(state)
        return results

    def __repr__(self) -> str:
        avail = "available" if self.is_available() else "not available"
        return f"<{self.__class__.__name__} ({self.name}) [{avail}]>"
