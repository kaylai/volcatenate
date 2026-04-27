# volcatenate

Unified volcanic degassing model comparison toolkit for Python. The purpose is for this to be a usable library for python scripting and some simple CLI use, with the specific goal of obtaining a clean single pipeline to run degassing simluation rungs with EVo, MAGEC, Sulfur_X, and VolFe (C-O-H-S+), VESIcal (C-O-H; with MagmaSat, Iacono-Marziano, and Dixon (VolatileCalc) solubility models), and D-Compress. The latter is separatated out simply because we cannot easily run it programmatically due to its use of a GUI, but plotting functions within volcatenate do ingest D-Compress outputs pre-formatted with certain columns.

This library was developed based on original messy python scripts written by K. Iacovino (me) to parse existing modeling tool outputs, create plots for an in-prep manuscript, and bootstrap python wrappers for recalculating those outputs with the tools. This library was develoed with substantial help from Anthropic's Claude AI: Claude for Mac Version 1.1.4498 (24f768), particularly for handling MAGEC, debugging my bootstrapped wrappers, and coding workarounds for solvers internal to tools when they failed to converge. "We" (this pronoun is easierst - me and Claude) kept a running list of "model quirks", things we stumbled over when trying to implement them in this python mega wrapper.

The GitHub repository the authors are using for this project, with more information on the manuscript-specific info, lives here: https://github.com/PennyWieser/Sulfur_Comparison_Paper

**volcatenate** provides a single interface for running and comparing saturation pressure and degassing path calculations across six volcanic degassing models:

| Model | Type |
|-------|------|
| **VESIcal** | Solubility / degassing (C-O-H) |
| **VolFe** | Degassing with Fe-S redox (C-O-H-S) |
| **EVo** | Thermodynamic degassing (C-O-H-S-N) |
| **MAGEC** | MATLAB-based degassing (C-O-H-S) |
| **SulfurX** | Sulfur-focused degassing (C-O-H-S) |
| **D-Compress** | Decompression degassing (C-O-H-S) |

## Model code repos and literature citations
#### D-Compress: https://www.isterre.fr/annuaire/pages-web-du-personnel/alain-burgisser/article/software.html
  - Burgisser, A., Alleti, M. & Scaillet, B. (2015) Simulating the behavior of volatiles belonging to the C–O–H–S system in silicate melts under magmatic conditions with the software D-Compress. Computers & Geosciences [doi:10.1016/j.cageo.2015.03.002](http://dx.doi.org/10.1016/j.cageo.2015.03.002)

#### EVo: https://github.com/pipliggins/EVo
  - EVo first mentioned:
    - Liggins, P., Shorttle, O. and Rimmer, P.B. (2020) Can Volcanism Build Hydrogen Rich Early Atmospheres? Earth and Planetary Science Letters, 550, 116546. [doi.org/10.1016/j.epsl.2020.116546](https://www.sciencedirect.com/science/article/pii/S0012821X20304908)
  - More recent citation with current changes to the sulfur model:
    - Liggins, P., Jordan, S., Rimmer, P.B., and Shorttle, O. (2022) Growth and Evolution of Secondary Volcanic Atmospheres I: Identifying the Geological Character of Hot Rocky Planets. Journal of Geophysical Research: Planets, 127. [doi.org/10.1029/2021JE007123](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2021JE007123)
  - ReadTheDocs: https://evo-outgas.readthedocs.io/en/latest/

### MAGEC: No repo
  - Sun, C., Lee, C.T.A., 2022. Redox evolution of crystallizing magmas with c-h-o-s volatiles and its implications for atmospheric oxygenation. Geochimica et Cosmochimica Acta 338, 302–321. [doi:https://doi.org/10.1016/j.gca.2022.09.044](https://www.sciencedirect.com/science/article/abs/pii/S0016703722005300).
  - Sun, C., Yao, L., 2024. Redox equilibria of iron in low- to high-silica melts: A simple model and its applications to c-h-o-s degassing. Earth and Planetary Science Letters 638, 118742. [doi:https://doi.org/10.1016/j.epsl.2024.118742](https://www.sciencedirect.com/science/article/pii/S0012821X24001754).
  
#### Sulfur_X: https://github.com/sdecho/Sulfur_X
  - Ding, S., Plank, T., Wallace, P. J. & Rasmussen, D. J. (2023) Sulfur_X: A Model of Sulfur Degassing During Magma Ascent. Geochem., Geophys., Geosystems 24.

#### VolFe: https://github.com/eryhughes/VolFe
  - Hughes, E.C., Saper, L.M., Liggins, P., O'Neill, H.S.C. and Stolper, E.M. (2023) The sulfur solubility minimum and maximum in silicate melt. Journal of the Geological Society 180 (3): jgs2021–125. doi: https://doi.org/10.1144/jgs2021-125
  - Hughes, E.C., Liggins, P., Saper, L. and Stolper, E.M. (accepted) The effects of oxygen fugacity and sulfur on the pressure of vapor-saturation of magma. American Mineralogist doi: 10.2138/am-2022-8739

#### VESIcal: https://github.com/kaylai/VESIcal
  - Model description:
    - Iacovino, K., Matthews, S., Wieser, P. E., Moore, G. M. & Bégué, F. (2021) VESIcal Part I: An open‐source thermodynamic model engine for mixed volatile (H2O-CO2) solubility in silicate melts. Earth Space Sci [doi:10.1029/2020ea001584](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2020EA001584).
  - Overview of models and intercomparison: 
    - Wieser, P. E., Iacovino, K., Matthews, S., Moore, G. & Allison, C. M. (2022) VESIcal Part II: A critical approach to volatile solubility modelling using an open‐source Python3 engine. Earth Space Sci [doi:10.1029/2021ea001932](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2021EA001932).
  - ReadTheDocs: https://vesical.readthedocs.io/en/latest/
  - Web app: https://vesical.anvil.app


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

config = RunConfig(keep_raw_output=False)

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
    keep_raw_output=False,          # Clean up raw tool files after each run
    evo=EVoConfig(p_stop=10),       # Change EVo final pressure to 10 bar
    volfe=VolFeConfig(
        gassing_style="closed",
        fo2_column="DNNO",
    ),
)
```

### `keep_raw_output`

When set to `False`, raw tool output files (EVo YAML directories, MAGEC Excel/MATLAB scripts, VolFe solver debug files, etc.) are automatically cleaned up after each model run, keeping only the result DataFrames in memory. Set to `True` (default) to retain all files in the `raw_tool_output/` subdirectory for debugging or inspection.

### Reproducible run bundles

Set `RunConfig.save_bundle = "path/to/run_bundle.json"` to write a single JSON file capturing the resolved config, every input composition, model list, backend versions, caller git state, `pip freeze`, platform info, and free-text notes (`bundle_comments`). Replay with `volcatenate.replay("run_bundle.json")`. See [docs/run_bundles.md](docs/run_bundles.md) for full details and migration guidance for projects replacing a hand-rolled `manifest.txt`.

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

GPL, see license file.
