"""Reproducible run bundles — save and replay volcatenate runs.

A *run bundle* is a single JSON file that captures everything needed
to reproduce a volcatenate calculation exactly:

- All input compositions (melt inclusions)
- Full model configuration (RunConfig + nested sub-configs)
- Model list and run type
- Metadata (volcatenate version, timestamp, Python version)

Usage
-----
**Saving** — set ``save_bundle`` in config or call directly::

    config = RunConfig(save_bundle="my_run.json")
    volcatenate.run_comparison(..., config=config)
    # → my_run.json is written automatically

    # Or manually:
    from volcatenate.reproducible import create_bundle, save_bundle
    bundle = create_bundle("comparison", compositions, models, config)
    save_bundle(bundle, "my_run.json")

**Replaying** — reproduce a run from a saved bundle::

    from volcatenate.reproducible import replay
    results = replay("my_run.json")

    # Override machine-specific paths:
    results = replay("my_run.json", config_overrides={
        "magec": {"solver_dir": "/new/path/to/MAGEC"},
    })
"""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, fields, asdict
from datetime import datetime, timezone
from typing import Any, Optional, Union

import numpy as np

from volcatenate.composition import MeltComposition, composition_from_dict
from volcatenate.config import RunConfig, _build_dataclass, _SECTION_CLASSES
from volcatenate.log import logger


# ---------------------------------------------------------------------------
# RunBundle dataclass
# ---------------------------------------------------------------------------

@dataclass
class RunBundle:
    """Everything needed to reproduce a volcatenate run.

    Attributes
    ----------
    volcatenate_version : str
        Version of volcatenate that created this bundle.
    timestamp : str
        ISO 8601 timestamp of bundle creation.
    python_version : str
        Python version string (e.g. "3.11.5").
    run_type : str
        One of ``"saturation_pressure"``, ``"degassing"``, or
        ``"comparison"``.
    models : list[str]
        Model backend names to run.
    compositions : list[dict]
        Each dict is a ``MeltComposition.to_dict()`` snapshot.
    config : dict
        Full ``RunConfig`` serialized as a nested dict.
    satp_output : str or None
        CSV output path for saturation pressures (comparison mode).
    degassing_output_dir : str or None
        Directory for degassing CSV output (comparison mode).
    backend_versions : dict
        Per-backend version info captured at bundle creation — keys are
        backend names (e.g. ``"sulfurx"``) and values are the dicts
        returned by ``volcatenate.backend_version_info``.
    """

    volcatenate_version: str
    timestamp: str
    python_version: str
    run_type: str
    models: list[str]
    compositions: list[dict]
    config: dict
    satp_output: Optional[str] = None
    degassing_output_dir: Optional[str] = None
    backend_versions: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.backend_versions is None:
            self.backend_versions = {}


# ---------------------------------------------------------------------------
# Config ↔ dict helpers
# ---------------------------------------------------------------------------

def _config_to_dict(config: RunConfig) -> dict:
    """Recursively convert a RunConfig to a plain dict.

    Handles nested dataclass sub-configs.  All values become
    JSON-serializable types (no numpy scalars, no NaN).
    """
    result: dict[str, Any] = {}

    for f in fields(config):
        val = getattr(config, f.name)

        if f.name in _SECTION_CLASSES:
            # Nested sub-config dataclass
            sub_dict: dict[str, Any] = {}
            for sf in fields(val):
                sv = getattr(val, sf.name)
                sub_dict[sf.name] = _sanitize_value(sv)
            result[f.name] = sub_dict
        else:
            result[f.name] = _sanitize_value(val)

    return result


def _dict_to_config(d: dict) -> RunConfig:
    """Reconstruct a RunConfig from a plain dict.

    Uses the same ``_build_dataclass`` helper as the YAML loader,
    so unknown keys are silently ignored and missing keys get defaults.
    """
    kwargs: dict[str, Any] = {}

    for f in fields(RunConfig):
        if f.name in _SECTION_CLASSES:
            if f.name in d and isinstance(d[f.name], dict):
                cls = _SECTION_CLASSES[f.name]
                kwargs[f.name] = _build_dataclass(cls, d[f.name])
        elif f.name in d:
            kwargs[f.name] = d[f.name]

    return RunConfig(**kwargs)


# ---------------------------------------------------------------------------
# JSON-safe value handling
# ---------------------------------------------------------------------------

def _sanitize_value(val: Any) -> Any:
    """Convert a value to a JSON-serializable form.

    - ``np.nan`` and ``float('nan')`` → ``None``
    - ``np.integer`` / ``np.floating`` → Python int/float
    - ``np.bool_`` → Python bool
    - ``dict`` values are recursively sanitized
    - Everything else passes through unchanged
    """
    if val is None:
        return None

    # numpy scalar types
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        if np.isnan(val):
            return None
        return float(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)

    # Python float NaN
    if isinstance(val, float) and np.isnan(val):
        return None

    # Recurse into dicts
    if isinstance(val, dict):
        return {k: _sanitize_value(v) for k, v in val.items()}

    # Recurse into lists
    if isinstance(val, list):
        return [_sanitize_value(v) for v in val]

    return val


def _restore_nan(val: Any) -> Any:
    """Restore NaN from None for float fields.

    This is the inverse of ``_sanitize_value`` for numeric contexts.
    Applied selectively when loading composition dicts.
    """
    if val is None:
        return np.nan
    return val


# ---------------------------------------------------------------------------
# Bundle creation
# ---------------------------------------------------------------------------

def create_bundle(
    run_type: str,
    compositions: list[MeltComposition],
    models: list[str],
    config: RunConfig,
    satp_output: Optional[str] = None,
    degassing_output_dir: Optional[str] = None,
) -> RunBundle:
    """Create a RunBundle from run inputs.

    Parameters
    ----------
    run_type : str
        One of ``"saturation_pressure"``, ``"degassing"``, or
        ``"comparison"``.
    compositions : list[MeltComposition]
        The melt compositions being run.
    models : list[str]
        Model backend names.
    config : RunConfig
        Full configuration.
    satp_output : str, optional
        Saturation pressure CSV path (for comparison runs).
    degassing_output_dir : str, optional
        Degassing output directory (for comparison runs).

    Returns
    -------
    RunBundle
    """
    from volcatenate import __version__
    from volcatenate.versions import all_backend_versions

    return RunBundle(
        volcatenate_version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        python_version=platform.python_version(),
        run_type=run_type,
        models=list(models),
        compositions=[_sanitize_value(c.to_dict()) for c in compositions],
        config=_config_to_dict(config),
        satp_output=satp_output,
        degassing_output_dir=degassing_output_dir,
        backend_versions=_sanitize_value(all_backend_versions()),
    )


# ---------------------------------------------------------------------------
# Save / Load
# ---------------------------------------------------------------------------

def save_bundle(bundle: RunBundle, path: str) -> str:
    """Write a RunBundle to a JSON file.

    Parameters
    ----------
    bundle : RunBundle
        The bundle to save.
    path : str
        Output file path (typically ``*.json``).

    Returns
    -------
    str
        The path that was written to.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    data = {
        "volcatenate_version": bundle.volcatenate_version,
        "timestamp": bundle.timestamp,
        "python_version": bundle.python_version,
        "run_type": bundle.run_type,
        "models": bundle.models,
        "compositions": bundle.compositions,
        "config": bundle.config,
        "satp_output": bundle.satp_output,
        "degassing_output_dir": bundle.degassing_output_dir,
        "backend_versions": bundle.backend_versions,
    }

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    logger.info("Run bundle saved to %s", path)
    return path


def load_bundle(path: str) -> RunBundle:
    """Load a RunBundle from a JSON file.

    Parameters
    ----------
    path : str
        Path to the JSON bundle file.

    Returns
    -------
    RunBundle
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    return RunBundle(
        volcatenate_version=data.get("volcatenate_version", "unknown"),
        timestamp=data.get("timestamp", ""),
        python_version=data.get("python_version", ""),
        run_type=data["run_type"],
        models=data["models"],
        compositions=data["compositions"],
        config=data["config"],
        satp_output=data.get("satp_output"),
        degassing_output_dir=data.get("degassing_output_dir"),
        backend_versions=data.get("backend_versions") or {},
    )


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def _compositions_from_bundle(
    bundle: RunBundle,
) -> list[MeltComposition]:
    """Reconstruct MeltComposition objects from bundle dicts.

    Restores ``None`` values to ``np.nan`` for numeric fields
    that were sanitized during serialization.
    """
    comps = []
    for d in bundle.compositions:
        # Restore NaN for optional numeric fields that were None in JSON
        restored = {}
        for key, val in d.items():
            restored[key] = val  # composition_from_dict handles None gracefully
        comps.append(composition_from_dict(restored))
    return comps


def _merge_config_overrides(
    config_dict: dict,
    overrides: dict,
) -> dict:
    """Merge user-provided overrides into a config dict.

    Supports nested dicts for sub-config sections::

        overrides = {
            "verbose": True,
            "magec": {"solver_dir": "/new/path"},
        }
    """
    merged = dict(config_dict)
    for key, val in overrides.items():
        if isinstance(val, dict) and key in merged and isinstance(merged[key], dict):
            merged[key] = {**merged[key], **val}
        else:
            merged[key] = val
    return merged


def replay(
    path: str,
    config_overrides: Optional[dict] = None,
) -> dict:
    """Load a run bundle and re-run the calculation.

    Parameters
    ----------
    path : str
        Path to the JSON bundle file.
    config_overrides : dict, optional
        Override specific config values for this machine.
        Supports nested dicts for sub-config sections::

            replay("run.json", config_overrides={
                "verbose": True,
                "magec": {"solver_dir": "/path/to/MAGEC"},
            })

    Returns
    -------
    dict
        Same return type as the original run function:

        - For ``"saturation_pressure"``: ``{"satp_df": SaturationResult}``
        - For ``"degassing"``: ``{"degassing": {sample: {model: DataFrame}}}``
        - For ``"comparison"``: ``{"satp_df": ..., "degassing": ...}``

    Notes
    -----
    The ``save_bundle`` config option is cleared during replay to avoid
    re-saving the bundle (which would overwrite the original).

    Machine-specific paths (e.g. ``magec.solver_dir``, ``magec.matlab_bin``,
    ``sulfurx.path``) are stored in the bundle for documentation but may
    not exist on the replay machine.  Use ``config_overrides`` to replace
    them, or let the auto-detection (default_factory) find the correct
    paths on this machine.
    """
    from volcatenate.core import (
        calculate_saturation_pressure,
        calculate_degassing,
        run_comparison,
    )

    bundle = load_bundle(path)
    logger.info(
        "Replaying %s run from %s (volcatenate %s, %s)",
        bundle.run_type, path,
        bundle.volcatenate_version, bundle.timestamp,
    )

    # Reconstruct config
    config_dict = bundle.config
    if config_overrides:
        config_dict = _merge_config_overrides(config_dict, config_overrides)

    # Clear save_bundle to avoid re-saving during replay
    config_dict["save_bundle"] = ""

    config = _dict_to_config(config_dict)

    # Reconstruct compositions
    compositions = _compositions_from_bundle(bundle)

    # Dispatch to the appropriate run function
    if bundle.run_type == "saturation_pressure":
        result = calculate_saturation_pressure(
            compositions,
            models=bundle.models,
            config=config,
        )
        return {"satp_df": result, "degassing": None}

    elif bundle.run_type == "degassing":
        all_degassing = {}
        for comp in compositions:
            results = calculate_degassing(
                comp,
                models=bundle.models,
                config=config,
            )
            all_degassing[comp.sample] = results
        return {"satp_df": None, "degassing": all_degassing}

    elif bundle.run_type == "comparison":
        return run_comparison(
            satp_compositions=compositions,
            degassing_compositions=compositions,
            models=bundle.models,
            config=config,
            satp_output=bundle.satp_output or "saturation_pressures.csv",
            degassing_output_dir=bundle.degassing_output_dir,
        )

    else:
        raise ValueError(
            f"Unknown run_type in bundle: {bundle.run_type!r}. "
            f"Expected 'saturation_pressure', 'degassing', or 'comparison'."
        )
