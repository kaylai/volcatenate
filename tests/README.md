# volcatenate test suite

## Running the tests

```
pytest tests/           # everything
pytest tests/ -m '...'  # specific markers (none defined yet)
```

The full suite takes ~100s on a developer laptop. Most of that is real backend invocations (SulfurX, MAGEC, EVo) at deliberately tiny problem sizes; the rest is sub-second config / converter / unit work.

## Test-suite SulfurX version

volcatenate wraps several volcanic-degassing models that are not pip-installable — they live as plain git checkouts (SulfurX) or supplementary-material files (MAGEC) at user-configured paths. To keep test results reproducible across developer machines and CI, the test suite **always runs SulfurX-touching tests against a specific tagged release** (currently `v.1.2`) rather than against whatever the developer's local checkout happens to point at.

### How the fixture works

The single source of truth is in [`src/volcatenate/versions.py`](../src/volcatenate/versions.py):

```python
TESTED_SULFURX_VERSION: str = "v.1.2"
TESTED_SULFURX: set[str] = {TESTED_SULFURX_VERSION}
KNOWN_SULFURX: dict[str, str] = {
    "4c36ee0d1babdaaeaf915ba359bb9006f9c76741": "v.1.2",
    ...
}
```

The session-scoped `sulfurx_tested_path` fixture in [`tests/conftest.py`](conftest.py) does the following at the start of each pytest session:

1. Locate the developer's existing SulfurX checkout via `SULFURX_PATH` env var or `_find_sulfurx()` auto-discovery.
2. Verify `TESTED_SULFURX_VERSION` resolves to a known tag in that checkout.
3. Assert the SHA the local tag points to matches the SHA recorded in `KNOWN_SULFURX` — catches the (rare) case where upstream force-pushes a tag.
4. `git worktree add --detach <tmp> <tag>` to materialize the tested-version source in a temp directory.
5. Purge cached SulfurX modules from `sys.modules` and any stale SulfurX entries from `sys.path` so re-imports come from the tested-version worktree.
6. Yield the worktree path; tests set `cfg.sulfurx.path = sulfurx_tested_path`.
7. On teardown: restore `sys.path`, purge again, remove the worktree.

The worktree creation is sub-second on local SSDs.

Tests that touch SulfurX (e.g. [`test_sulfurx_montecarlo.py`](test_sulfurx_montecarlo.py)) consume the fixture as a regular pytest argument:

```python
def test_monte_carlo_writes_expected_csvs(tmp_path, sulfurx_tested_path):
    config.sulfurx.path = sulfurx_tested_path  # tested version, not auto-discovered
    ...
```

Pure config-shape tests that don't actually run SulfurX (e.g. [`test_sulfurx_config.py`](test_sulfurx_config.py)) don't need the fixture and run regardless of whether SulfurX is installed.

### Why a fixed tested version?

- **Reproducibility.** Every developer and CI runner sees byte-identical SulfurX source for any given volcatenate commit. No "works on my machine" because of an upstream rebase.
- **Wrapper-not-fork philosophy.** We don't vendor SulfurX into this repo. We don't publish it to PyPI on volcatenate's behalf. We just point tests at a tagged release.
- **Doesn't constrain dev work.** You can keep your local SulfurX checkout on any branch / commit you like for your own development. The fixture only operates against the tagged version.

### Setup: one-time per development machine

```bash
# Clone SulfurX (auto-discovery looks for it under ~/PythonGit/Volatile_Models/Sulfur_X
# and a few other common locations — see _find_sulfurx() in src/volcatenate/config.py).
git clone https://github.com/kaylai/Sulfur_X.git ~/PythonGit/Volatile_Models/Sulfur_X
cd ~/PythonGit/Volatile_Models/Sulfur_X
git fetch --tags
```

If SulfurX lives somewhere else, set `SULFURX_PATH=/your/path/to/Sulfur_X` in your shell.

If a SulfurX-touching test skips with `"missing tag 'v.1.2'"`, run `git -C $SULFURX_PATH fetch --tags` and re-run the test.

### Updating to a new tested SulfurX release

When SulfurX cuts a new release that we want to validate against (let's say `v.1.3`):

1. Add the new SHA → tag mapping to `KNOWN_SULFURX` in [`src/volcatenate/versions.py`](../src/volcatenate/versions.py). Get the SHA via `gh api repos/sdecho/Sulfur_X/tags` or `git -C $SULFURX_PATH rev-parse v.1.3`.
2. Bump `TESTED_SULFURX_VERSION` to `"v.1.3"` (the `TESTED_SULFURX` set updates automatically since it derives from the constant).
3. Run the full suite. If anything regresses, that's the wrapper's job to handle — file an issue or fix in `src/volcatenate/backends/sulfurx.py`.
4. Update the SulfurX-version callout in [`docs/config_options.md`](../docs/config_options.md) (search for "Validated against SulfurX").
5. Commit all four changes together.

### Skip behavior

The `sulfurx_tested_path` fixture **skips** (does not fail) when:

- SulfurX is not found via `SULFURX_PATH` or auto-discovery.
- The tested-version tag is not present in the local checkout (developer hasn't run `git fetch --tags`).

It **fails loudly** when:

- The tested-version tag's SHA in the local checkout does not match the SHA recorded in `KNOWN_SULFURX` (upstream force-pushed the tag, or `versions.py` is wrong).
- `git worktree add` fails for any other reason.

### CI

CI just needs to clone SulfurX once and fetch tags before running pytest:

```bash
git clone --depth=1 --no-single-branch https://github.com/kaylai/Sulfur_X.git $SULFURX_PATH
git -C $SULFURX_PATH fetch --tags
pytest tests/
```

The fixture handles the worktree from there.

## What about MAGEC, EVo, VolFe?

- **MAGEC** is distributed as supplementary material to Sun & Yao (2024) EPSL — it is not a git repo, so version detection happens via SHA256 of the compiled `.p` solver file. The single tested version is recorded in `TESTED_MAGEC` in `versions.py`. Test gating happens via per-test `pytest.skip` when the path or MATLAB binary is unavailable; there is no worktree-style fixture because there is no upstream git repo to check a tag out of.
- **EVo** is a `pip install -e`-able Python package — version selection happens via `pyproject.toml` extras, not via a fixture.
- **VolFe** likewise.

If a SulfurX-style worktree fixture later becomes useful for one of these, the pattern in `tests/conftest.py` generalizes — extract the SulfurX-specific bits into a `_use_tested_git_backend(repo_path, tag, expected_sha, modules_to_purge)` helper and reuse it.
