# Command-line guide

Start with the [instructor quickstart](../README.md). Commands below assume an installed `code-visualizer`; in a checkout, prefix commands with `uv run`.

## Single-program inputs and outputs

```sh
code-visualizer Main.java -o main.png
code-visualizer -i Main.java -o main.png
code-visualizer < Main.java > main.png
code-visualizer Main.java -a -o steps.png
```

Use one source per single-program invocation. Without an input path, source is read from standard input. Without `-o`, a single image is written to standard output. `-a` requires `-o` and produces numbered images plus the last image at the requested path.

Single-program mode creates parent directories and replaces existing files. Batch overwrite protection, output templates, and rollback apply only to batch mode.

## Select and format images

| Option | Behavior |
| --- | --- |
| `-b N`, `--breakpoint N` | Select a source line; repeat to request multiple lines. |
| `-a`, `--all-steps` | Trace and render all execution steps. |
| `--format PNG` | Select a raster encoding or standalone `SVG`; default is PNG. Match explicit filename extensions to the encoding. |
| `--dpi 2` | Scale raster resolution or SVG display dimensions; default is 1. |
| `--no-types` | Hide type tags. |
| `--text-memory-labels` | Replace reference arrows with text labels. |
| `--strip-type-prefix PREFIX` | Strip a type-name prefix; repeat as needed. |
| `--array-orientation horizontal\|vertical` | Set base array orientation. |
| `--alternate-array-orientations` | Alternate layout with array dimensionality. |
| `--array-orientation-for ID=ORIENTATION` | Override a heap object's orientation; repeat as needed. |

Without `-a`, single-program mode emits one image, even when several breakpoints are supplied. Batch mode also emits one image per job without `-a`. Use the [Python API](../HACKING.md) for explicit line-to-image mappings. Source lines and execution step indices are distinct.

See the [array guide](array-orientation/README.md) for override precedence and examples. `code-visualizer --help` is the installed version's complete option list.

## SVG exports

```sh
code-visualizer Main.java --format SVG -o main.svg
code-visualizer Main.java --format SVG -a -o steps.svg
code-visualizer --batch --input-dir sources --format SVG --out-dir diagrams
```

SVG exports contain editable text, shapes, and reference paths, with no embedded HTML or raster screenshots. Format names are case-insensitive. Single images, all execution steps, batch jobs, and the Python image APIs support SVG with the same array and labeling options as PNG.

The SVG uses the browser's diagram layout. `--dpi 2` doubles its declared width and height while leaving the `viewBox`, geometry, and proportions unchanged. SVG text remains selectable and editable when opened directly in a browser or embedded inline in HTML. An HTML `<img>` displays the SVG as an image and does not allow selecting its internal text. Fonts are not embedded: browsers and Inkscape may substitute fonts, and unsupported glyphs such as emoji can differ or be absent. Text is fitted to the measured label bounds to preserve layout; exact glyph appearance is not guaranteed.

Each export includes an accessible summary and a full text description of the rendered state. The description lists stack frames and variables before heap objects, names reference targets, and lists each object once, including cycles and shared references. It follows the selected step and visible labels; hidden fields are omitted. The comparison gallery provides the same information in an expandable **Text description** panel with headings and lists. VoiceOver with Safari still requires manual acceptance testing.

Use `.svg` for explicit SVG output paths. An explicit `-o` path or custom pattern is used exactly as supplied; its extension does not select or override the encoding. See the [SVG comparison gallery instructions](svg-gallery.md) for reproducible visual checks.

## Batch inputs

```sh
code-visualizer --batch Main.java Other.java --out-dir diagrams
code-visualizer --batch --input-dir sources --out-dir diagrams
code-visualizer --batch -i manifest.ndjson --out-dir diagrams --output-pattern '{id}.{step}.png'
```

Each input is traced independently. Directory scans recurse through `.java` files and preserve paths relative to the scan root. Positional files retain their supplied parent path for templates. Absolute output paths bypass `--out-dir`; use relative inputs or an explicit pattern to keep outputs under that directory.

A manifest has one JSON object per nonblank line:

```json
{"id":"lesson-one","source":"class Main { public static void main(String[] args) { int n = 1; System.out.println(n); } }"}
```

Supported job fields are `id`, `source`, `breakpoints` (an array of line numbers), `array_orientation`, `alternate_array_orientations`, and `array_orientations`. Omitted IDs use `job_` plus the zero-based manifest line index. Empty or omitted breakpoints inherit CLI breakpoints. Array settings inherit CLI defaults; per-object maps merge with job entries taking precedence. Invalid array settings reject the manifest before any job executes. Supply a manifest file: batch mode currently does not read a manifest from `-i -`.

## Output paths

`--output-pattern` controls batch image names and `--trace-pattern` saves intermediate trace JSON. Relative destinations are placed under `--out-dir` when supplied.

| Placeholder | Value |
| --- | --- |
| `{id}` | Manifest job ID or source stem. |
| `{dirname}` | Source parent directory; empty for manifest jobs. |
| `{filename}` | Source filename, including extension; empty for manifest jobs. |
| `{basename}` | Source stem, or job ID for manifest jobs. |
| `{ext}` | Source extension, usually `java`. |
| `{step}` | Image index, or `final` for a single image. |
| `{line}` | Source line prefixed with `L`; requires frame metadata. |
| `{format}` | Lowercase output format, or `json` for traces. |

The default image pattern is `{dirname}/{basename}.{format}`, or `{dirname}/{basename}.{step}.{format}` for all steps or CLI breakpoints. Thus `--format SVG` produces `.svg` filenames and the default PNG format still produces `.png`. Manifest jobs should use an explicit `{id}` pattern to distinguish programs.

```sh
code-visualizer --batch -a Main.java --out-dir diagrams \
  --output-pattern '{basename}.step{step}.png' \
  --trace-pattern '{basename}.json'
```

Multiple images require `{step}` or `{line}` in the image pattern. Loops can repeat line numbers, so use `{step}` to distinguish occurrences. Duplicate destinations within a job are rejected even with `--force`. Use unique job IDs and patterns across jobs; `--force` permits later jobs to replace earlier files.

## Batch execution and failures

- `--workers N` configures tracer workers (default 1); `--browsers N` configures the browser pool (default 2). The CLI currently iterates jobs in order; these settings do not promise parallel execution of all input files.
- `--keep-going` attempts later jobs after a handled job failure. The command still exits unsuccessfully if any job fails.
- `--force` permits overwriting batch destinations. Without it, existing outputs cause a job failure.
- Parent directories are created automatically. Outputs are staged beside their destinations and published using per-file atomic replacement. Publication failure rolls back earlier replacements within the job; this is not a crash-atomic transaction across files or jobs. Rollback errors report retained recovery backups.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Command not found | Run `uv tool update-shell`, restart the shell, and check the wheel installation. |
| Initial download failure | Check network access and retry. A verified tracer cache can work offline; an invalid cache cannot. |
| Browser startup failure | Check Chrome installation and driver compatibility; inspect the underlying Selenium error. |
| Missing selected state | Select an executable, reached source line, or render all steps to inspect the trace. |
| Existing batch destination | Choose another output directory or intentionally pass `--force`. |
| Repeated template destination | Include `{step}`; `{line}` alone is insufficient for loops. |

## Specialized commands

```sh
generate_trace < Main.java > trace.json
generate_visualization < trace.json > trace.png
list_breakpoints < Main.java
render_image < Main.java > rendered.png
render_html < trace.json > embed.html
```

These utilities have their own options and defaults; use each command's `--help`. For example, program input (`--stdin` or `--stdin-file`) is available through the lower-level tracing/rendering tools and Python APIs, not the unified CLI. HTML embedding and bundle options are described in the [array guide](array-orientation/README.md).

## Color themes

Use `--theme light`, `--theme dark`, or `--theme auto` with `code-visualizer`,
`generate_visualization`, `render_image`, or `render_html`. Batch manifests may
set `"theme": "dark"` per job, overriding the command's theme.

```sh
uv run code-visualizer examples/example0/Driver.java --theme dark --format SVG -o driver-dark.svg
```

With no theme option, standalone exports use light colors and inline SVG markup
follows the host's `data-theme` attribute. Auto follows the system preference.
See [Visualization themes](../HACKING.md#visualization-themes) for embedding and
CSS overrides.
