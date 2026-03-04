"""Abstract base class for model backends.

Every degassing model (VESIcal, VolFe, EVo, MAGEC, SulfurX, D-Compress)
implements this interface.  The registry in ``backends/__init__.py``
auto-discovers all concrete implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig


class ModelBackend(ABC):
    """Interface that every model backend must implement."""

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
    ) -> float:
        """Return the volatile saturation pressure in **bars**.

        Parameters
        ----------
        comp : MeltComposition
            A single melt inclusion / sample composition.
        config : RunConfig
            Full configuration (each backend reads its own sub-config).

        Returns
        -------
        float
            Saturation pressure in bars, or ``np.nan`` on failure.
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

    def __repr__(self) -> str:
        avail = "available" if self.is_available() else "not available"
        return f"<{self.__class__.__name__} ({self.name}) [{avail}]>"
