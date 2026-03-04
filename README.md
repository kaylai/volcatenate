# volcatenate

Unified volcanic degassing model comparison toolkit for Python.

**volcatenate** provides a single interface for running and comparing saturation pressure and degassing path calculations across six volcanic degassing models:

| Model | Type |
|-------|------|
| **VESIcal** | Solubility / degassing (C-O-H) |
| **VolFe** | Degassing with Fe-S redox (C-O-H-S) |
| **EVo** | Thermodynamic degassing (C-O-H-S-N) |
| **MAGEC** | MATLAB-based degassing (C-O-H-S) |
| **SulfurX** | Sulfur-focused degassing (C-O-H-S) |
| **D-Compress** | Decompression degassing (C-O-H-S) |

## Installation

```bash
# From the volcatenate directory:
pip install -e .

# With plotting support:
pip install -e ".[plotting]"

# With dev/test dependencies:
pip install -e ".[dev,plotting]"
```

Each model backend is optional. If a model's dependencies are not installed, it is silently skipped. Check which backends are available:

```python
import volcatenate
volcatenate.list_models(available_only=True)
```

## Quick Start

### Saturation Pressure (batch of compositions)

Calculate volatile saturation pressures for multiple melt compositions from a CSV file:

```python
import volcatenate

satp_df = volcatenate.calculate_saturation_pressure(
    "examples/example_satP_input.csv",
    models=["EVo", "VolFe", "MAGEC"],
)

# Export results
volcatenate.export_saturation_pressure(satp_df, "results/saturation_pressures.csv")
```

The returned DataFrame has one row per sample and columns `Sample`, `Reservoir`, plus `<Model>_SatP_bars` for each model.

### Degassing Path (single composition)

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

The returned dict maps model names to DataFrames with standardized output columns (see below).

### End-to-End Comparison

Run saturation pressure + degassing + CSV export in one call:

```python
import volcatenate
from volcatenate.config import RunConfig

config = RunConfig(keep_intermediates=False)

results = volcatenate.run_comparison(
    satp_compositions="examples/example_satP_input.csv",
    degassing_compositions="examples/example_degassing_input.csv",
    models=["EVo", "VolFe", "MAGEC"],
    config=config,
    satp_output="results/saturation_pressures.csv",
    degassing_output_dir="results/degassing",
)

# results["satp_df"]  -> saturation pressure DataFrame
# results["degassing"] -> {"Kilauea": {"EVo": DataFrame, "VolFe": DataFrame, ...}}
```

## Input Format

### CSV Input

Provide a CSV with one row per melt composition. Column names are flexible:

| Column | Aliases | Units | Required |
|--------|---------|-------|----------|
| `Sample` | `Label`, `sample` | -- | Yes |
| `T_C` | `Temp`, `Temperature` | Celsius | No (default: 1200) |
| `SiO2` | -- | wt% | Yes |
| `TiO2` | -- | wt% | Yes |
| `Al2O3` | -- | wt% | Yes |
| `FeOT` | `FeO*` | wt% (total iron as FeO) | * |
| `FeO` | -- | wt% (speciated) | * |
| `Fe2O3` | -- | wt% (speciated) | * |
| `MnO` | -- | wt% | No |
| `MgO` | -- | wt% | Yes |
| `CaO` | -- | wt% | Yes |
| `Na2O` | -- | wt% | Yes |
| `K2O` | -- | wt% | Yes |
| `P2O5` | -- | wt% | No |
| `H2O` | -- | wt% | Yes |
| `CO2` | -- | wt% | Yes |
| `S` | -- | wt% | Yes |
| `Fe3FeT` | -- | molar ratio (0-1) | No |
| `dNNO` | `DNNO` | log units | No |
| `dFMQ` | `DFMQ` | log units | No |

\* For iron, provide **either** `FeOT` (total iron as FeO) **or** speciated `FeO` + `Fe2O3`. If speciated values are given, `FeOT` is computed automatically.

See `examples/example_satP_input.csv` for a complete example.

### Dict Input

Dicts use the same flexible column names as CSV input:

```python
comp = {
    "Sample": "Kilauea",   # or "sample" or "Label"
    "T_C": 1200,
    "SiO2": 50.19,
    "FeOT": 11.34,         # or provide "FeO" + "Fe2O3"
    "H2O": 0.30,
    "CO2": 0.08,
    "S": 0.15,
    # ... other oxides ...
}
```

## Standardized Output Columns

All degassing path DataFrames share these column names:

| Column | Description |
|--------|-------------|
| `P_bars` | Pressure (bar) |
| `H2OT_m_wtpc` | Total H2O in melt (wt%) |
| `CO2T_m_ppmw` | Total CO2 in melt (ppm) |
| `ST_m_ppmw` | Total S in melt (ppm) |
| `Fe3Fet_m` | Fe3+/FeT ratio in melt |
| `S6St_m` | S6+/ST ratio in melt |
| `logfO2` | log10(fO2) |
| `dFMQ` | fO2 relative to FMQ buffer |
| `vapor_wt` | Vapor mass fraction (0-1) |
| `CO2_v_mf`, `H2O_v_mf`, `SO2_v_mf`, ... | Vapor species mole fractions |
| `CS_v_mf` | C/S vapor mole fraction ratio |

## Configuration

Each model backend has its own configuration dataclass. Override defaults via `RunConfig`:

```python
from volcatenate.config import RunConfig, EVoConfig, VolFeConfig

config = RunConfig(
    output_dir="my_output",
    keep_intermediates=False,       # Clean up intermediate files after each run
    evo=EVoConfig(p_stop=10),       # Change EVo final pressure to 10 bar
    volfe=VolFeConfig(
        gassing_style="closed",
        fo2_column="DNNO",
    ),
)
```

### `keep_intermediates`

When set to `False`, intermediate files (EVo YAML directories, MAGEC Excel/MATLAB scripts, etc.) are automatically cleaned up after each model run, keeping only the result DataFrames in memory. Set to `True` (default) to retain all files for debugging or inspection.

## Plotting

The `volcatenate.plotting` module provides functions for generating publication-quality figures:

```python
import volcatenate.plotting as vp

# Plotly-based line plots (degassing paths)
fig = vp.plot_results(model_names, data_list, ["H2Om", "CO2m", "Sm"], line_colors)
vp.save_plotly_fig(fig, "figure_name", scale=4)

# Matplotlib-based deviation envelopes
data, fig, axes = vp.plot_all_melt_volatiles(systems, colors=["#4477AA", "#EE6677"])
fig.savefig("envelopes.png", dpi=300)
```

## CLI

```bash
# List available models
volcatenate list-models

# Run saturation pressure calculation
volcatenate saturation-pressure input.csv -m EVo,VolFe -o results.csv

# Run degassing path calculation
volcatenate degassing input.csv -m all -o ./paths/
```

## Examples

See the `examples/` directory:

- `example_satP_input.csv` -- Example CSV for saturation pressure calculations (4 basalt compositions)
- `example_degassing_input.csv` -- Example CSV for degassing path calculations (single composition)
- `run_full_comparison.py` -- Complete workflow script demonstrating satP, degassing, and figure generation

## License

This project accompanies the Sulfur Comparison Paper. Please contact the authors for usage terms.
