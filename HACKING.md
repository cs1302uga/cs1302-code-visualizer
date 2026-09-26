# Integrating the renderer with Python

Use the renderer in course builds or other Python applications. For command-line use, see the [instructor guide](README.md); for changes to the renderer itself, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Install in your application

Use Python 3.13 or newer and the browser prerequisites in the [installation guide](README.md#install). Download a release wheel, then add it to your uv project, substituting its actual path:

```sh
uv add ./cs1302_code_visualizer-0.16.2-py3-none-any.whl
```

The following recipes run in order in one Python script, using `Main.java` from the instructor quickstart. Run the script with `uv run python your_script.py`.

## Render one image

```python
from pathlib import Path

from cs1302_code_visualizer import render_image, render_images, RenderingSession

java_source = Path("Main.java").read_text(encoding="utf-8")
image = render_image(java_source, timeout_secs=30)
Path("python-final.png").write_bytes(image)
```

`render_image` returns image bytes. It captures the state just before exit by default; use `breakpoint_line=4` to select a line, or `(4, 2)` to select an occurrence (occurrence numbers start at 1). It owns its browser and does not accept a session.

Pass `format="SVG"` to obtain UTF-8 SVG bytes with editable text and vector shapes:

```python
svg = render_image(java_source, format="SVG", dpi=2, timeout_secs=30)
Path("python-final.svg").write_bytes(svg)
```

The same format is supported by `render_images`, batch jobs, `generate_image`, and `generate_step_images`. For SVG, `dpi` scales display dimensions without changing the layout or `viewBox`. Fonts are not embedded; see the [SVG export contract](docs/cli.md#svg-exports) for font-substitution behavior.

## Select lines and repeated occurrences

```python
images = render_images(java_source, {3, 4}, timeout_secs=30)
for line, image in images.items():
    Path(f"python-line{line}.png").write_bytes(image)

occurrences = render_images(
    java_source, {4}, render_all_breakpoint_occurrences=True, timeout_secs=30
)
for line, frames in occurrences.items():
    for index, image in enumerate(frames):
        Path(f"python-line{line}-{index}.png").write_bytes(image)
```

Normally the result maps source lines to bytes and selects the last execution of each line. With `render_all_breakpoint_occurrences=True`, each value is a list of images in execution order. Do not assume every requested line appears: non-executable or unreached lines may not produce a snapshot.

## Configure layouts

```python
image = render_image(
    java_source,
    array_orientation="vertical",
    include_types=True,
    dpi=2,
    timeout_secs=30,
)
Path("python-layout.png").write_bytes(image)
```

Array settings also include `alternate_array_orientations` and `array_orientations={"42": "vertical"}`. Overrides use heap IDs from a trace, not Java variable names. They affect presentation and do not change trace-cache keys. See the [array guide](docs/array-orientation/README.md).

## Reuse browsers and cache traces

```python
with RenderingSession(max_browsers=2, cache_dir=Path(".cache/traces")) as session:
    images = render_images(java_source, {3, 4}, session=session, timeout_secs=30)
    larger = render_images(
        java_source, {3, 4}, dpi=2, session=session, timeout_secs=30
    )
    for line, image in larger.items():
        Path(f"python-large{line}.png").write_bytes(image)
```

A session reuses browsers. Trace caching is separate: omit `cache_dir` for no persistent cache; set `cache_traces=True` for memory-only caching. By default, every request executes Java again. Cache keys include execution arguments, JDK release identity, and tracer URL and checksum. Different breakpoint selections and occurrence settings remain distinct. Failed requests are not cached; damaged cache entries are regenerated.

A session leases browsers exclusively and keeps at most `max_browsers` alive across DPI settings. Reuse requires matching DPI, headless, and debug settings. Each render loads a fresh frontend document. Failed render or viewport reset discards the browser without retrying the request; the next request replaces it. The context manager closes browsers even after an exception. Sessions do not span processes or separate runs.

Persistent traces are not removed automatically:

```python
from cs1302_code_visualizer.session import prune_trace_cache

preview = prune_trace_cache(Path(".cache/traces"), max_age_days=30, dry_run=True)
print(preview)
```

Set `dry_run=False` to remove entries unused for the selected period, or delete the cache directory to force retracing.

## Render independent snapshots together

For existing JSON payloads that share rendering options, use
`generate_snapshot_images`:

```python
from pathlib import Path

from cs1302_code_visualizer import RenderingSession, generate_snapshot_images

payloads = [Path(name).read_text(encoding="utf-8") for name in ("first.json", "second.json")]
with RenderingSession(max_browsers=2) as session:
    images = generate_snapshot_images(payloads, format="SVG", theme="auto", session=session)
for index, image in enumerate(images):
    Path(f"snapshot-{index}.svg").write_bytes(image)
```

Each string is an independent payload and may contain a different program.
The result preserves input order, including repeated payloads. Empty input returns
an empty list without launching a browser. An error raises without returning a
partial list; callers may retry the individual payloads to isolate a failure.
All payloads in a call use the same options, including breakpoint selection and
`theme` (`light`, `dark`, `auto`, or omitted for adaptive output). Each image gets
its own tight crop; changing the batch order, membership, or cache-miss subset
does not change its framing.

The API keeps one browser lease and host document for the call. Subsequent payloads
load the unchanged renderer in fresh full-viewport frames, then discard those
frames. This preserves the font-loading timing and heap spacing of individual
images. It does not share a diagram's layout history between programs.
`generate_step_images` remains the API for chronological steps of one trace.
Singleton inputs and the `json-pre` visualizer use the individual-image path.
For parallel builds, submit bounded groups through the same `RenderingSession`;
one group occupies one browser until its images are complete.

## Handle failures and program input

```python
from cs1302_code_visualizer import CodeVisError, CodeVisualizerError

try:
    image = render_image(java_source, stdin="sample input\n", timeout_secs=30)
except (CodeVisError, CodeVisualizerError, OSError, ValueError) as exc:
    print(f"Could not render program: {exc}")
else:
    Path("python-input.png").write_bytes(image)
```

Use `stdin` or `stdin_file` to supply input to the Java program. Set a trace timeout appropriate to your build. Errors can arise during dependency installation, tracing, rendering, or file output; inspect chained exceptions when diagnosing failures. The exception families differ between APIs, and browser/dependency failures can also surface their underlying exceptions. Let unexpected failures fail your build.

## Other public APIs

- `BatchRenderJob` and `render_batch_images`: render multiple jobs and yield image mappings in input order, optionally using a shared session.
- `generate_trace`: produce a trace for a selected JDK and source.
- `generate_image`, `generate_step_images`, and `generate_snapshot_images`: render existing trace JSON, optionally with a session.
- `render_html`: produce an HTML embed from a trace.

See the exported APIs and docstrings in [the package](cs1302_code_visualizer/__init__.py), [browser driver](cs1302_code_visualizer/browser_driver.py), and [session module](cs1302_code_visualizer/session.py) for signatures and return types. For example, `help(render_images)` shows the installed version's parameter documentation.

## Visualization themes

Image APIs (`render_image`, `render_images`, `BatchRenderJob`, `generate_image`, and `generate_step_images`) accept `theme="light"`, `"dark"`, or `"auto"`. For a fixed dark SVG:

```python
svg = render_image(java_source, format="SVG", theme="dark", timeout_secs=30)
Path("python-dark.svg").write_bytes(svg)
```

Omit `theme` (or pass `None`) for a light standalone SVG that follows an ancestor's `data-theme` when embedded inline. Explicit Auto follows the viewing system's preference independently of the host's manual choice. Raster output captures the rendering browser's theme at export time and cannot switch afterward. Themes affect presentation, not trace-cache keys.

For an interactive embed, first create `trace.json` with `generate_trace < Main.java > trace.json` and load a matching frontend bundle. Assuming your site serves this checkout's built `vis-module.bundle.js` at `/assets/vis-module.bundle.js`:

```python
from cs1302_code_visualizer import render_html

trace = Path("trace.json").read_text(encoding="utf-8")
html = render_html(trace, bundle_url="/assets/vis-module.bundle.js")
Path("memory-embed.html").write_text(html, encoding="utf-8")
```

Insert this snippet into your page and set an ancestor, such as the page's `body`, to `data-theme="light"`, `"dark"`, or `"auto"`. Omit `theme` in `render_html` to follow that attribute. Pass `theme="dark"` or `theme="auto"` to override it for that instance. Without `bundle_url`, the helper uses the installed package version's GitHub release bundle URL; that release asset must be available.

See the [theme guide](docs/themes.md) for a complete static HTML recipe, a three-frame visual comparison, CSS color overrides, print behavior, and the scope of the contrast checks.
