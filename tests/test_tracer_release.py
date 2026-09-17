"""Integration contracts for the pinned tracer and its distributed configuration."""

import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cs1302_code_visualizer import trace_generator
from cs1302_code_visualizer.errors import CodeVisTraceGeneratorError, TracerDownloadError


def test_wheel_preserves_tracer_pin(tmp_path):
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist")],
        cwd=root,
        check=True,
        capture_output=True,
    )
    installed = tmp_path / "installed"
    with zipfile.ZipFile(next((tmp_path / "dist").glob("*.whl"))) as wheel:
        wheel.extractall(installed)
    expected = trace_generator.read_tracer_url_and_sum_from_toml()
    env = dict(os.environ, PYTHONPATH=str(installed))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; from pathlib import Path; "
                "from cs1302_code_visualizer import trace_generator as t; "
                "assert Path(t.__file__).is_relative_to(Path.cwd()); "
                "print(json.dumps(t.read_tracer_url_and_sum_from_toml()))"
            ),
        ],
        cwd=installed,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert expected is not None
    assert json.loads(result.stdout) == list(expected)


@pytest.fixture
def outdated_cache(tmp_path, monkeypatch):
    jar = tmp_path / "code-tracer.jar"
    jar.write_bytes(b"old release")
    (tmp_path / "code_tracer_dl_headers.json").write_text(
        json.dumps({"Last-Modified": "Wed, 16 Sep 2026 00:00:00 GMT"})
    )
    monkeypatch.setattr(trace_generator, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        trace_generator,
        "read_tracer_url_and_sum_from_toml",
        lambda: ("https://example.test/new.jar", hashlib.sha256(b"new release").hexdigest()),
    )
    return jar


@pytest.mark.parametrize("update_existing", [False, True])
def test_outdated_cache_is_rejected_offline(outdated_cache, monkeypatch, update_existing):
    sock = MagicMock()
    sock.return_value.connect.side_effect = OSError("offline")
    monkeypatch.setattr(trace_generator.socket, "socket", sock)
    with pytest.raises(TracerDownloadError, match="checksum"):
        trace_generator.ensure_code_tracer_installed(update_existing=update_existing)
    assert outdated_cache.read_bytes() == b"old release"


@pytest.mark.parametrize("status", [200, 304])
def test_outdated_cache_does_not_reuse_download_headers(outdated_cache, monkeypatch, status):
    monkeypatch.setattr(trace_generator.socket, "socket", MagicMock())
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.iter_content.return_value = [b"new release"]
    response.headers = {}
    request = MagicMock(return_value=response)
    monkeypatch.setattr(trace_generator.requests, "get", request)
    if status == 304:
        with pytest.raises(TracerDownloadError, match="304"):
            trace_generator.ensure_code_tracer_installed()
        assert outdated_cache.read_bytes() == b"old release"
    else:
        trace_generator.ensure_code_tracer_installed()
        assert outdated_cache.read_bytes() == b"new release"
    assert "If-Modified-Since" not in request.call_args.kwargs["headers"]


def test_packaged_pin_takes_precedence_over_neighboring_project(tmp_path, monkeypatch):
    package = tmp_path / "cs1302_code_visualizer"
    package.mkdir()
    config = '[tool.cs1302-code-visualizer]\ntracer-url="{url}"\ntracer-sha256="{sha}"\n'
    (package / "pyproject.toml").write_text(config.format(url="packaged", sha="expected"))
    (tmp_path / "pyproject.toml").write_text(config.format(url="unrelated", sha="wrong"))
    monkeypatch.setattr(trace_generator, "PACKAGE_DIR", package)
    assert trace_generator.read_tracer_url_and_sum_from_toml() == ("packaged", "expected")


def test_bad_download_preserves_previous_release(outdated_cache, monkeypatch):
    monkeypatch.setattr(trace_generator.socket, "socket", MagicMock())
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = [b"corrupted release"]
    monkeypatch.setattr(trace_generator.requests, "get", MagicMock(return_value=response))
    with pytest.raises(TracerDownloadError, match="SHA256"):
        trace_generator.ensure_code_tracer_installed()
    assert outdated_cache.read_bytes() == b"old release"
    assert not list(outdated_cache.parent.glob("*.tmp.*"))


@pytest.fixture(scope="module")
def java_home():
    trace_generator.ensure_code_tracer_installed()
    return trace_generator.ensure_jdk_installed()


LOOP_SOURCE = """public class Driver {
    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            System.out.println(i);
        }
    }
}
"""


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
@pytest.mark.parametrize("unlimited", [False, True])
def test_explicit_budget_failure_preserves_diagnostics(java_home, trace_format, unlimited):
    args = [f"--format={trace_format}", "--max-snapshots=1"]
    if unlimited:
        args.append("--unlimited")
    with pytest.raises(CodeVisTraceGeneratorError) as raised:
        trace_generator.generate_trace(
            java_home, LOOP_SOURCE, all_breakpoints=True, extra_tracer_args=args
        )
    error = raised.value
    assert error.exit_status == 3
    assert error.stdout == ""
    assert "snapshot_limit" in error.stderr
    assert error.source_code == LOOP_SOURCE
    assert all(arg in error.cli_args for arg in args)
    assert any("snapshot_limit" in note for note in error.__notes__)


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
def test_unlimited_matches_successful_default_trace(java_home, trace_format):
    args = [f"--format={trace_format}"]
    default = json.loads(
        trace_generator.generate_trace(
            java_home, LOOP_SOURCE, all_breakpoints=True, extra_tracer_args=args
        )
    )
    unlimited = json.loads(
        trace_generator.generate_trace(
            java_home, LOOP_SOURCE, all_breakpoints=True, extra_tracer_args=[*args, "--unlimited"]
        )
    )
    key = "steps" if trace_format == "modern" else "trace"
    # Object IDs belong to separate JVMs; compare observable execution instead.
    signature = lambda trace: [(s["line"], s["stdout"]) for s in trace[key]]
    assert signature(default) == signature(unlimited)
    assert default[key][-1]["stdout"] == "0\n1\n2\n"


def test_process_timeout_is_distinct_from_tracer_budget(java_home, monkeypatch):
    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 1
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(trace_generator.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        trace_generator.generate_trace(java_home, LOOP_SOURCE, timeout_secs=1)
    assert raised.value.timeout == 1


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
@pytest.mark.parametrize("reader", ["scanner", "buffered", "io"])
def test_logical_unicode_input_consumption(java_home, trace_format, reader):
    if reader == "io":
        release = (java_home / "release").read_text()
        major = re.search(r'JAVA_VERSION="(\d+)', release)
        assert major is not None
        if int(major[1]) < 25:
            pytest.skip("java.lang.IO.readln requires JDK 25")
        setup = ""
        first_read = 'java.lang.IO.readln("prompt: ")'
        second_read = "java.lang.IO.readln()"
    elif reader == "buffered":
        setup = "var input = new java.io.BufferedReader(new java.io.InputStreamReader(System.in));"
        first_read = second_read = "input.readLine()"
    else:
        setup = "var input = new java.util.Scanner(System.in);"
        first_read = second_read = "input.nextLine()"
    source = f"""public class Driver {{
    public static void main(String[] args) throws Exception {{
        {setup}
        String first = {first_read};
        String second = {second_read};
        String unrelated = new java.util.Scanner("other").nextLine();
        System.out.println(first + second + unrelated);
    }}
}}
"""
    supplied = "é😀\nrest\nuntouched\n"
    trace = json.loads(
        trace_generator.generate_trace(
            java_home,
            source,
            stdin=supplied,
            all_breakpoints=True,
            extra_tracer_args=[f"--format={trace_format}"],
        )
    )
    steps = trace["steps" if trace_format == "modern" else "trace"]
    by_line = {step["line"]: step for step in steps}
    assert trace["stdin"] == supplied
    assert by_line[4]["stdinOffset"] == 0
    assert by_line[5]["stdinConsumed"] == "é😀\n"
    assert by_line[5]["stdinOffset"] == 4  # UTF-16, including the surrogate pair.
    assert by_line[6]["stdinConsumed"] == "é😀\nrest\n"
    assert by_line[6]["stdinOffset"] == 9
    assert by_line[7]["stdinOffset"] == 9  # Unrelated readers must not consume stdin.
