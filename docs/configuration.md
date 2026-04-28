# Configuration

`volcatenate` is configured through a single `RunConfig` dataclass that holds
top-level run settings and one nested config per backend. You can build it in
Python or load it from a YAML file.

## Two ways to configure

### Python

```python
from volcatenate.config import RunConfig, EVoConfig
config = RunConfig(evo=EVoConfig(p_stop=10))
```

### YAML

```python
from volcatenate.config import load_config, save_config

# Generate a fully-populated template:
save_config(RunConfig(), "volcatenate_config.yaml")

# Or copy the bundled default in one shot:
#   $ volcatenate init-config

# Load it back:
config = load_config("volcatenate_config.yaml")
```

`load_config` only overrides fields that are present in the YAML; everything
else keeps its dataclass default. Minimal configs work fine:

```yaml
output_dir: my_output
magec:
  solver_dir: /custom/path
```

## Top-level settings

| Field | Default | Description |
|---|---|---|
| `output_dir` | `"."` | Root directory for all output. |
| `raw_output_dir` | `"raw_tool_output"` | Subdirectory for raw model files. |
| `keep_raw_output` | `True` | Keep raw tool output after run. |
| `verbose` | `False` | Print progress to terminal. |
| `log_file` | `""` | Write all output to this file. |
| `show_progress` | `True` | Show rich progress bars. |
| `save_bundle` | `""` | Path to save reproducible JSON bundle. See [run_bundles.md](run_bundles.md). |
| `bundle_comments` | `""` | Free-text notes recorded in the bundle's `comments` field (provenance only — ignored on replay). |

## Backend sections

Each backend has its own nested section. The full set of fields and accepted
values is documented inline in the bundled default config — open it with:

```bash
volcatenate init-config        # writes a copy you can edit
```

Or in Python:

```python
import volcatenate
print(volcatenate.config.default_config_path())
```

The currently-supported backends are: **VolFe**, **EVo**, **MAGEC**,
**SulfurX**, **DCompress** (stub), and **VESIcal** (split into one named
backend per solubility model: `VESIcal_Iacono`, `VESIcal_Dixon`,
`VESIcal_MS`, `VESIcal_Liu`, `VESIcal_ShishkinaIdealMixing`). Pick the
VESIcal variant by passing the name to the calculate functions —
there is no `vesical.model` config field.

## Per-sample overrides

A single global default does not always fit every sample. ("Sample" here means one `MeltComposition` instance — see [sample_data.md](sample_data.md) for how those are built from a CSV row, a Python dict, or the class directly.) For example, EVo's default `dp_max: 100` (bar) works fine for most basalts but causes the solver to bail out partway through degassing for reduced MORB at low pressure. The fix is `dp_max: 25` for that one sample only.

Every backend config (`VESIcalConfig`, `VolFeConfig`, `EVoConfig`, `MAGECConfig`, `SulfurXConfig`) carries an `overrides` dict shaped like `{sample_name: {field_name: value}}`:

```yaml
evo:
  dp_max: 100
  overrides:
    MORB: {dp_max: 25}
    Fogo: {p_start: 5000, gas_system: coh}

magec:
  p_start_kbar: 3.0
  overrides:
    Fogo: {p_start_kbar: 8.0}
```

Any scalar field on the backend config can be overridden. Samples not listed
under `overrides` use the global defaults from the rest of the section.

### Resolution rules

- **Unknown field names** (e.g. typos like `dp_maxx`) emit a warning and are
  ignored. The original value is kept.
- **Unknown sample names** raise `ValueError` from `run_comparison` before any
  model runs. The error names the offending samples and the backend they
  came from.
- Single-sample direct calls
  (`backend.calculate_degassing(comp, config)`) skip sample-name validation.
  They have no full sample list to compare against.

### Backwards compatibility

MAGEC previously had a per-field `p_start_overrides: {sample: value}` shim.
Configs that still use it load successfully with a deprecation warning, and
the values are folded into `magec.overrides`. Update your configs to silence
the warning:

```yaml
# Old (still works, but deprecated):
magec:
  p_start_overrides: {Fogo: 8.0}

# New:
magec:
  overrides:
    Fogo: {p_start_kbar: 8.0}
```

VESIcal previously had a `vesical.model: <SolubilityModel>` field that picked
which solubility model to use for the bare `"VESIcal"` backend. The bare
backend has been removed — request a named variant directly. Configs with
the old field load with a deprecation warning and the field is ignored:

```yaml
# Old (still loads, but deprecated and ignored):
vesical:
  model: IaconoMarziano

# New: drop the field, then request the variant by name:
#   volcatenate.calculate_degassing(comp, models=["VESIcal_Iacono", ...])
```

## Loading and saving

| Function | Purpose |
|---|---|
| `load_config(path)` | Read YAML, override only the fields present, keep dataclass defaults for the rest. |
| `save_config(cfg, path)` | Write a `RunConfig` to a fully-populated, commented YAML file. |
| `volcatenate init-config` | CLI shortcut that copies the bundled default to your working directory. |
