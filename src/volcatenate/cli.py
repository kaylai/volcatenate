"""Command-line interface for volcatenate.

Usage::

    volcatenate init-config                         # generate default config YAML
    volcatenate saturation-pressure input.csv -m EVo,VolFe -o results.csv
    volcatenate degassing kilauea.json -m all -o ./paths/
    volcatenate list-models
"""

from __future__ import annotations

import json
import os
import sys

import click

from volcatenate.config import RunConfig, load_config, save_config


@click.group()
@click.version_option(package_name="volcatenate")
def main():
    """volcatenate — Unified volcanic degassing model comparison."""
    pass


# ── Helper to load config from --config flag ──────────────────────────

def _load_run_config(config_path: str | None, output_dir: str | None = None) -> RunConfig:
    """Build a RunConfig from an optional YAML path + CLI overrides."""
    if config_path:
        config = load_config(config_path)
    else:
        config = RunConfig()
    if output_dir:
        config.output_dir = output_dir
    return config


# ── init-config ───────────────────────────────────────────────────────

@main.command("init-config")
@click.option("-o", "--output", default="volcatenate_config.yaml",
              help="Output YAML path (default: volcatenate_config.yaml).")
def init_config_cmd(output):
    """Generate a configuration YAML in your project directory.

    The file contains all settings with their default values and
    inline comments.  Paths to MATLAB, MAGEC, and SulfurX are
    auto-detected for your machine.  Edit only the fields you
    need to change; missing keys will use defaults when loaded.
    """
    from volcatenate.config import RunConfig, save_config

    config = RunConfig()  # auto-detects paths for this machine
    save_config(config, output)

    click.echo(f"Config written to {output}")

    # Report auto-detected paths
    if config.magec.matlab_bin:
        click.echo(f"  Auto-detected MATLAB: {config.magec.matlab_bin}")
    else:
        click.echo("  ⚠ MATLAB not found — set magec.matlab_bin in the config")
    if config.magec.solver_dir:
        click.echo(f"  Auto-detected MAGEC solver: {config.magec.solver_dir}")
    else:
        click.echo("  ⚠ MAGEC solver not found — set magec.solver_dir in the config")
    if config.sulfurx.path:
        click.echo(f"  Auto-detected SulfurX: {config.sulfurx.path}")
    else:
        click.echo("  ⚠ SulfurX not found — set sulfurx.path in the config")

    click.echo("\nEdit the file, then pass --config to load it.")


# ── list-models ───────────────────────────────────────────────────────

@main.command("list-models")
@click.option("--available-only", is_flag=True, default=False,
              help="Only show models whose dependencies are installed.")
def list_models_cmd(available_only):
    """List all registered model backends."""
    from volcatenate import list_models
    from volcatenate.backends import get_backend

    names = list_models(available_only=available_only)
    if not names:
        click.echo("No models registered.")
        return

    for name in names:
        try:
            backend = get_backend(name)
            status = "\u2713" if backend.is_available() else "\u2717"
        except Exception:
            status = "\u2717"
        click.echo(f"  {status}  {name}")


# ── saturation-pressure ──────────────────────────────────────────────

@main.command("saturation-pressure")
@click.argument("input_csv", type=click.Path(exists=True))
@click.option("-m", "--models", default="all",
              help="Comma-separated model names, or 'all'.")
@click.option("-o", "--output", default="saturation_pressures.csv",
              help="Output CSV path.")
@click.option("--output-dir", default=None,
              help="Working directory for intermediate files.")
@click.option("--config", "config_path", default=None,
              type=click.Path(exists=True),
              help="Path to a YAML config file.")
@click.option("--no-progress", is_flag=True, default=False,
              help="Disable progress bars.")
def saturation_pressure_cmd(input_csv, models, output, output_dir, config_path,
                            no_progress):
    """Calculate volatile saturation pressure for melt compositions."""
    from volcatenate import calculate_saturation_pressure

    model_list = [m.strip() for m in models.split(",")]
    config = _load_run_config(config_path, output_dir)
    if no_progress:
        config.show_progress = False

    click.echo(f"Reading compositions from {input_csv}")
    df = calculate_saturation_pressure(input_csv, models=model_list, config=config)

    df.to_csv(output, index=False)
    click.echo(f"\nResults saved to {output}")
    click.echo(f"  {len(df)} compositions \u00d7 {len(model_list)} models")


# ── degassing ─────────────────────────────────────────────────────────

@main.command("degassing")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("-m", "--models", default="all",
              help="Comma-separated model names, or 'all'.")
@click.option("-o", "--output-dir", default="degassing_output",
              help="Output directory for degassing path CSVs.")
@click.option("--config", "config_path", default=None,
              type=click.Path(exists=True),
              help="Path to a YAML config file.")
@click.option("--no-progress", is_flag=True, default=False,
              help="Disable progress bars.")
def degassing_cmd(input_file, models, output_dir, config_path, no_progress):
    """Run degassing path calculations for a single composition.

    INPUT_FILE can be a CSV (uses the first row) or a JSON file
    with composition fields.
    """
    from volcatenate import calculate_degassing
    from volcatenate.composition import read_compositions, composition_from_dict

    model_list = [m.strip() for m in models.split(",")]
    config = _load_run_config(config_path, output_dir)
    if no_progress:
        config.show_progress = False

    # Read composition
    if input_file.endswith(".json"):
        with open(input_file) as f:
            comp_data = json.load(f)
        comp = composition_from_dict(comp_data)
    else:
        comps = read_compositions(input_file)
        if not comps:
            click.echo("No compositions found in input file.")
            sys.exit(1)
        comp = comps[0]
        click.echo(f"Using first composition: {comp.sample}")

    click.echo(f"Running degassing for {comp.sample}...")
    results = calculate_degassing(comp, models=model_list, config=config)

    # Save each model's output
    os.makedirs(output_dir, exist_ok=True)
    for model_name, df in results.items():
        out_path = os.path.join(output_dir, f"{comp.sample}_{model_name}.csv")
        df.to_csv(out_path, index=False)
        click.echo(f"  Saved {model_name}: {out_path} ({len(df)} steps)")

    if not results:
        click.echo("No models produced output.")


if __name__ == "__main__":
    main()
