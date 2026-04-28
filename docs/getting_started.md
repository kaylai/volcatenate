# Getting started

## Installation

Install volcatenate from a clone of the repository:

```bash
# From the volcatenate directory:
pip install -e .

# With plotting support:
pip install -e ".[plotting]"

# With dev/test dependencies:
pip install -e ".[dev,plotting]"
```

Each model backend is optional. If a model's dependencies are not
installed, it is silently skipped. Check which backends are available:

```python
import volcatenate
volcatenate.list_models(available_only=True)
```

## Saturation pressure (batch of compositions)

Calculate volatile saturation pressures for several melt compositions
from a CSV file:

```python
import volcatenate

satp_df = volcatenate.calculate_saturation_pressure(
    "examples/example_satP_input.csv",
    models=["EVo", "VolFe", "MAGEC"],
)

# Export results
volcatenate.export_saturation_pressure(satp_df, "results/saturation_pressures.csv")
```

The returned DataFrame has one row per sample and columns `Sample`,
`Reservoir`, plus `<Model>_SatP_bars` for each model.

## Degassing path (single composition)

Calculate a degassing path for one composition:

```python
import volcatenate

# From a CSV (uses the first row):
paths = volcatenate.calculate_degassing(
    "examples/example_degassing_input.csv",
    models=["EVo", "VolFe"],
)

# Or from a dict:
paths = volcatenate.calculate_degassing(
    {
        "Sample": "Kilauea", "T_C": 1200,
        "SiO2": 50.19, "TiO2": 2.34, "Al2O3": 12.79,
        "FeOT": 11.34, "MnO": 0.18, "MgO": 9.23, "CaO": 10.44,
        "Na2O": 2.39, "K2O": 0.43, "P2O5": 0.27,
        "H2O": 0.30, "CO2": 0.0800, "S": 0.1500,
        "Fe3FeT": 0.18, "dNNO": -0.23,
    },
    models=["all"],
)

# Export per-model CSVs
volcatenate.export_degassing_paths(paths, output_dir="results/degassing", sample_name="kilauea")
```

The returned dict maps model names to DataFrames with standardized output
columns.

## End-to-end comparison

Run saturation pressure + degassing + CSV export in a single call:

```python
import volcatenate
from volcatenate.config import RunConfig

config = RunConfig(keep_raw_output=False)

results = volcatenate.run_comparison(
    satp_compositions="examples/example_satP_input.csv",
    degassing_compositions="examples/example_degassing_input.csv",
    models=["EVo", "VolFe", "MAGEC"],
    config=config,
    satp_output="results/saturation_pressures.csv",
    degassing_output_dir="results/degassing",
)

# results["satp_df"]   -> saturation pressure DataFrame
# results["degassing"] -> {"Kilauea": {"EVo": DataFrame, "VolFe": DataFrame, ...}}
```

## Command line

```bash
# List available models
volcatenate list-models

# Run saturation pressure calculation
volcatenate saturation-pressure input.csv -m EVo,VolFe -o results.csv

# Run degassing path calculation
volcatenate degassing input.csv -m all -o ./paths/
```

## Where to next

- [Configuration](configuration.md) — all `RunConfig` settings.
- [Run bundles](run_bundles.md) — reproducible JSON snapshots of a run.
- [Config propagation reference](config_propagation.md) — what each YAML
  field actually does inside each backend.
- [API reference](api/index.rst) — every public module and function.
