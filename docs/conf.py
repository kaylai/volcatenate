"""Sphinx configuration for volcatenate documentation."""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

# Make the package importable for autodoc, even when not pip-installed.
sys.path.insert(0, os.path.abspath("../src"))

# -- Project information -----------------------------------------------------

project = "volcatenate"
author = "Kayla Iacovino"
copyright = "2025, Kayla Iacovino"

try:
    release = _pkg_version("volcatenate")
except PackageNotFoundError:
    release = "0.3.0"
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
    "sphinx_copybutton",
]

# Auto-generate stub pages for autosummary entries.
autosummary_generate = True

# MyST: enable a small, useful set of extensions; keep core minimal.
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "smartquotes",
]
myst_heading_anchors = 3

# Napoleon: NumPy-style docstrings.
napoleon_google_docstring = False
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_use_rtype = True

# Autodoc defaults.
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}
autodoc_typehints = "description"
autodoc_member_order = "bysource"

# Intersphinx — stdlib + scientific Python.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
}

# File handling.
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "README.md"]

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_title = f"volcatenate {version}"
html_static_path = ["_static"]
templates_path = ["_templates"]

# Don't fail the build if _static is empty.
html_css_files: list[str] = []

# Copy-button: skip prompts in code blocks.
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: "
copybutton_prompt_is_regexp = True
