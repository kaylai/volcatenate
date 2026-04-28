# Building the docs locally

The volcatenate documentation is built with [Sphinx](https://www.sphinx-doc.org/)
and is published on [Read the Docs](https://readthedocs.org/).

## Install the doc dependencies

```bash
pip install -r docs/requirements.txt
pip install -e .   # so autodoc can import volcatenate
```

## Build

From the repo root:

```bash
sphinx-build -b html docs docs/_build/html
```

Or, if `make` is available:

```bash
cd docs && make html
```

Open `docs/_build/html/index.html` in a browser to preview.

## Read the Docs

The build is configured by `.readthedocs.yaml` at the repo root. It uses
Python 3.11, installs `docs/requirements.txt` and the package itself,
then runs `sphinx-build` against `docs/conf.py`.
