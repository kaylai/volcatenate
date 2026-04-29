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
    release = "0.4.0"
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
    "nbsphinx",
    "sphinxcontrib.mermaid",
]

# Don't execute notebooks at build time; render them as authored. The
# example notebooks intentionally do not require every backend to be
# installed, so they will not always run cleanly on the docs builder.
nbsphinx_execute = "never"
nbsphinx_custom_formats: dict = {}
# A "Download notebook" link is injected at the top of every rendered
# notebook page. ``env.docname`` is the path of the current notebook
# without extension, so ``{{ env.docname.split('/')|last }}`` gives
# the filename. nbsphinx automatically copies the source ``.ipynb`` to
# the HTML output tree, and we point at it relative to the rendered
# page (``../_sources/<docname>.ipynb`` is the canonical location).
nbsphinx_prolog = r"""
{% set basename = env.docname.split('/')|last %}

.. raw:: html

    <div class="admonition note">
      <p class="admonition-title">Run this notebook locally</p>
      <p>Download <a class="reference download external" download
        href="{{ basename }}.ipynb"
      ><code class="docutils literal notranslate"><span class="pre">{{ basename }}.ipynb</span></code></a>
      and open it in Jupyter, JupyterLab, or VS Code to run the cells interactively. nbsphinx copies the source notebook to the output tree alongside this page, so the link above is a direct download.</p>
    </div>
"""

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
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "README.md", "**/README.md", "**/.ipynb_checkpoints"]

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
