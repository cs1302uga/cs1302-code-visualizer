# Code Visualizer (`cs1302-code-visualizer`)

Create memory diagrams from Java programs for lectures, assignments, and other teaching materials.

![The main frame holds alice, which refers to a Person with age 42 and a name reference to the Alice string](demo.png)

## Install

Install [uv](https://docs.astral.sh/uv/) and Google Chrome. Python 3.13 or newer is required; uv can provision Python when installing the tool. The renderer uses headless Chrome through Selenium. Its first run may download browser driver components, a JDK, and the checksum-verified Java tracer, so allow network access and extra startup time.

Download the `.whl` file from the project's [GitHub releases](https://github.com/cs1302uga/cs1302-code-visualizer/releases). In the directory containing that file, install it with uv (replace the filename with the version you downloaded):

```sh
uv tool install ./cs1302_code_visualizer-0.18.0-py3-none-any.whl
code-visualizer --help
```

If the command is not found, run `uv tool update-shell`, then restart your shell.

## Create your first diagram

Save this as `Main.java`:

```java
public class Main {
  public static void main(String[] args) {
    Person alice = new Person("Alice", 42);
    System.out.println(alice.name());
  }
}

record Person(String name, int age) { }
```

Render the final captured state:

```sh
code-visualizer Main.java -o main.png
```

For editable vector artwork, use `code-visualizer Main.java --format SVG -o main.svg`.
SVG also supports all steps and batch rendering; see [SVG exports](docs/cli.md#svg-exports).

Open `main.png` and insert it into your teaching material. Use `--dpi 2` for a larger image. Single-file mode replaces existing output files; choose a new filename to retain an earlier image.

## Read the diagram

Start at a variable's reference dot and follow the arrowhead to its object. In
this example, `alice` refers to a `Person`; `age` contains `42`, while `name`
refers to the String `"Alice"`.

- Stack frames show method invocations and their visible variables. A label such
  as `main:5` includes source-line context, not an execution-step count.
- Heap labels such as `Person@92` show the runtime class and trace object ID.
  IDs identify shared objects; they are not memory addresses.
- Several references to one object are aliases. A returning arrow can form a
  cycle or self-reference; an arrow crossing is not a connection.
- `null` has no target arrow. Array indices identify elements regardless of
  whether the array is displayed horizontally or vertically.
- The active frame is highlighted. Blue references come from it or heap objects;
  muted references come from inactive frames, not necessarily unreachable objects.

See [reading memory diagrams](docs/reading-diagrams.md) for the visual key,
string styles, and how presentation options change what is visible.

Stack types share a left-aligned column, with variable names right-aligned beside
their value boxes. Type labels stay on one line, with stack/global declared-type
space reserved across supplied states or requested snapshots; heap-field types
do not widen that column. Variable-name space is reserved across a trace so longer
names appearing during playback do not move existing name and value columns.
Maps have an enclosing object border. Separate
String objects show `(length N)` using Java’s UTF-16 length. Arrows stop at target
boundaries and avoid arrowheads for different targets. Parallel shafts to different
targets stay separated. Aliases also use separate horizontal lanes away from their
target. Departures prefer clearance from box borders. Readable shaft crossings may remain.

## Accessibility

Both default palettes are tested for **at least 7:1 text contrast** (the WCAG 2.2
AAA text-contrast threshold) and **3:1 border/reference contrast** (the AA
non-text threshold). SVG exports include an accessible summary and full state
description; their labels remain selectable when viewed directly or inline.
PNG needs a text alternative supplied by the author.

These are criterion-specific features, not a claim of complete WCAG AA or AAA
conformance. Custom colors, embedding, and assistive-technology behavior require
review. See [accessibility and WCAG scope](docs/accessibility.md) for default
light/dark colors, criterion levels, SVG descriptions, and publishing guidance.

## Choose colors

```sh
code-visualizer Main.java --theme dark -o main-dark.png
```

Use `--theme light` or `--theme dark` for a fixed palette. To follow a website's theme selector, export SVG without `--theme` and embed its markup inline. Auto follows the system preference; PNG colors are fixed when rendered. See the [theme guide and light/dark examples](docs/themes.md).

## Choose execution steps

Capture a source line using `-b` (line numbers start at 1):

```sh
code-visualizer Main.java -b 4 -o line4.png
```

Choose an executable line. To inspect the sequence of captured states:

```sh
code-visualizer Main.java -a -o steps.png
```

This creates `steps.0.png`, `steps.1.png`, and so on, plus `steps.png` containing the last image. Execution steps can revisit the same source line, particularly in loops.

## Arrange arrays

```sh
code-visualizer Main.java -o vertical.png --array-orientation vertical
code-visualizer Main.java -o alternating.png --alternate-array-orientations
```

Use these options with a program containing arrays. See the [array layout guide and visual comparisons](docs/array-orientation/README.md) for multidimensional arrays and per-object overrides.

## Generate a collection of diagrams

Place Java sources in a `sources/` directory, then run:

```sh
code-visualizer --batch --input-dir sources --out-dir diagrams
```

Each file is traced as a separate program. Batch mode preserves relative directories and refuses to overwrite existing outputs unless `--force` is supplied. See the [CLI guide](docs/cli.md) for manifests, output templates, and failure handling.

## More documentation

- [Example gallery](examples/README.md): Java concepts and rendered diagrams.
- [CLI guide](docs/cli.md): detailed command usage and troubleshooting.
- [Reading diagrams](docs/reading-diagrams.md): frames, values, references, and object identity.
- [Accessibility](docs/accessibility.md): WCAG criterion levels, palettes, and text alternatives.
- [Reference arrows](docs/reference-routing/README.md): routing, text clearance, and a runnable example.
- [Visualization themes](docs/themes.md): colors, Auto mode, embedding, and contrast.
- [Python integration](HACKING.md): embed rendering in scripts and course builds.
- [Contributing](CONTRIBUTING.md): develop, test, and release the project.

## String presentation

Use `--string-style compact` for reference boxes followed by string literals,
`--string-style inline` for literals inside value boxes, or `--string-style default`
for separate string heap objects. The default is `default` for every renderer.

```sh
code-visualizer Main.java --string-style compact -o compact.svg
```

Python renderers accept `string_style="compact"`. The old rendering argument
`inline_strings` is deprecated; see the [string style guide](docs/string-style/README.md)
for migration, shared-string identity, and examples.
