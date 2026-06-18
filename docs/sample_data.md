# Supplying composition data

Every volcatenate function that runs a model takes some form of "composition" input. In practice that means one of three things — pick whichever is most convenient. Whatever you pass, the wrapper turns it into a `MeltComposition` object internally, so anywhere this documentation says "the sample" or "from the composition," you can read it as "the `MeltComposition` instance built from your input."

## Option 1 — CSV file (most common)

Hand any of the calculator functions the path to a CSV; volcatenate reads it and builds one `MeltComposition` per row.

```python
import volcatenate

result = volcatenate.calculate_saturation_pressure(
    "kilauea_inclusions.csv",
    models=["EVo", "VolFe"],
)
```

The CSV has one row per sample.

### Required columns

| Column                                 | Meaning                                                                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `Sample` (or `Label`)              | Sample identifier — used as the row key in the output.                                                                         |
| `T_C` (or `Temp`, `Temperature`) | Temperature in °C.                                                                                                             |
| Major oxides                           | `SiO2`, `TiO2`, `Al2O3`, `MnO`, `MgO `, `CaO `, `Na2O `, `K2O `, `P2O5 `, plus iron (see below) — all wt%. |
| `H2O`                                | Bulk H₂O, wt%.                                                                                                                 |
| `CO2`                                | Bulk CO₂, wt%.                                                                                                                 |
| `S`                                  | Bulk sulfur, wt%.                                                                                                               |

### Optional columns

| Column                                | Meaning                                                                    |
| ------------------------------------- | -------------------------------------------------------------------------- |
| `FeOT` (or `FeO*`)                | Total iron as FeO, wt%. The most common form.                              |
| `FeO`, `Fe2O3`                    | Speciated iron, both wt%. Supply both*or* just `FeOT`, not a mix.      |
| `Fe3FeT`                            | Ferric ratio (0–1). Accepted by EVo, VolFe, and MAGEC (not SulfurX).       |
| `dFMQ` (or `DFMQ`)                | log fO₂ relative to FMQ buffer.                                           |
| `dNNO` (or `DNNO`)                | log fO₂ relative to NNO buffer.                                           |
| `Cr2O3`                             | Used by MAGEC's anhydrous renormalization; ignored by every other backend. |
| `N_ppm` (or `Nppm`, `Nitrogen`) | Bulk nitrogen in ppm. Used by EVo when `evo.nitrogen_set=True`.          |
| `Xppm`                              | Inert trace species (Ar/Ne) — VolFe only.                                 |

Header matching is exact for canonical names but accepts the common aliases shown above. If a column you expect isn't being picked up, the alias map in [composition.py](https://github.com/kaylai/volcatenate/blob/main/src/volcatenate/composition.py) is the source of truth.

### Redox columns — what to provide

Different backends accept different redox indicators, and the wrapper passes whatever you supply straight through — it does **not** convert one indicator into another on a backend's behalf. So a sample must carry an indicator each backend you run can actually accept:

| Backend | Accepts                          | Notes                                                                 |
| ------- | -------------------------------- | -------------------------------------------------------------------- |
| EVo     | `Fe3FeT`, `dNNO`, `dFMQ`         | `auto` falls back Fe3+/FeT → dNNO → dFMQ across these three.          |
| VolFe   | `Fe3FeT`, `dNNO`, `dFMQ`         | `auto` falls back Fe3+/FeT → dNNO → dFMQ across these three.          |
| MAGEC   | `Fe3FeT`, `dFMQ`                 | Does not accept `dNNO`.                                               |
| SulfurX | `dFMQ`                           | Its native input is `delta_FMQ`; requires `dFMQ`.                     |

If a backend's accepted indicator is missing on the sample, that backend raises `ValueError` rather than substituting. `dFMQ` is the one indicator all four backends accept, so it is the safest single value to supply when you want to run every backend on the same sample. If you have only `Fe3FeT` or `dNNO` and want to include SulfurX (or MAGEC, for `dNNO`), convert to the accepted indicator yourself, using whichever fO2 model your study has standardized on, before the run. The strict-mode options (`evo.fo2_source`, `volfe.fo2_source`, `magec.redox_source`) make a backend raise on a specific missing indicator rather than fall back.

You need at least one indicator each backend you run can accept. Providing more than one is fine; each backend picks the one it accepts per its config.

## Option 2 — Python dict

For a quick interactive run, skip the CSV and pass a dict directly:

```python
fuego = {
    "Sample": "Fuego",
    "T_C": 1030,
    "SiO2": 53.7, "TiO2": 1.11, "Al2O3": 18.2, "FeOT": 9.83,
    "MnO": 0.20, "MgO": 3.94, "CaO": 8.34, "Na2O": 3.62, "K2O": 0.81, "P2O5": 0.25,
    "H2O": 4.7, "CO2": 0.085, "S": 0.028,
    "Fe3FeT": 0.24,
}

result = volcatenate.calculate_saturation_pressure(fuego, models=["EVo"])
```

A list of dicts works too, and is equivalent to a CSV with those rows.

## Option 3 — `MeltComposition` directly

Use this when the composition is built programmatically (from a database query, another tool's output, or a parametric sweep). Field names here are the **canonical** ones — the CSV-style aliases are not applied:

```python
from volcatenate.composition import MeltComposition

fuego = MeltComposition(
    sample="Fuego",
    T_C=1030,
    SiO2=53.7, TiO2=1.11, Al2O3=18.2, FeOT=9.83,
    MnO=0.20, MgO=3.94, CaO=8.34, Na2O=3.62, K2O=0.81, P2O5=0.25,
    H2O=4.7, CO2=0.085, S=0.028,
    Fe3FeT=0.24,
)
```

A list of `MeltComposition` instances also works.

This is the lowest-level entry point. Both the CSV and dict paths build `MeltComposition` objects internally, so anything you can do via CSV you can do via `MeltComposition` and vice versa.

### Editing one in place

`MeltComposition` is a plain dataclass, so you can change any field by assignment — handy when most samples share a value but one backend needs a different redox indicator:

```python
fuego.dFMQ = 1.17   # set a value SulfurX can read
fuego.H2O = 4.5     # any other field works the same way
```

The change sticks on that object. If you need an independent copy — say, a different fO₂ for one backend without touching another run's samples — read the CSV again rather than mutating a shared list.

## What "the sample" means in this documentation

Every reference to "the sample" or "from the composition" elsewhere in this documentation — in the [propagation reference](config_options.md), the [run-bundle guide](run_bundles.md), the example notebooks, and the API docstrings — refers to a single `MeltComposition` instance. The three input shapes above are just different ways of constructing those instances.

When the propagation reference says, for example, "EVo's `WTH2O_START` is filled from `comp.H2O / 100`," that means: whatever H₂O value you put in the `H2O` column of your CSV (or the `H2O` field of your dict / `MeltComposition`) flows through to EVo's `env.yaml` divided by 100.
