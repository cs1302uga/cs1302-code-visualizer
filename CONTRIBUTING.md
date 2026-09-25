# Contributing

For generating teaching diagrams, start with [README.md](README.md). For using the Python API in another project, see [HACKING.md](HACKING.md).

## Set up a checkout

Install uv, Node.js 22 with npm, and Google Chrome. Python requires version 3.13 or newer. The release workflow tests Python 3.13 with JDK 21 and 25; the automatic JDK installer is configured separately in `pyproject.toml`.

```sh
git clone https://github.com/cs1302uga/cs1302-code-visualizer.git
cd cs1302-code-visualizer
uv sync --all-groups
npm --prefix cs1302_code_visualizer/frontend ci
make build-frontend
uv run code-visualizer --help
```

First rendering may download a JDK, the pinned tracer, and Selenium browser driver components. `make install` provides an alternative dependency setup using npm install. `make install-sys-deps` installs additional configured tools for related workflows; inspect [its configuration](pyproject.toml) before using it.

## Architecture

Java source passes through three components:

1. [Trace generator](cs1302_code_visualizer/trace_generator.py): provisions and verifies the tracer, locates or installs Java, and executes the Java source to produce trace JSON.
2. [Frontend](cs1302_code_visualizer/frontend): turns traces into memory diagrams using the adapted OnlinePythonTutor visualizer.
3. [Browser driver](cs1302_code_visualizer/browser_driver.py): loads the frontend in headless Chrome and captures images.

The [unified CLI](cs1302_code_visualizer/cli.py) handles source inputs and output paths. [Rendering sessions](cs1302_code_visualizer/session.py) own reusable browsers and optional trace caches. The [Python integration guide](HACKING.md) describes public lifecycle contracts.

## Make and validate changes

```sh
make watch-frontend
```

Run the watcher while changing frontend code, or run `make build-frontend` before testing screenshots. Python edits are available through the uv environment's editable installation.

```sh
make check
make test-examples
```

`make check` runs Ruff, Basedpyright, all Markdown checks, Python tests, and frontend tests. Python tests enforce 100% coverage. `make test-examples` exercises the Java examples and retains output artifacts; review generated changes before committing. Run `make deptry` when changing Python dependencies and `make build` to validate distributable builds.

For focused work, use `make test-py`, `make test-frontend`, `make lint`, or `make typecheck`. Python formatting and lint rules are in [pyproject.toml](pyproject.toml), including Google-style docstrings. `make format-py` applies Ruff formatting and fixes.

## Documentation requirements

Every repository-owned `.md` file must pass Markdown linting, including existing guides and example READMEs. Only dependency and generated build directories are excluded. Use the shared [.markdownlint.yaml](.markdownlint.yaml) configuration; do not suppress rules to avoid repairing documentation.

```sh
make lint-docs
```

This runs Markdown linting and checks local link/image destinations across tracked and non-ignored untracked Markdown files. Local file checks do not validate heading fragments or external URLs. The same command runs in CI and is required for the release job. To apply automatic Markdown formatting fixes, run `node scripts/check_docs.cjs --fix`, then inspect the diff and rerun the check.

Keep runnable commands aligned with the implementation. When changing documented behavior, update the relevant audience guide and run affected examples. Maintain links when moving documentation.

## Rendering tests and benchmarks

Rendering tests can request the `rendering_session` fixture and pass it to `generate_image` or `generate_step_images`. The fixture owns one browser per pytest worker and does not cache traces. Tests touching raw WebDriver, browser configuration, or lifecycle behavior must own fresh browsers. Each session render reloads the frontend and resets viewport emulation.

Browser reuse preserves the two-pass fitting behavior, minimum browser dimensions, and connector placement while avoiding native resize stalls. Compare fresh and reused captures in the same Chrome environment:

```sh
uv run python -m scripts.benchmark_rendering small-trace-examples/example0/Driver.java.json --requests 6
uv run python -m scripts.benchmark_cli_batch --num-examples 6
```

The rendering benchmark checks dimensions and decoded pixels and reports time and Chrome launches. The CLI benchmark compares sequential and batch configurations; `--skip-sequential` reports speedups as `N/A`.

## Maintainer tasks

### Update the tracer

The tracer URL and SHA-256 pin live under `tool.cs1302-code-visualizer` in [pyproject.toml](pyproject.toml). `make update-tracer` invokes the update helper; inspect its resulting changes, run validation, and review the [tracer upgrade notes](docs/tracer-v3.1.2-upgrade.md).

The wheel includes this configuration as `_tracer.toml`. The installer executes a cached tracer only when its checksum matches the pin. A matching cache works offline, even if a refresh fails. A missing, unreadable, or mismatched cache requires a verified replacement. Failed downloads preserve the old file but do not authorize its execution. Missing or invalid metadata requires repairing the configuration or reinstalling the package; there is no checksum override.

### Build and release

Update the package version in `pyproject.toml`, verify the tracer pin, and run `make check` and `make build`. Check that the wheel contains the frontend build and tracer configuration, then exercise the installed wheel's quickstart outside the checkout.

The [release workflow](.github/workflows/release.yml) runs on main-branch pushes, pull requests targeting main, and tag pushes. A tag push triggers publication after validation; it uploads the frontend bundles and Python distributions to a GitHub release. Follow the project's existing tag naming convention. The workflow does not publish to PyPI.
