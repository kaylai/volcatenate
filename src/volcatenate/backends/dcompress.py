"""D-Compress backend — stub.

D-Compress is not yet callable from Python.  This backend exists as a
placeholder so that the registry knows about it and pre-existing
D-Compress output CSVs can be loaded through the converter.

Both ``calculate_saturation_pressure`` and ``calculate_degassing``
raise ``NotImplementedError``.
"""

from __future__ import annotations

import pandas as pd

from volcatenate.backends._base import ModelBackend
from volcatenate.composition import MeltComposition
from volcatenate.config import RunConfig


class Backend(ModelBackend):

    @property
    def name(self) -> str:
        return "DCompress"

    def is_available(self) -> bool:
        return False  # Cannot run D-Compress programmatically yet

    def calculate_saturation_pressure(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.Series | None:
        raise NotImplementedError(
            "D-Compress cannot be run programmatically yet. "
            "Use the D-Compress web interface and load the output CSV "
            "via volcatenate.converters.convert_dcompress()."
        )

    def calculate_degassing(
        self,
        comp: MeltComposition,
        config: RunConfig,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "D-Compress cannot be run programmatically yet. "
            "Use the D-Compress web interface and load the output CSV "
            "via volcatenate.converters.convert_dcompress()."
        )
