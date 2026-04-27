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
from dataclasses import dataclass, field, fields, MISSING as dataclass_field_missing
from typing import Any, Type, TypeVar


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
    """VolFe model configuration.

    Managed internally by volcatenate (not exposed here):
      - ``output csv``     — always False; volcatenate handles its own output
      - ``print status``   — always False; volcatenate handles logging
      - ``starting_P``     — always 'Pvsat'
      - ``P_variation``    — always 'polybaric'
      - ``T_variation``    — always 'isothermal'
      - ``eq_Fe``          — always 'yes'

    Populated from the input composition (MeltComposition), not config:
      - Sample name, T_C, all oxides, H2O, CO2ppm, STppm, Xppm
      - fO2 indicator (DNNO / Fe3FeT / DFMQ) — chosen via ``fo2_column``
    """

    # Saturation
    sulfur_saturation: bool = False
    graphite_saturation: bool = False

    # Redox input (volcatenate-specific: which column to read from the input CSV)
    fo2_column: str = "Fe3FeT"        # 'DNNO', 'Fe3FeT', or 'DFMQ'

    # Degassing
    gassing_style: str = "closed"       # 'closed' or 'open'
    gassing_direction: str = "degas"    # 'degas' or 'regas'
    bulk_composition: str = "melt-only" # 'melt-only', 'melt+vapor_wtg', 'melt+vapor_initialCO2'

    # Species
    coh_species: str = "yes_H2_CO_CH4_melt"  # COH species in melt and vapor
    h2s_melt: bool = True               # H2S as dissolved melt species
    species_x: str = "Ar"               # Chemical identity of species X ('Ar' or 'Ne')

    # Oxygen fugacity
    fo2_model: str = "Kress91A"          # fO2–Fe3+/FeT relationship
    fmq_buffer: str = "Frost91"          # FMQ buffer parameterisation

    # Solubility constants
    co2_sol: str = "MORB_Dixon95"        # CO2T solubility constant
    h2o_sol: str = "Basalt_Hughes24"     # H2O solubility constant
    h2_sol: str = "Basalt_Hughes24"      # H2 solubility constant
    sulfide_sol: str = "ONeill21dil"     # S2- solubility constant
    sulfate_sol: str = "ONeill22dil"     # S6+ solubility constant
    h2s_sol: str = "Basalt_Hughes24"     # H2S solubility constant
    ch4_sol: str = "Basalt_Ardia13"      # CH4 solubility constant
    co_sol: str = "Basalt_Hughes24"      # CO solubility constant
    x_sol: str = "Ar_Basalt_HughesIP"    # Species X solubility constant
    c_spec_comp: str = "Basalt"          # CO2mol/CO32- speciation model
    h_spec_comp: str = "MORB_HughesIP"   # H2Omol/OH- speciation model

    # Saturation conditions
    scss: str = "ONeill21hyd"            # SCSS model
    scas: str = "Zajacz19_pss"           # SCAS model

    # Fugacity coefficients
    ideal_gas: bool = False              # Treat all vapor species as ideal gases
    y_co2: str = "Shi92"                 # CO2 fugacity coefficient
    y_so2: str = "Shi92_Hughes23"        # SO2 fugacity coefficient
    y_h2s: str = "Shi92_Hughes24"        # H2S fugacity coefficient
    y_h2: str = "Shaw64"                 # H2 fugacity coefficient
    y_o2: str = "Shi92"                  # O2 fugacity coefficient
    y_s2: str = "Shi92"                  # S2 fugacity coefficient
    y_co: str = "Shi92"                  # CO fugacity coefficient
    y_ch4: str = "Shi92"                 # CH4 fugacity coefficient
    y_h2o: str = "Holland91"             # H2O fugacity coefficient
    y_ocs: str = "Shi92"                 # OCS fugacity coefficient

    # Equilibrium constants (only those with multiple model options)
    k_hosg: str = "Ohmoto97"            # H2S equilibrium (0.5S2 + H2O = H2S + 0.5O2)
    k_osg: str = "Ohmoto97"             # SO2 equilibrium (0.5S2 + O2 = SO2)
    k_cohg: str = "Ohmoto97"            # CH4 equilibrium (CH4 + 2O2 = CO2 + 2H2O)
    k_ocsg: str = "Moussallam19"         # OCS equilibrium


@dataclass
class EVoConfig:
    """EVo model configuration.

    Managed internally by volcatenate (not exposed here):
      - ``COMPOSITION``    — always 'basalt'
      - ``RUN_TYPE``       — set by volcatenate method (closed/open)
      - ``SINGLE_STEP``    — always False
      - ``S_SAT_WARN``     — always False

    Volatile initialization (from MeltComposition, not config):
      - ``WTH2O_SET/START``  — always True; value from comp.H2O
      - ``WTCO2_SET/START``  — always True; value from comp.CO2
      - ``SULFUR_SET/START`` — always True; value from comp.S

    fO2 buffer (auto-selected from composition data):
      - ``FO2_buffer_SET``   — True only when no Fe3FeT data available
      - ``FO2_buffer/START`` — picked from comp.dNNO or comp.dFMQ

    Fugacity fallbacks (kept at EVo defaults):
      - ``FO2_SET/START``, ``FH2_SET/START``, ``FH2O_SET/START``,
        ``FCO2_SET/START`` — always False (wt% initialization used instead)

    Iron split (from MeltComposition):
      - FeOT is split into FeO + Fe2O3 using comp.fe3fet_computed in chem.yaml
    """

    gas_system: str = "cohs"
    fo2_buffer: str = "FMQ"
    fe_system: bool = True
    find_saturation: bool = True
    atomic_mass_set: bool = False
    ocs: bool = False                 # Include OCS as a gas species
    dp_min: int = 1
    dp_max: int = 100
    mass: int = 100
    p_start: int = 3000              # bar
    p_stop: int = 1                  # bar
    wgt: float = 0.00001             # Initial gas weight fraction
    loss_frac: float = 0.9999        # Gas loss fraction per step (open-system)
    run_type: str = "closed"           # 'closed' or 'open' (open requires loss_frac < 1)

    # Volatile initialization as atomic mass fractions (ppm).
    # Only used when atomic_mass_set = True.
    atomic_h: float = 500
    atomic_c: float = 200
    atomic_s: float = 4000
    atomic_n: float = 10

    # Nitrogen and graphite
    nitrogen_set: bool = False        # Set N from composition (if True, uses N from MeltComposition)
    graphite_saturated: bool = False  # Graphite saturation at start

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

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"MORB": {"dp_max": 25}, "Fogo": {"p_start": 5000, "gas_system": "coh"}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


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
    fe_redox: int = 1          # (1) Sun & Yao 2024; (2) KC91; (3) Hirschmann 2022
    s_redox: int = 1           # (1) Sun & Yao 2024; (2) Nash 2019; (3) Jugo 2010;
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

    # Per-sample overrides: {sample_name: {field_name: value}}
    # Example: {"Fogo": {"p_start_kbar": 8.0}}
    # Unknown field names are warned and skipped at resolution time.
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)


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
        Root directory for all output files (results CSVs, figures,
        raw tool output).  Default ``""`` means the current working
        directory.
    raw_output_dir : str
        Subdirectory (relative to *output_dir*) for raw model files
        — EVo YAML configs, MAGEC MATLAB scripts, per-sample
        subdirectories, etc.  Default ``"raw_tool_output"``.
    keep_raw_output : bool
        If *True* (default), all raw tool output files are retained
        in *raw_output_dir* for inspection.  If *False*, raw files
        are cleaned up after each model run completes, keeping only
        the final result DataFrames in memory.
    """

    output_dir: str = "."
    raw_output_dir: str = "raw_tool_output"
    keep_raw_output: bool = True
    verbose: bool = False
    log_file: str = ""
    show_progress: bool = True
    save_bundle: str = ""

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
    ("_top", "output_dir"):          "Root directory for all output (default: working directory)",
    ("_top", "raw_output_dir"):     "Subdirectory for raw model files (EVo YAML, MAGEC scripts, etc.)",
    ("_top", "keep_raw_output"):    "Keep raw tool output files after run",
    ("_top", "verbose"):             "Print progress to terminal",
    ("_top", "log_file"):            "Write all output to this file (empty = no log file)",
    ("_top", "show_progress"):       "Show rich progress bars (True/False)",
    ("_top", "save_bundle"):         "Path to save reproducible JSON bundle (empty = don't save)",
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
    ("volfe", "gassing_direction"):  "'degas' or 'regas'",
    ("volfe", "bulk_composition"):   "'melt-only', 'melt+vapor_wtg', or 'melt+vapor_initialCO2'",
    ("volfe", "coh_species"):        "'yes_H2_CO_CH4_melt', 'no_H2_CO_CH4_melt', or 'H2O-CO2 only'",
    ("volfe", "h2s_melt"):           "Include H2Smol as dissolved melt species",
    ("volfe", "species_x"):          "'Ar' or 'Ne'",
    ("volfe", "fo2_model"):          "fO2-Fe3+/FeT model: 'Kress91A', 'Kress91', 'ONeill18', 'Borisov18'",
    ("volfe", "fmq_buffer"):         "FMQ buffer: 'Frost91' or 'ONeill87'",
    ("volfe", "co2_sol"):            "CO2T solubility constant",
    ("volfe", "h2o_sol"):            "H2O solubility constant",
    ("volfe", "h2_sol"):             "H2 solubility constant",
    ("volfe", "sulfide_sol"):        "S2- solubility constant",
    ("volfe", "sulfate_sol"):        "S6+ solubility constant",
    ("volfe", "h2s_sol"):            "H2S solubility constant",
    ("volfe", "ch4_sol"):            "CH4 solubility constant",
    ("volfe", "co_sol"):             "CO solubility constant",
    ("volfe", "x_sol"):              "Species X solubility constant",
    ("volfe", "c_spec_comp"):        "CO2mol/CO32- speciation model",
    ("volfe", "h_spec_comp"):        "H2Omol/OH- speciation model",
    ("volfe", "scss"):               "SCSS model",
    ("volfe", "scas"):               "SCAS model",
    ("volfe", "ideal_gas"):          "Treat all vapor species as ideal gases",
    ("volfe", "y_co2"):              "CO2 fugacity coefficient model",
    ("volfe", "y_so2"):              "SO2 fugacity coefficient model",
    ("volfe", "y_h2s"):              "H2S fugacity coefficient model",
    ("volfe", "y_h2"):               "H2 fugacity coefficient model",
    ("volfe", "y_o2"):               "O2 fugacity coefficient model",
    ("volfe", "y_s2"):               "S2 fugacity coefficient model",
    ("volfe", "y_co"):               "CO fugacity coefficient model",
    ("volfe", "y_ch4"):              "CH4 fugacity coefficient model",
    ("volfe", "y_h2o"):              "H2O fugacity coefficient model",
    ("volfe", "y_ocs"):              "OCS fugacity coefficient model",
    ("volfe", "k_hosg"):             "H2S equilibrium constant (0.5S2 + H2O = H2S + 0.5O2)",
    ("volfe", "k_osg"):              "SO2 equilibrium constant (0.5S2 + O2 = SO2)",
    ("volfe", "k_cohg"):             "CH4 equilibrium constant (CH4 + 2O2 = CO2 + 2H2O)",
    ("volfe", "k_ocsg"):             "OCS equilibrium constant",
    # EVo
    ("evo", "gas_system"):           "'cohs', 'coh', 'cos', etc.",
    ("evo", "fo2_buffer"):           "'FMQ', 'NNO', etc.",
    ("evo", "fe_system"):            "Include Fe redox equilibrium",
    ("evo", "find_saturation"):      "Find saturation pressure automatically",
    ("evo", "atomic_mass_set"):      "Use atomic mass fractions for H/C/S/N",
    ("evo", "ocs"):                  "Include OCS as a gas species",
    ("evo", "dp_min"):               "Minimum pressure step (bar)",
    ("evo", "dp_max"):               "Maximum pressure step (bar)",
    ("evo", "mass"):                 "System mass (g)",
    ("evo", "p_start"):              "Starting pressure (bar)",
    ("evo", "p_stop"):               "Final pressure (bar)",
    ("evo", "wgt"):                  "Initial gas weight fraction",
    ("evo", "loss_frac"):            "Gas loss fraction per step (open-system)",
    ("evo", "run_type"):             "'closed' (default) or 'open' — open-system requires loss_frac < 1",
    ("evo", "atomic_h"):             "Atomic H (ppm) — only used when atomic_mass_set=true",
    ("evo", "atomic_c"):             "Atomic C (ppm) — only used when atomic_mass_set=true",
    ("evo", "atomic_s"):             "Atomic S (ppm) — only used when atomic_mass_set=true",
    ("evo", "atomic_n"):             "Atomic N (ppm) — only used when atomic_mass_set=true",
    ("evo", "nitrogen_set"):         "Set N from composition",
    ("evo", "graphite_saturated"):   "Graphite saturation at start",
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
    ("evo", "overrides"):            "Per-sample overrides, e.g. {MORB: {dp_max: 25}}",
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
    ("magec", "overrides"):          "Per-sample overrides, e.g. {Fogo: {p_start_kbar: 8.0}}",
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
        s = f"{val}"
        # YAML 1.1 requires a '.' before 'e' for scientific notation
        # (e.g. '1e-05' is parsed as a string, '1.0e-05' as a float)
        if "e" in s and "." not in s:
            s = s.replace("e", ".0e", 1)
        return s
    if isinstance(val, dict):
        if not val:
            return "{}"
        # Inline YAML mapping: {key1: val1, key2: val2}
        items = ", ".join(
            f"{_format_value(k)}: {_format_value(v)}" for k, v in val.items()
        )
        return "{" + items + "}"
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
