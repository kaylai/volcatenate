"""Auto-discovery registry for model backends.

Each backend module defines a ``Backend`` class that inherits from
:class:`~volcatenate.backends._base.ModelBackend`.  At import time this
module attempts to import each backend and silently skips those whose
external dependencies are missing.

Usage::

    from volcatenate.backends import get_backend, list_backends

    for name in list_backends():
        backend = get_backend(name)
        print(f"{name}: available={backend.is_available()}")
"""

from __future__ import annotations

import importlib
import warnings
from typing import Optional

from volcatenate.backends._base import ModelBackend

# Maps display name (e.g. "EVo") → Backend instance
_REGISTRY: dict[str, ModelBackend] = {}

# (module_name, class_name) for each backend
_BACKEND_MODULES = [
    ("volcatenate.backends.vesical",   "Backend"),
    ("volcatenate.backends.volfe",     "Backend"),
    ("volcatenate.backends.evo",       "Backend"),
    ("volcatenate.backends.magec",     "Backend"),
    ("volcatenate.backends.sulfurx",   "Backend"),
    ("volcatenate.backends.dcompress", "Backend"),
]


def _discover() -> None:
    """Import each backend module and register its Backend class."""
    for module_path, cls_name in _BACKEND_MODULES:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, cls_name)
            instance = cls()
            _REGISTRY[instance.name] = instance
        except Exception as exc:
            # Silently skip — the backend's is_available() would also
            # return False, but we can't even instantiate it.
            warnings.warn(
                f"Could not load backend {module_path}: {exc}",
                stacklevel=2,
            )


def get_backend(name: str) -> ModelBackend:
    """Return the backend instance for the given model name.

    Supports VESIcal variant names like ``"VESIcal_Iacono"`` or
    ``"VESIcal_Dixon"`` — these create a VESIcal backend pinned to
    a specific solubility model, independent of the config file.

    Parameters
    ----------
    name : str
        Model name (case-sensitive), e.g. ``"EVo"``, ``"VolFe"``,
        ``"VESIcal_Iacono"``.

    Raises
    ------
    KeyError
        If no backend with that name is registered.
    """
    if not _REGISTRY:
        _discover()
    if name in _REGISTRY:
        return _REGISTRY[name]

    # Dynamic VESIcal variant lookup
    if name.startswith("VESIcal_"):
        from volcatenate.backends.vesical import Backend as VESIcalBackend, VARIANT_MAP
        if name in VARIANT_MAP:
            instance = VESIcalBackend(variant=VARIANT_MAP[name])
            _REGISTRY[name] = instance  # cache for reuse
            return instance

    raise KeyError(
        f"Unknown backend {name!r}. "
        f"Available: {sorted(_REGISTRY.keys())}. "
        f"VESIcal variants: VESIcal_MS, VESIcal_Dixon, VESIcal_Iacono, "
        f"VESIcal_Liu, VESIcal_ShishkinaIdealMixing"
    )


def list_backends(available_only: bool = False) -> list[str]:
    """Return all registered backend names.

    Parameters
    ----------
    available_only : bool
        If *True*, only include backends whose ``is_available()``
        returns *True*.
    """
    if not _REGISTRY:
        _discover()
    if available_only:
        return sorted(n for n, b in _REGISTRY.items() if b.is_available())
    return sorted(_REGISTRY.keys())


def get_all_backends(available_only: bool = False) -> dict[str, ModelBackend]:
    """Return all registered backends as a dict.

    Parameters
    ----------
    available_only : bool
        If *True*, only include available backends.
    """
    if not _REGISTRY:
        _discover()
    if available_only:
        return {n: b for n, b in _REGISTRY.items() if b.is_available()}
    return dict(_REGISTRY)


__all__ = [
    "ModelBackend",
    "get_backend",
    "list_backends",
    "get_all_backends",
]
