"""Configuration dataclasses for each model backend.

Defaults match the settings used in the Sulfur Comparison Paper.

Configuration can be set in Python or loaded from a YAML file::

    # Python-only
    from volcatenate.config import RunConfig, EVoConfig
    config = RunConfig(evo=EVoConfig(p_stop=10))

    # From YAML (edit only the fields you need)
    from volcatenate.config import load_config, save_config
    save_config(RunConfig(), "volcatenate_config.yaml")   # generate template
    config = load_config("volcatenate_config.yaml")       # load it back
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
from dataclasses import dataclass, field, fields, asdict, MISSING as dataclass_field_missing
from typing import Type, TypeVar


# ── Auto-detection helpers ───────────────────────────────────────

def _find_matlab() -> str:
    """Try to locate the MATLAB binary automatically.

    Search order:
      1. ``MATLAB_BIN`` environment variable
      2. ``matlab`` on ``$PATH`` (via ``shutil.which``)
      3. Common installation directories (macOS / Linux / Windows)

    Returns ``""`` if nothing is found.
    """
    # 1. Explicit environment variable
    env = os.environ.get("MATLAB_BIN", "")
    if env and os.path.isfile(env):
        return env

    # 2. On $PATH
    on_path = shutil.which("matlab")
    if on_path:
        return on_path

    # 3. Common installation directories
    system = platform.system()
    candidates: list[str] = []

    if system == "Darwin":
        # macOS: /Applications/MATLAB_R20*.app/bin/matlab (newest first)
        candidates = sorted(
            glob.glob("/Applications/MATLAB_R*.app/bin/matlab"),
            reverse=True,
        )
    elif system == "Linux":
        candidates = sorted(
            glob.glob("/usr/local/MATLAB/R*/bin/matlab"),
            reverse=True,
        )
    elif system == "Windows":
        candidates = sorted(
            glob.glob("C:\\Program Files\\MATLAB\\R*\\bin\\matlab.exe"),
            reverse=True,
        )

    for c in candidates:
        if os.path.isfile(c):
            return c

    return ""


def _find_magec_solver() -> str:
    """Try to locate the MAGEC solver directory automatically.

    Search order:
      1. ``MAGEC_SOLVER_DIR`` environment variable
      2. Directory containing ``MAGEC_Solver_v1b.p`` anywhere under
         common locations (home directory, ``~/MAGEC*``, etc.)

    Returns ``""`` if nothing is found.
    """
    # 1. Explicit environment variable
    env = os.environ.get("MAGEC_SOLVER_DIR", "")
    if env and os.path.isdir(env):
        return env

    # 2. Search common locations for the compiled solver file
    home = os.path.expanduser("~")
    search_roots = [
        os.path.join(home, "PythonGit", "Volatile_Models", "MAGEC*"),
        os.path.join(home, "MAGEC*"),
        os.path.join(home, "Documents", "MAGEC*"),
        os.path.join(home, "Desktop", "MAGEC*"),
    ]

    for pattern in search_roots:
        for root in sorted(glob.glob(pattern), reverse=True):
            matches = glob.glob(
                os.path.join(root, "**", "MAGEC_Solver_v1b.p"),
                recursive=True,
            )
            if matches:
                return os.path.dirname(matches[0])

    return ""


def _find_sulfurx() -> str:
    """Try to locate the SulfurX installation directory automatically.

    Search order:
      1. ``SULFURX_PATH`` environment variable
      2. Directory containing ``Iacono_Marziano_COH.py`` under
         common locations.

    Returns ``""`` if nothing is found.
    """
    # 1. Explicit environment variable
    env = os.environ.get("SULFURX_PATH", "")
    if env and os.path.isdir(env):
        return env

    # 2. Search common locations
    home = os.path.expanduser("~")
    search_roots = [
        os.path.join(home, "PythonGit", "Volatile_Models", "Sulfur*"),
        os.path.join(home, "Sulfur*"),
        os.path.join(home, "Documents", "Sulfur*"),
        os.path.join(home, "Desktop", "Sulfur*"),
    ]

    for pattern in search_roots:
        for root in sorted(glob.glob(pattern), reverse=True):
            marker = os.path.join(root, "Iacono_Marziano_COH.py")
            if os.path.isfile(marker):
                return root
            # Check one level deeper
            matches = glob.glob(os.path.join(root, "*", "Iacono_Marziano_COH.py"))
            if matches:
                return os.path.dirname(matches[0])

    return ""


@dataclass
class VESIcalConfig:
    """VESIcal model configuration."""

    model: str = "IaconoMarziano"
    steps: int = 101
    final_pressure: float = 1.0       # bar
    fractionate_vapor: float = 0.0    # 0 = closed, 1 = open


@dataclass
class VolFeConfig:
    """VolFe model configuration."""

    sulfur_saturation: bool = False
    graphite_saturation: bool = False
    fo2_column: str = "Fe3FeT"        # 'DNNO', 'Fe3FeT', or 'DFMQ'
    gassing_style: str = "closed"


@dataclass
class EVoConfig:
    """EVo model configuration."""

    gas_system: str = "cohs"
    fo2_buffer: str = "FMQ"
    fe_system: bool = True
    find_saturation: bool = True
    atomic_mass_set: bool = False
    dp_min: int = 1
    dp_max: int = 100
    mass: int = 100
    p_start: int = 3000              # bar
    p_stop: int = 1                  # bar

    # Solubility model selections
    h2o_model: str = "burguisser2015"
    h2_model: str = "gaillard2003"
    c_model: str = "burguisser2015"
    co_model: str = "armstrong2015"
    ch4_model: str = "ardia2013"
    sulfide_capacity: str = "oneill2020"
    sulfate_capacity: str = "nash2019"
    scss: str = "liu2007"
    n_model: str = "libourel2003"
    density_model: str = "spera2000"
    fo2_model: str = "kc1991"
    fmq_model: str = "frost1991"


@dataclass
class MAGECConfig:
    """MAGEC model configuration (MATLAB subprocess).

    The *solver_dir* and *matlab_bin* paths are auto-detected at
    import time.  You can also set the environment variables
    ``MAGEC_SOLVER_DIR`` and ``MATLAB_BIN`` to override detection.
    """

    solver_dir: str = field(default_factory=_find_magec_solver)
    matlab_bin: str = field(default_factory=_find_matlab)

    # Model settings (14 options matching MAGEC's settings sheet)
    sulfide_sat: int = 0       # (1) Yes; (0) No
    sulfate_sat: int = 0       # (1) Yes; (0) No
    graphite_sat: int = 0      # (1) Yes; (0) No
    fe_redox: int = 2          # (1) Sun & Yao 2024; (2) KC91; (3) Hirschmann 2022
    s_redox: int = 2           # (1) Sun & Yao 2024; (2) Nash 2019; (3) Jugo 2010;
                               #   (4) O'Neill 2022; (5) Boulliung 2023
    scss: int = 1              # (1) Blanchard 2021; (2) Fortin 2015;
                               #   (3) Smythe 2017; (4) O'Neill 2021
    sulfide_cap: int = 1       # (1) Nzotta 1999; (2) O'Neill 2021; (3) Boulliung 2023
    co2_sol: int = 1           # (1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015
    h2o_sol: int = 1           # (1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015
    co_sol: int = 1            # (1) Armstrong 2015; (2.x) Yoshioka 2019
    adiabatic: int = 0         # 0 = isothermal
    solver: int = 2            # (1) lsqnonlin; (2) fsolve
    gas_behavior: int = 1      # (1) real gas; (2) ideal
    o2_balance: int = 0        # (0) Total O balanced; (1) fixed fO2 buffer

    # Pressure search settings for saturation pressure
    redox_option: str = "Fe3+/FeT"   # 'logfO2', 'dFMQ', 'Fe3+/FeT', or 'S6+/ST'
    p_start_kbar: float = 3.0
    p_final_kbar: float = 0.001
    n_steps: int = 100

    # Subprocess timeout (seconds) — if MAGEC hangs (e.g. saturation
    # pressure outside search range), it will be killed after this.
    timeout: int = 300


@dataclass
class SulfurXConfig:
    """SulfurX model configuration.

    The *path* is auto-detected at import time.  You can also set
    the environment variable ``SULFURX_PATH`` to override detection.
    """

    path: str = field(default_factory=_find_sulfurx)
    coh_model: int = 0                # 0 = Iacono-Marziano, 1 = VolatileCalc
    slope_h2o: float = -0.3396        # K2O-H2O relationship: K2O = a * H2O + b
    constant_h2o: float = 2.7
    n_steps: int = 600                # Pressure grid steps for degassing
    fo2_tracker: int = 1              # 0 = buffered fO2, 1 = redox evolution
    s_fe_choice: int = 1              # S speciation model: 0=Nash, 1=O'Neill&Mavrogenes
    sigma: float = 0.005              # log10fO2 tolerance for redox calculation
    sulfide_pre: int = 0              # 0 = no sulfide precipitation, 1 = enabled


@dataclass
class DCompressConfig:
    """DCompress model configuration (stub)."""

    pass


@dataclass
class RunConfig:
    """Top-level configuration composing all model configs.

    Parameters
    ----------
    output_dir : str
        Directory for intermediate model output files (YAML configs,
        MATLAB scripts, per-sample subdirectories, etc.).
    keep_intermediates : bool
        If *True* (default), all intermediate files are retained in
        *output_dir* for inspection.  If *False*, intermediate files
        are cleaned up after each model run completes, keeping only
        the final result DataFrames in memory.  This dramatically
        reduces on-disk clutter (e.g., dozens of EVo YAML
        subdirectories or MAGEC MATLAB scripts).
    """

    output_dir: str = "volcatenate_output"
    keep_intermediates: bool = True
    verbose: bool = False
    log_file: str = ""
    show_progress: bool = True

    vesical: VESIcalConfig = field(default_factory=VESIcalConfig)
    volfe: VolFeConfig = field(default_factory=VolFeConfig)
    evo: EVoConfig = field(default_factory=EVoConfig)
    magec: MAGECConfig = field(default_factory=MAGECConfig)
    sulfurx: SulfurXConfig = field(default_factory=SulfurXConfig)
    dcompress: DCompressConfig = field(default_factory=DCompressConfig)


# ── Bundled default config ────────────────────────────────────────────

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yaml")


def default_config_path() -> str:
    """Return the path to the bundled default config YAML.

    The file contains all settings with their paper-default values and
    inline comments.  **Do not edit this file directly** — it lives
    inside the installed package and will be overwritten on reinstall.

    Instead, copy it to your project and edit the copy::

        # Easiest — from the command line:
        volcatenate init-config

        # Or in Python:
        import shutil, volcatenate
        shutil.copy(volcatenate.default_config_path(), "volcatenate_config.yaml")
    """
    return _DEFAULT_CONFIG_PATH


# ── Inline comments for YAML export ──────────────────────────────────
# Maps (section, field_name) → comment string.  Used by save_config()
# to produce human-readable YAML with the same documentation as the
# dataclass definitions above.

_FIELD_COMMENTS: dict[tuple[str, str], str] = {
    # top-level
    ("_top", "output_dir"):          "Directory for intermediate model output files",
    ("_top", "keep_intermediates"):  "Keep intermediate files (EVo YAML dirs, MAGEC scripts, etc.)",
    ("_top", "verbose"):             "Print progress to terminal",
    ("_top", "log_file"):            "Write all output to this file (empty = no log file)",
    ("_top", "show_progress"):       "Show rich progress bars (True/False)",
    # VESIcal
    ("vesical", "model"):            "Solubility model name",
    ("vesical", "steps"):            "Number of degassing steps",
    ("vesical", "final_pressure"):   "bar",
    ("vesical", "fractionate_vapor"): "0 = closed-system, 1 = open-system",
    # VolFe
    ("volfe", "sulfur_saturation"):  "",
    ("volfe", "graphite_saturation"): "",
    ("volfe", "fo2_column"):         "'DNNO', 'Fe3FeT', or 'DFMQ'",
    ("volfe", "gassing_style"):      "'closed' or 'open'",
    # EVo
    ("evo", "gas_system"):           "'cohs', 'coh', 'cos', etc.",
    ("evo", "fo2_buffer"):           "'FMQ', 'NNO', etc.",
    ("evo", "fe_system"):            "Include Fe redox equilibrium",
    ("evo", "find_saturation"):      "Find saturation pressure automatically",
    ("evo", "atomic_mass_set"):      "",
    ("evo", "dp_min"):               "Minimum pressure step (bar)",
    ("evo", "dp_max"):               "Maximum pressure step (bar)",
    ("evo", "mass"):                 "System mass (g)",
    ("evo", "p_start"):              "Starting pressure (bar)",
    ("evo", "p_stop"):               "Final pressure (bar)",
    ("evo", "h2o_model"):            "",
    ("evo", "h2_model"):             "",
    ("evo", "c_model"):              "",
    ("evo", "co_model"):             "",
    ("evo", "ch4_model"):            "",
    ("evo", "sulfide_capacity"):     "",
    ("evo", "sulfate_capacity"):     "",
    ("evo", "scss"):                 "",
    ("evo", "n_model"):              "",
    ("evo", "density_model"):        "",
    ("evo", "fo2_model"):            "",
    ("evo", "fmq_model"):            "",
    # MAGEC
    ("magec", "solver_dir"):         "Path to MAGEC_Solver_v1b.p directory",
    ("magec", "matlab_bin"):         "Path to MATLAB binary",
    ("magec", "sulfide_sat"):        "(1) Yes; (0) No",
    ("magec", "sulfate_sat"):        "(1) Yes; (0) No",
    ("magec", "graphite_sat"):       "(1) Yes; (0) No",
    ("magec", "fe_redox"):           "(1) Sun & Yao 2024; (2) KC91; (3) Hirschmann 2022",
    ("magec", "s_redox"):            "(1) Sun & Yao 2024; (2) Nash 2019; (3) Jugo 2010; (4) O'Neill 2022; (5) Boulliung 2023",
    ("magec", "scss"):               "(1) Blanchard 2021; (2) Fortin 2015; (3) Smythe 2017; (4) O'Neill 2021",
    ("magec", "sulfide_cap"):        "(1) Nzotta 1999; (2) O'Neill 2021; (3) Boulliung 2023",
    ("magec", "co2_sol"):            "(1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015",
    ("magec", "h2o_sol"):            "(1) IM2012; (2) Liu 2005; (3.x) Burgisser 2015",
    ("magec", "co_sol"):             "(1) Armstrong 2015; (2.x) Yoshioka 2019",
    ("magec", "adiabatic"):          "0 = isothermal",
    ("magec", "solver"):             "(1) lsqnonlin; (2) fsolve",
    ("magec", "gas_behavior"):       "(1) real gas; (2) ideal",
    ("magec", "o2_balance"):         "(0) Total O balanced; (1) fixed fO2 buffer",
    ("magec", "redox_option"):       "'logfO2', 'dFMQ', 'Fe3+/FeT', or 'S6+/ST'",
    ("magec", "p_start_kbar"):       "SatP search start pressure (kbar)",
    ("magec", "p_final_kbar"):       "SatP search end pressure (kbar)",
    ("magec", "n_steps"):            "Number of pressure steps for SatP search",
    ("magec", "timeout"):            "MATLAB subprocess timeout (seconds)",
    # SulfurX
    ("sulfurx", "path"):             "Path to SulfurX installation",
    ("sulfurx", "coh_model"):        "0 = Iacono-Marziano, 1 = VolatileCalc",
    ("sulfurx", "slope_h2o"):        "K2O-H2O relationship slope: K2O = a*H2O + b",
    ("sulfurx", "constant_h2o"):     "K2O-H2O relationship intercept",
    ("sulfurx", "n_steps"):          "Pressure grid steps for degassing",
    ("sulfurx", "fo2_tracker"):      "0 = buffered fO2, 1 = redox evolution",
    ("sulfurx", "s_fe_choice"):      "S speciation: 0=Nash, 1=O'Neill&Mavrogenes",
    ("sulfurx", "sigma"):            "log10fO2 tolerance for redox calculation",
    ("sulfurx", "sulfide_pre"):      "0 = no sulfide precipitation, 1 = enabled",
}

# Maps section name → dataclass type (for load_config)
_SECTION_CLASSES: dict[str, Type] = {
    "vesical": VESIcalConfig,
    "volfe": VolFeConfig,
    "evo": EVoConfig,
    "magec": MAGECConfig,
    "sulfurx": SulfurXConfig,
    "dcompress": DCompressConfig,
}


# ── YAML I/O ─────────────────────────────────────────────────────────

def _format_value(val: object) -> str:
    """Format a Python value for YAML output."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, str):
        # Quote strings that could be misinterpreted by YAML
        if val == "" or val in ("true", "false", "null", "yes", "no"):
            return f'"{val}"'
        # Quote strings with special chars
        if any(c in val for c in ":#{}[]|>&*!%@`"):
            return f'"{val}"'
        return val
    if isinstance(val, float):
        return f"{val}"
    return str(val)


def save_config(config: RunConfig, path: str) -> str:
    """Write a RunConfig to a commented YAML file.

    The generated file includes inline comments describing each
    setting, making it easy to edit.  All current values are written,
    so the file serves as both documentation and configuration.

    Parameters
    ----------
    config : RunConfig
        Configuration to save.
    path : str
        Output YAML file path.

    Returns
    -------
    str
        The path that was written to.
    """
    lines: list[str] = [
        "# volcatenate configuration",
        "# Generated with: volcatenate.config.save_config(RunConfig(), path)",
        "#",
        "# Edit only the settings you need to change.",
        "# Missing keys use defaults (paper settings).",
        "# Load with: config = volcatenate.config.load_config(path)",
        "",
    ]

    # Top-level scalar fields
    for f in fields(RunConfig):
        if f.name in _SECTION_CLASSES:
            continue  # handle sub-configs below
        val = getattr(config, f.name)
        comment = _FIELD_COMMENTS.get(("_top", f.name), "")
        line = f"{f.name}: {_format_value(val)}"
        if comment:
            line += f"  # {comment}"
        lines.append(line)

    # Sub-config sections
    for section_name in _SECTION_CLASSES:
        sub = getattr(config, section_name)
        sub_fields = fields(sub)
        if not sub_fields:
            continue  # skip empty (e.g. DCompressConfig)
        lines.append("")
        lines.append(f"{section_name}:")
        for f in sub_fields:
            val = getattr(sub, f.name)
            comment = _FIELD_COMMENTS.get((section_name, f.name), "")
            line = f"  {f.name}: {_format_value(val)}"
            if comment:
                line += f"  # {comment}"
            lines.append(line)

    lines.append("")  # trailing newline

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return path


T = TypeVar("T")


def _build_dataclass(cls: Type[T], data: dict) -> T:
    """Build a dataclass from a dict, ignoring unknown keys.

    Only keys that match actual field names are passed to the
    constructor; everything else is silently ignored.  Missing
    keys use the dataclass defaults.

    Empty strings are skipped for fields that use ``default_factory``
    (i.e. auto-detected paths) so that auto-detection still runs.
    """
    valid_names = {f.name for f in fields(cls)}
    # Fields that use default_factory (auto-detected paths).
    # For these, an empty string in YAML means "use auto-detection".
    factory_fields = {
        f.name for f in fields(cls)
        if f.default_factory is not dataclass_field_missing
    }
    filtered = {}
    for k, v in data.items():
        if k in valid_names:
            # Skip empty strings for auto-detected fields → let factory run
            if k in factory_fields and v == "":
                continue
            # Coerce types where needed (YAML may parse ints as floats)
            f_type = {f.name: f.type for f in fields(cls)}.get(k)
            if f_type == "int" and isinstance(v, float):
                v = int(v)
            filtered[k] = v
    return cls(**filtered)


def load_config(path: str) -> RunConfig:
    """Load a RunConfig from a YAML file.

    Only fields present in the YAML are overridden; everything
    else keeps its dataclass default.  This means a minimal YAML
    with just the settings you want to change works fine::

        # my_config.yaml
        output_dir: my_output
        magec:
          solver_dir: /new/path

    Parameters
    ----------
    path : str
        Path to YAML file.

    Returns
    -------
    RunConfig
    """
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    kwargs: dict[str, object] = {}

    # Top-level scalar fields
    for f in fields(RunConfig):
        if f.name in _SECTION_CLASSES:
            continue
        if f.name in raw:
            kwargs[f.name] = raw[f.name]

    # Sub-config sections
    for section_name, cls in _SECTION_CLASSES.items():
        if section_name in raw and isinstance(raw[section_name], dict):
            kwargs[section_name] = _build_dataclass(cls, raw[section_name])

    return RunConfig(**kwargs)
