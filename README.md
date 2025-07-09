# cs1302-book-visualizer

## Usage

This project visualizes the final state of the Java world just before the main method returns. Write
the code you want visualized and save it to a file (e.g. `In.java`). Then, run the visualizer chain
(program -> trace -> screengrab -> png).

```console
$ cat In.java | uv run trace_generator | uv run browser_driver > out.png
```

This can also be done in one step using the command below:

```console
$ cat In.java | uv run render_image > out.png
```
