"""Per-(sample, backend) resolved input capture for run bundles.

When a backend builds the actual input it will hand to the underlying model — EVo's ``env.yaml`` dict, VolFe's ``setup_df`` + ``models_df``, MAGEC's input row + settings struct, SulfurX's kwargs — it should call :func:`capture` so volcatenate can record exactly what got sent. This is the part of the run that is determined by the *combination* of the YAML config and the per-sample composition; it is the only honest answer to "what actually went into the model for this sample."

Two outputs:

- An on-disk yaml file at ``<output_dir>/resolved_inputs/<sample>/<backend>.yaml`` that humans can read and diff. These files are written outside ``raw_tool_output`` so they survive ``keep_raw_output=False``.
- A process-level dict that the run-bundle saver pulls into the JSON bundle so a ``RunBundle`` is fully self-contained for replay and audit.

The orchestrator calls :func:`reset` at the start of each top-level ``calculate_*`` invocation and :func:`snapshot` at the end.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml

from volcatenate.log import logger


# Process-level capture buffer. Keyed [sample][backend] -> resolved dict.
# Survives the lifetime of a single Python process; cleared by ``reset``.
_capture: dict[str, dict[str, dict[str, Any]]] = {}


def reset() -> None:
    """Clear the capture buffer.

    The orchestrator calls this at the start of each top-level ``calculate_*`` run so the bundle for the current run sees only the inputs from this run, not residue from earlier ones.
    """
    _capture.clear()


def capture(
    sample: str,
    backend: str,
    data: dict[str, Any],
    output_dir: Optional[str] = None,
) -> None:
    """Record what a backend actually sent to its underlying model.

    Stores ``data`` under ``[sample][backend]`` in the process-level buffer. If ``output_dir`` is provided, also writes a yaml file at ``<output_dir>/resolved_inputs/<sample>/<backend>.yaml``.

    Parameters
    ----------
    sample : str
        Sample name (matches ``MeltComposition.sample``).
    backend : str
        Short backend name (``"EVo"``, ``"VolFe"``, ``"MAGEC"``, ``"SulfurX"``, ``"VESIcal_*"``, etc.).
    data : dict
        Whatever the backend wants to record. Typical shape includes the dict / DataFrame contents passed to the model. Will be sanitized to JSON / YAML-safe primitives before writing.
    output_dir : str, optional
        Run output directory. If provided, a yaml sidecar is written. If omitted, only the in-memory buffer is updated.

    Notes
    -----
    Sanitization handles common non-yaml types: numpy scalars, NaN, pandas DataFrames (``orient="records"``), pandas Series (as dict).
    """
    sane = _sanitize(data)
    _capture.setdefault(sample, {})[backend] = sane

    if output_dir:
        path = os.path.join(
            output_dir, "resolved_inputs", sample, f"{backend}.yaml",
        )
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(
                    sane,
                    fh,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
        except OSError as exc:
            # Don't fail the run if we can't write the sidecar — the
            # bundle still gets the in-memory copy.
            logger.warning(
                "[resolved_inputs] could not write %s: %s", path, exc,
            )


def snapshot() -> dict[str, dict[str, dict[str, Any]]]:
    """Return a deep copy of all captured data.

    Used by the run-bundle saver at the end of the run.
    """
    return copy.deepcopy(_capture)


def _sanitize(val: Any) -> Any:
    """Convert a value to YAML-/JSON-safe primitives.

    - ``np.nan``, ``None`` → ``None``
    - ``np.integer`` / ``np.floating`` → Python int / float
    - ``np.bool_`` → Python bool
    - ``pd.DataFrame`` → list of row dicts (``orient="records"``)
    - ``pd.Series`` → dict
    - ``dict`` / ``list`` → recursively sanitized
    - Everything else passes through unchanged.
    """
    if val is None:
        return None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return None if np.isnan(val) else float(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    if isinstance(val, float) and np.isnan(val):
        return None
    if isinstance(val, pd.DataFrame):
        return [_sanitize(row) for row in val.to_dict(orient="records")]
    if isinstance(val, pd.Series):
        return _sanitize(val.to_dict())
    if isinstance(val, dict):
        return {str(k): _sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize(v) for v in val]
    return val
