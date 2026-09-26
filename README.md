# Code Visualizer (`cs1302-code-visualizer`)

Create memory diagrams from Java programs for lectures, assignments, and other teaching materials.

![Java memory diagram showing a Person record](demo.png)

## Install

Install [uv](https://docs.astral.sh/uv/) and Google Chrome. Python 3.13 or newer is required; uv can provision Python when installing the tool. The renderer uses headless Chrome through Selenium. Its first run may download browser driver components, a JDK, and the checksum-verified Java tracer, so allow network access and extra startup time.

Download the `.whl` file from the project's [GitHub releases](https://github.com/cs1302uga/cs1302-code-visualizer/releases). In the directory containing that file, install it with uv (replace the filename with the version you downloaded):

```sh
uv tool install ./cs1302_code_visualizer-0.16.1-py3-none-any.whl
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
- [Visualization themes](docs/themes.md): colors, Auto mode, embedding, and contrast.
- [Python integration](HACKING.md): embed rendering in scripts and course builds.
- [Contributing](CONTRIBUTING.md): develop, test, and release the project.
