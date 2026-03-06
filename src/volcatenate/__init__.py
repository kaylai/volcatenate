"""volcatenate — Unified volcanic degassing model comparison library.

Compare saturation pressures and degassing paths across six models:
VESIcal, VolFe, EVo, MAGEC, SulfurX, and D-Compress.

Example usage::

    import volcatenate

    # Saturation pressures for a batch of melt compositions
    satp_df = volcatenate.calculate_saturation_pressure(
        "melt_inclusions.csv",
        models=["EVo", "VolFe"],
    )

    # Degassing path for a single composition
    paths = volcatenate.calculate_degassing(
        {"sample": "Kilauea", "T_C": 1200, "SiO2": 50.19, ...},
        models=["all"],
    )

    # End-to-end comparison (satP + degassing + CSV export)
    results = volcatenate.run_comparison(
        satp_compositions="melt_inclusions.csv",
        degassing_compositions=kilauea_dict,
        models=["EVo", "VolFe"],
    )

    # List available models
    volcatenate.list_models()

Configuration
-------------
All model settings default to the Sulfur Comparison Paper values,
so configuration is entirely **optional**.  Three approaches:

1. **Do nothing** — defaults are used automatically.

2. **Python-only** — override individual settings::

       from volcatenate.config import RunConfig, EVoConfig
       config = RunConfig(evo=EVoConfig(p_stop=10))

3. **YAML file** — generate a template, edit it, load it::

       volcatenate init-config          # creates ./volcatenate_config.yaml
       # ... edit the file ...
       config = volcatenate.load_config("volcatenate_config.yaml")

   You can also combine: load a YAML then tweak in Python::

       config = volcatenate.load_config("my_config.yaml")
       config.evo.p_stop = 10           # override one more thing
"""

from volcatenate.core import (
    calculate_saturation_pressure,
    calculate_degassing,
    export_saturation_pressure,
    export_degassing_paths,
    run_comparison,
)
from volcatenate.backends import list_backends, get_all_backends
from volcatenate.composition import MeltComposition, read_compositions
from volcatenate.config import RunConfig, load_config, save_config, default_config_path
from volcatenate.compat import (
    load_model_csv, load_data, degassing_results_to_compat,
    loadData, load_results,
)
from volcatenate.log import setup_logging
from volcatenate.plotting import generate_all_figures
from volcatenate.result import SaturationResult


def list_models(available_only: bool = False) -> list[str]:
    """Return the names of all registered model backends.

    Parameters
    ----------
    available_only : bool
        If *True*, only return models whose dependencies are installed.
    """
    return list_backends(available_only=available_only)


__version__ = "0.2.0"

__all__ = [
    # Core API
    "calculate_saturation_pressure",
    "calculate_degassing",
    "export_saturation_pressure",
    "export_degassing_paths",
    "run_comparison",
    # Helpers
    "list_models",
    "MeltComposition",
    "read_compositions",
    "RunConfig",
    "load_config",
    "save_config",
    "default_config_path",
    # Logging
    "setup_logging",
    # Compat layer
    "load_model_csv",
    "load_data",
    "load_results",
    "loadData",
    "degassing_results_to_compat",
    # Plotting
    "generate_all_figures",
    # Result containers
    "SaturationResult",
]
