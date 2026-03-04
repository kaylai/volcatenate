"""Converters for each model's native output → standardized column format.

Each converter module exposes:
    is_raw(df)  → bool   — True if the DataFrame looks like unconverted output
    convert(df) → DataFrame — Returns a copy with standardized column names
"""

from volcatenate.converters.evo_converter import (
    convert as convert_evo,
    is_raw as is_raw_evo,
)
from volcatenate.converters.volfe_converter import (
    convert as convert_volfe,
    is_raw as is_raw_volfe,
)
from volcatenate.converters.magec_converter import (
    convert as convert_magec,
    is_raw as is_raw_magec,
)
from volcatenate.converters.vesical_converter import (
    convert as convert_vesical,
    is_raw as is_raw_vesical,
)
from volcatenate.converters.sulfurx_converter import (
    convert as convert_sulfurx,
    is_raw as is_raw_sulfurx,
)
from volcatenate.converters.dcompress_converter import (
    convert as convert_dcompress,
    is_raw as is_raw_dcompress,
)

__all__ = [
    "convert_evo", "is_raw_evo",
    "convert_volfe", "is_raw_volfe",
    "convert_magec", "is_raw_magec",
    "convert_vesical", "is_raw_vesical",
    "convert_sulfurx", "is_raw_sulfurx",
    "convert_dcompress", "is_raw_dcompress",
]
