# volcatenate

**volcatenate** is a Python package that wraps several volcanic degassing
models — [VESIcal](https://github.com/kaylai/VESIcal),
[VolFe](https://github.com/eryhughes/VolFe),
[EVo](https://github.com/pipliggins/EVo),
[MAGEC](https://doi.org/10.1016/j.gca.2022.09.044),
[SulfurX](https://github.com/sdecho/Sulfur_X), and
D-Compress — behind a single Python API. The goal is a clean, scriptable
pipeline for running and comparing saturation-pressure and degassing-path
calculations across all of these tools at once.

The package was developed alongside the **Sulfur Comparison Paper**
([repo](https://github.com/PennyWieser/Sulfur_Comparison_Paper)) and is
distributed under the GPL.

## What you can do with it

- Compute saturation pressures for a batch of melt compositions using any
  combination of backends. Compositions can be supplied as a CSV, a Python
  dict, or a `MeltComposition` instance — see [sample_data.md](sample_data.md)
  for the full input options.
- Run degassing paths for one composition through every backend and get
  back DataFrames with standardized column names.
- Save a single JSON **run bundle** that captures the resolved
  configuration, every input composition, model versions, and machine
  metadata — and replay it later on another machine.
- Drive everything from Python, YAML, or the `volcatenate` CLI.

## Documentation

```{toctree}
:maxdepth: 2
:caption: User guide

getting_started
sample_data
configuration
run_bundles
config_options
```

```{toctree}
:maxdepth: 2
:caption: Examples

examples/minimal_config
examples/full_config
```

```{toctree}
:maxdepth: 2
:caption: Reference

api/index
```

## Indices

- {ref}`genindex`
- {ref}`modindex`
