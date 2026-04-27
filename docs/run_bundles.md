# Run bundles

A *run bundle* is a single JSON file that captures everything needed to
reproduce a `volcatenate` run: the resolved configuration, every input
composition, the model list, backend versions, and machine/environment
provenance. Drop the JSON onto another machine, call
[`volcatenate.replay`](#replaying-a-bundle), and you get the same run back.

Bundles also replace ad-hoc `manifest.txt` files that downstream projects
(notably the [Sulfur Comparison Paper](https://github.com/PennyWieser/Sulfur_Comparison_Paper))
used to write alongside results — see
[Migrating from a custom manifest](#migrating-from-a-custom-manifest).

## Quickstart

Set `save_bundle` on `RunConfig` and `volcatenate` writes the bundle for
you when you call any of the top-level entry points:

```python
import volcatenate
from volcatenate.config import RunConfig

config = RunConfig(
    save_bundle="run_bundle.json",
    bundle_comments="Initial run for the Fuego sample set.",
)

volcatenate.run_comparison(
    satp_compositions=comps,
    degassing_compositions=comps,
    models=["VolFe", "MAGEC", "SulfurX"],
    config=config,
)
# → ./run_bundle.json
```

Replay it later — anywhere the dependencies are installed:

```python
import volcatenate
results = volcatenate.replay("run_bundle.json")
```

## Anatomy of a bundle

```json
{
  "volcatenate_version": "0.3.1",
  "timestamp": "2026-04-27T15:32:11+00:00",
  "python_version": "3.11.9",
  "run_type": "comparison",
  "models": ["VolFe", "MAGEC", "SulfurX"],
  "compositions": [
    {"sample": "Fuego", "T_C": 1030.0, "SiO2": 50.4, "...": "..."}
  ],
  "config": {
    "output_dir": ".", "save_bundle": "run_bundle.json",
    "bundle_comments": "Initial run for the Fuego sample set.",
    "magec": {"solver_dir": "/Users/me/MAGEC", "...": "..."},
    "volfe": {"...": "..."},
    "...": "..."
  },
  "satp_output": "saturation_pressures.csv",
  "degassing_output_dir": "degassing_csvs",
  "backend_versions": {
    "volfe":   {"version": "1.2.0", "git_sha": "a1b2c3d", "tested": true},
    "sulfurx": {"version": "0.2.3", "git_sha": null,      "tested": true},
    "magec":   {"version": "v1b (Sun & Yao 2024)", "tested": true}
  },
  "caller_git_state": {
    "repo_path": "/Users/me/PythonGit/Sulfur_Comparison_Paper",
    "sha": "ad001b9d4e...", "dirty": true, "branch": "main"
  },
  "platform_info": {
    "system": "Darwin", "release": "25.3.0",
    "machine": "arm64", "python_implementation": "CPython"
  },
  "comments": "Initial run for the Fuego sample set.",
  "pip_freeze": "absl-py==2.1.0\nanthropic==0.34.2\n... (truncated) ..."
}
```

| Key | Purpose |
|---|---|
| `volcatenate_version` | Version of `volcatenate` that wrote the bundle. |
| `timestamp` | ISO 8601 UTC timestamp of bundle creation. |
| `python_version` | Python version string from `platform.python_version()`. |
| `run_type` | `"saturation_pressure"`, `"degassing"`, or `"comparison"`. |
| `models` | Backend names to run (in order). |
| `compositions` | List of `MeltComposition.to_dict()` snapshots. |
| `config` | Resolved `RunConfig` as a nested dict (all sub-configs included). |
| `satp_output` / `degassing_output_dir` | Output paths used (comparison runs). |
| `backend_versions` | Per-backend version + git SHA where available. |
| `caller_git_state` | Git state of the **caller's** repo (the project invoking volcatenate). `None` if not in a git repo. |
| `platform_info` | OS / arch / Python implementation. |
| `comments` | Free-text notes from `config.bundle_comments` or the `comments` kwarg. |
| `pip_freeze` | Full `pip freeze` output for the active environment. `None` if pip freeze failed. |

## Replaying a bundle

```python
results = volcatenate.replay("run_bundle.json")
```

Replay re-resolves the saved compositions, rebuilds the `RunConfig`, and
calls the same entry point that produced the bundle.

Machine-specific paths (`magec.solver_dir`, `magec.matlab_bin`,
`sulfurx.path`) are stored verbatim in the bundle. If they don't exist on
the replay machine, override them:

```python
results = volcatenate.replay("run_bundle.json", config_overrides={
    "magec":   {"solver_dir": "/new/path/to/MAGEC"},
    "sulfurx": {"path": "/new/path/to/SulfurX"},
})
```

`config_overrides` accepts the same nested-dict shape as `RunConfig`. The
existing `save_bundle` field is cleared automatically during replay so the
original JSON isn't overwritten.

## Provenance and reproducibility

The bundle is the single source of truth for *what was run*. It records:

- **Caller git state** (`caller_git_state`) — the SHA, branch, and
  clean/dirty status of the project that invoked `volcatenate`. Detected
  by walking up from `os.getcwd()` until a `.git` directory or file is
  found. Silent on failure: returns `None` if there's no git repo, no
  `git` binary, or anything else goes wrong.
- **Pip freeze** (`pip_freeze`) — the full output of
  `python -m pip freeze` at run time. Stored as a single string; replay
  does not consume this, but it's invaluable when results diverge.
- **Platform info** (`platform_info`) — `system`, `release`, `machine`,
  `python_implementation`. Useful when the replay machine differs from
  the original.
- **Backend versions** (`backend_versions`) — per-backend version strings
  plus git SHA where the backend is installed from a working tree.
- **Free-text comments** (`comments`) — set via
  `RunConfig.bundle_comments` or the `comments` kwarg on `create_bundle`.
  This is where you describe *why* the run exists, what changed, what
  bugs you patched in a backend, etc.

Together these fields replace the hand-rolled `manifest.txt` files that
downstream projects used to write next to their results.

## Limitations

The bundle captures a lot but it does **not** guarantee bit-exact
reproducibility. In particular:

- **Transitive dependencies** are only pinned to whatever `pip freeze`
  records. If a sub-dependency uses a version range, you can still drift.
- **System libraries** (BLAS, MATLAB, system Python build, GCC version,
  etc.) are not captured. MAGEC results in particular depend on the MATLAB
  version, which the bundle does not pin.
- **Path-installed (non-pip) backends** only record the version string
  the backend registry produces — typically with no git SHA. EVo,
  SulfurX, and MAGEC fall in this category if you install them by
  cloning rather than via `pip install -e .`.
- **Cross-OS / cross-Python-minor replay** may produce numerically
  different results due to BLAS, libm, and floating-point rounding
  differences. The bundle records enough provenance to *detect* this
  but not to prevent it.
- **External data files** referenced by absolute path (e.g. a custom
  thermo database) are not embedded. The bundle stores the path; you
  need to ensure the file is present on the replay machine.

## Migrating from a custom manifest

Projects that previously wrote a `manifest.txt` like:

```
run_dir: _working_Apr-27-26
timestamp: 2026-04-27T15:32:11
git_state: ad001b9... (DIRTY — uncommitted changes)
python: 3.11.9 (...)

--- comments ---
1. Bug fix in VolFe ratio2overtotal() at 03c287c
2. Interpolate sulfur_x at low P/Pi for Fuego

--- tool versions ---
volcatenate==0.3.1
VolFe==1.2.0 (git: a1b2c3d)
SulfurX==0.2.3
...

--- config (manuscript_config.yaml) ---
<full yaml text>

--- pip freeze ---
<output of pip freeze>
```

…can drop their manifest code and rely on the bundle alone. Field
mapping:

| Manifest field | Bundle field |
|---|---|
| `run_dir` | external — caller's filesystem layout, not the bundle's concern |
| `timestamp` | `bundle.timestamp` |
| `git_state` | `bundle.caller_git_state` (`{repo_path, sha, dirty, branch}`) |
| `python` | `bundle.python_version` + `bundle.platform_info` |
| `comments` | `bundle.comments` (set via `config.bundle_comments`) |
| tool versions | `bundle.backend_versions` |
| raw YAML config | `bundle.config` (the *resolved* config — strictly more useful than the raw text) |
| `pip freeze` | `bundle.pip_freeze` |

Equivalent setup in your project:

```python
config = RunConfig(
    save_bundle=os.path.join(run_dir, "run_bundle.json"),
    bundle_comments=(
        "1. Bug fix in VolFe ratio2overtotal() at 03c287c\n"
        "2. Interpolate sulfur_x at low P/Pi for Fuego"
    ),
)
volcatenate.run_comparison(..., config=config)
```

That's it — every line of the old manifest is now reconstructible from
the JSON.
