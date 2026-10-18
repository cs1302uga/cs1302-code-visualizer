"""Unified CLI class-path parsing, forwarding, and real dependency access."""

import io
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cs1302_code_visualizer import cli, trace_generator
from cs1302_code_visualizer.errors import CodeVisTraceGeneratorError

SOURCE = """import dependencies.DirectoryValue;
import dependencies.JarValue;
public class Main {
    public static void main(String[] args) {
        System.out.println(DirectoryValue.get() + JarValue.get());
    }
}
"""
MODES = ["file", "stdin", "files", "directory", "manifest"]


def prepare_input(mode: str, tmp_path: Path, source: str) -> tuple[list[str], list[Path]]:
    output_dir = tmp_path / "output"
    if mode in {"file", "stdin"}:
        output = output_dir / "Main.png"
        if mode == "stdin":
            return ["--input", "-", "--output", str(output)], [output]
        source_path = tmp_path / "Main.java"
        source_path.write_text(source, encoding="utf-8")
        return [str(source_path), "--output", str(output)], [output]

    arguments = [
        "--batch",
        "--out-dir",
        str(output_dir),
        "--output-pattern",
        "{id}.png",
        "--trace-pattern",
        "{id}.json",
    ]
    if mode == "manifest":
        manifest = tmp_path / "jobs.ndjson"
        manifest.write_text(
            "\n".join(json.dumps({"id": name, "source": source}) for name in ["one", "two"]),
            encoding="utf-8",
        )
        return [*arguments, "--input", str(manifest)], [
            output_dir / "one.png",
            output_dir / "two.png",
        ]

    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    sources = [source_dir / "Main.java", source_dir / "Other.java"]
    for path in sources:
        path.write_text(source.replace("class Main", f"class {path.stem}"), encoding="utf-8")
    inputs = ["--input-dir", str(source_dir)] if mode == "directory" else [str(p) for p in sources]
    return [*arguments, *inputs], [output_dir / f"{path.stem}.png" for path in sources]


def reject_batch_worker(*args, **kwargs):
    pytest.fail("Explicit class paths must reach the one-shot tracer, not a batch worker")


@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("values", [None, ["first path", "libs/*.jar", "", "-leading.jar"]])
def test_class_path_parser_preserves_repeated_values(monkeypatch, batch, values):
    handler = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "run_batch_cli" if batch else "run_single_cli", handler)
    arguments = ["--batch"] if batch else []
    arguments.extend(f"--class-path={value}" for value in values or [])

    cli.main(arguments)

    assert handler.call_args.args[0].class_path == values


def test_class_path_requires_a_value(monkeypatch, capsys):
    handler = MagicMock()
    monkeypatch.setattr(cli, "run_single_cli", handler)

    with pytest.raises(SystemExit) as error:
        cli.main(["--class-path"])

    assert error.value.code == 2
    assert "--class-path: expected one argument" in capsys.readouterr().err
    handler.assert_not_called()


@pytest.mark.parametrize("mode", MODES)
def test_class_path_values_reach_every_cli_job_unchanged(tmp_path, monkeypatch, mode):
    values = [
        "dependencies with spaces/first.jar",
        f"first{os.pathsep}{os.pathsep}second{os.pathsep}",
        "libs/*.jar",
        "",
        "-leading.jar",
    ]
    arguments, outputs = prepare_input(mode, tmp_path, SOURCE)
    generate = MagicMock(return_value='{"trace": []}')
    monkeypatch.setattr(trace_generator, "ensure_jdk_installed", lambda: Path("/jdk"))
    monkeypatch.setattr(trace_generator, "ensure_code_tracer_installed", lambda: None)
    monkeypatch.setattr(trace_generator, "generate_trace", generate)
    monkeypatch.setattr("cs1302_code_visualizer.session.BatchTracerClient", reject_batch_worker)
    monkeypatch.setattr(cli.browser_driver, "generate_image", lambda *args, **kwargs: b"image")
    monkeypatch.setattr("sys.stdin", io.StringIO(SOURCE))

    cli.main([*arguments, *(f"--class-path={value}" for value in values)])

    assert generate.call_count == len(outputs)
    for call in generate.call_args_list:
        assert call.kwargs["extra_tracer_args"] == [f"--class-path={value}" for value in values]
    assert all(output.read_bytes() == b"image" for output in outputs)


@pytest.fixture(scope="module")
def binary_dependencies(tmp_path_factory):
    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()
    root = tmp_path_factory.mktemp("binary dependencies with spaces")
    directory = root / "compiled classes"
    jar_classes = root / "jar classes"
    directory.mkdir()
    jar_classes.mkdir()
    for name, value, destination in [
        ("DirectoryValue", 19, directory),
        ("JarValue", 23, jar_classes),
    ]:
        source = root / f"{name}.java"
        source.write_text(
            "package dependencies;\n"
            f"public class {name} {{\n"
            f"    public static int get() {{ return {value}; }}\n"
            "}\n",
            encoding="utf-8",
        )
        subprocess.run(
            [str(java_home / "bin" / "javac"), "-d", str(destination), str(source)],
            capture_output=True,
            text=True,
            check=True,
        )
    jar = root / "library with spaces.jar"
    subprocess.run(
        [
            str(java_home / "bin" / "jar"),
            "--create",
            "--file",
            str(jar),
            "-C",
            str(jar_classes),
            ".",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return directory, jar


@pytest.fixture
def capture_real_traces(monkeypatch):
    traces = []

    def render(trace_text, **kwargs):
        trace = json.loads(trace_text)
        assert trace["trace"][-1]["stdout"] == "42\n"
        assert all(frame.get("event") != "uncaught_exception" for frame in trace["trace"])
        traces.append(trace)
        return b"dependency image"

    monkeypatch.setattr(cli.browser_driver, "generate_image", render)
    monkeypatch.setattr("cs1302_code_visualizer.session.BatchTracerClient", reject_batch_worker)
    return traces


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("combined", [False, True], ids=["repeated", "native-separator"])
def test_real_cli_loads_directory_and_jar_dependencies(
    tmp_path, monkeypatch, binary_dependencies, capture_real_traces, mode, combined
):
    arguments, outputs = prepare_input(mode, tmp_path, SOURCE)
    directory, jar = binary_dependencies
    values = (
        [os.pathsep.join([str(directory), str(jar)])] if combined else [str(directory), str(jar)]
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(SOURCE))

    cli.main([*arguments, *(f"--class-path={value}" for value in values)])

    assert len(capture_real_traces) == len(outputs)
    assert all(output.read_bytes() == b"dependency image" for output in outputs)
    if mode in {"files", "directory", "manifest"}:
        for output in outputs:
            trace = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            assert trace["trace"][-1]["stdout"] == "42\n"


def test_real_cli_expands_quoted_jar_glob(
    tmp_path, monkeypatch, binary_dependencies, capture_real_traces
):
    arguments, outputs = prepare_input("stdin", tmp_path, SOURCE)
    directory, jar = binary_dependencies
    monkeypatch.setattr("sys.stdin", io.StringIO(SOURCE))

    cli.main([
        *arguments,
        "--class-path",
        str(directory),
        "--class-path",
        str(jar.parent / "*.jar"),
    ])

    assert len(capture_real_traces) == 1
    assert outputs[0].read_bytes() == b"dependency image"


@pytest.mark.parametrize("partial_class_path", [False, True], ids=["absent", "missing-jar"])
def test_missing_dependency_does_not_render_single_output(
    tmp_path, monkeypatch, binary_dependencies, partial_class_path
):
    arguments, outputs = prepare_input("file", tmp_path, SOURCE)
    directory, _ = binary_dependencies
    render = MagicMock()
    monkeypatch.setattr(cli.browser_driver, "generate_image", render)

    with pytest.raises(CodeVisTraceGeneratorError) as error:
        cli.main([*arguments, *(["--class-path", str(directory)] if partial_class_path else [])])

    assert "JarValue" in error.value.stderr
    render.assert_not_called()
    assert not outputs[0].parent.exists()


@pytest.mark.parametrize("invalid_entry", ["missing dependency.jar", "unmatched-*.jar"])
def test_invalid_class_path_does_not_publish_output(
    tmp_path, monkeypatch, binary_dependencies, invalid_entry
):
    arguments, outputs = prepare_input("file", tmp_path, SOURCE)
    directory, jar = binary_dependencies
    invalid_path = tmp_path / invalid_entry
    render = MagicMock()
    monkeypatch.setattr(cli.browser_driver, "generate_image", render)

    with pytest.raises(CodeVisTraceGeneratorError) as error:
        cli.main([
            *arguments,
            "--class-path",
            str(directory),
            "--class-path",
            str(jar),
            "--class-path",
            str(invalid_path),
        ])

    assert error.value.exit_status != 0
    assert invalid_entry in error.value.stderr
    assert str(tmp_path) in error.value.stderr
    render.assert_not_called()
    assert not outputs[0].parent.exists()


@pytest.mark.parametrize("keep_going", [False, True])
def test_missing_dependency_batch_failure_respects_keep_going(
    tmp_path, binary_dependencies, capture_real_traces, capsys, keep_going
):
    directory, _ = binary_dependencies
    valid_source = SOURCE.replace("import dependencies.JarValue;\n", "").replace(
        "JarValue.get()", "23"
    )
    manifest = tmp_path / "jobs.ndjson"
    manifest.write_text(
        "\n".join([
            json.dumps({"id": "bad", "source": SOURCE}),
            json.dumps({"id": "good", "source": valid_source}),
        ]),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    arguments = [
        "--batch",
        "--input",
        str(manifest),
        "--out-dir",
        str(output_dir),
        "--output-pattern",
        "{id}.png",
        "--trace-pattern",
        "{id}.json",
        "--class-path",
        str(directory),
    ]

    with pytest.raises(SystemExit) as error:
        cli.main([*arguments, *(["--keep-going"] if keep_going else [])])

    assert error.value.code == 1
    assert "Job 'bad' failed" in capsys.readouterr().err
    assert not (output_dir / "bad.png").exists()
    assert not (output_dir / "bad.json").exists()
    assert len(capture_real_traces) == int(keep_going)
    if keep_going:
        assert sorted(path.name for path in output_dir.iterdir()) == ["good.json", "good.png"]
        assert (output_dir / "good.png").read_bytes() == b"dependency image"
    else:
        assert not output_dir.exists()
