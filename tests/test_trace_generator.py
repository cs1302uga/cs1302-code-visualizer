import io
import sys
import json
import runpy
import pytest
import importlib
import zipfile
import tarfile
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import patch, MagicMock

import cs1302_code_visualizer.trace_generator as trace_generator
from cs1302_code_visualizer.trace_generator import (
    generate_trace,
    ensure_jdk_installed,
    ensure_code_tracer_installed,
    download_jdk,
    jdk_exists,
    read_tracer_url_and_sum_from_toml,
    get_enum_types,
    get_enum_globals,
    delete_globals,
    main as generator_main,
)
from cs1302_code_visualizer.errors import CodeVisTraceGeneratorError

SAMPLE_ENUM_JAVA = """
public class Driver {
    public static void main(String[] args) {
        Meal meal = Meal.LUNCH;
    }
}
enum Meal { BREAKFAST, LUNCH, DINNER; }
"""


@pytest.fixture(scope="module")
def java_home():
    return ensure_jdk_installed()


def test_trace_generator_debug_env(monkeypatch):
    monkeypatch.setenv("CS1302_DEBUG", "1")
    importlib.reload(trace_generator)
    assert trace_generator.DEBUG_MODE is True


def test_tracer_url_and_sum_from_toml():
    res = read_tracer_url_and_sum_from_toml()
    assert res is not None
    assert isinstance(res, tuple)
    assert len(res) == 2


def test_tracer_url_from_toml_failure(monkeypatch):
    monkeypatch.setattr("tomllib.load", lambda f: {})
    assert read_tracer_url_and_sum_from_toml() is None


def test_tracer_url_from_toml_none_url(monkeypatch):
    monkeypatch.setattr(
        "tomllib.load", lambda f: {"tool": {"cs1302-code-visualizer": {"tracer-url": None}}}
    )
    assert read_tracer_url_and_sum_from_toml() is None


def test_tracer_url_from_toml_none_sha(monkeypatch):
    monkeypatch.setattr(
        "tomllib.load",
        lambda f: {
            "tool": {
                "cs1302-code-visualizer": {
                    "tracer-url": "http://example.com",
                    "tracer-sha256": None,
                }
            }
        },
    )
    assert read_tracer_url_and_sum_from_toml() is None


def test_tracer_url_from_toml_exception(monkeypatch):
    with patch("builtins.open", side_effect=Exception("Read error")):
        assert read_tracer_url_and_sum_from_toml() is None


def test_jdk_exists(java_home):
    assert jdk_exists(java_home)
    assert not jdk_exists("/invalid/nonexistent/path")


def test_download_jdk_already_exists(tmp_path, monkeypatch):
    jdk_cache = tmp_path / "jdk"
    jdk_cache.mkdir()
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.JDK_CACHE_DIR", jdk_cache)
    download_jdk()  # returns immediately


def test_download_jdk_unsupported_platform(tmp_path, monkeypatch):
    fake_cache = tmp_path / "nonexistent"
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.JDK_CACHE_DIR", fake_cache)
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    with pytest.raises(
        Exception, match="Cannot automatically download a JDK for your computer's platform"
    ):
        download_jdk()


def test_download_jdk_unsupported_arch(tmp_path, monkeypatch):
    fake_cache = tmp_path / "nonexistent"
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.JDK_CACHE_DIR", fake_cache)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "mips64")
    with pytest.raises(
        Exception, match="Cannot automatically download a JDK for your computer's architecture"
    ):
        download_jdk()


def test_download_jdk_linux_x64(tmp_path, monkeypatch):
    fake_cache = tmp_path / "cache_linux"
    fake_cache.mkdir()
    fake_jdk = fake_cache / "jdk_test"
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.JDK_CACHE_DIR", fake_jdk)
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.CACHE_DIR", fake_cache)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")

    resp1 = MagicMock()
    resp1.raise_for_status = MagicMock()
    resp1.json.return_value = {"most_recent_lts": 21}

    resp2 = MagicMock()
    resp2.raise_for_status = MagicMock()
    resp2.status_code = 404  # triggers 404 fallback path

    resp3 = MagicMock()
    resp3.raise_for_status = MagicMock()
    resp3.status_code = 200
    resp3.iter_content.return_value = [b"mock_data"]

    call_count = 0

    def mock_get(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if "available_releases" in url:
            return resp1
        if call_count == 2:
            return resp2
        return resp3

    mock_tar = MagicMock()
    mock_tar.getnames.return_value = ["jdk-21-linux"]
    mock_tar_ctx = MagicMock()
    mock_tar_ctx.__enter__.return_value = mock_tar

    def mock_move(src, dst):
        jdk_dir = Path(dst)
        (jdk_dir / "bin").mkdir(parents=True, exist_ok=True)
        (jdk_dir / "bin" / "java").touch()
        (jdk_dir / "bin" / "javac").touch()

    with patch("requests.get", side_effect=mock_get):
        with patch("tarfile.open", return_value=mock_tar_ctx):
            with patch("shutil.move", side_effect=mock_move):
                download_jdk()


def test_download_jdk_windows_amd64(tmp_path, monkeypatch):
    fake_cache = tmp_path / "cache_win"
    fake_cache.mkdir()
    fake_jdk = fake_cache / "jdk_win"
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.JDK_CACHE_DIR", fake_jdk)
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.CACHE_DIR", fake_cache)
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("platform.machine", lambda: "amd64")

    resp1 = MagicMock()
    resp1.raise_for_status = MagicMock()
    resp1.json.return_value = {"most_recent_lts": 21}

    resp2 = MagicMock()
    resp2.raise_for_status = MagicMock()
    resp2.status_code = 200
    resp2.iter_content.return_value = [b"mock_zip_data"]

    def mock_get(url, *args, **kwargs):
        if "available_releases" in url:
            return resp1
        return resp2

    mock_zip = MagicMock()
    mock_zip.namelist.return_value = ["jdk-21-windows/"]
    mock_zip_ctx = MagicMock()
    mock_zip_ctx.__enter__.return_value = mock_zip

    def mock_move(src, dst):
        jdk_dir = Path(dst)
        (jdk_dir / "bin").mkdir(parents=True, exist_ok=True)
        (jdk_dir / "bin" / "java").touch()
        (jdk_dir / "bin" / "javac").touch()

    with patch("requests.get", side_effect=mock_get):
        with patch("zipfile.ZipFile", return_value=mock_zip_ctx):
            with patch("shutil.move", side_effect=mock_move):
                download_jdk()


def test_download_jdk_extraction_failed(tmp_path, monkeypatch):
    fake_cache = tmp_path / "cache_fail"
    fake_cache.mkdir()
    fake_jdk = fake_cache / "jdk_fail"
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.JDK_CACHE_DIR", fake_jdk)
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.CACHE_DIR", fake_cache)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")

    resp1 = MagicMock()
    resp1.raise_for_status = MagicMock()
    resp1.json.return_value = {"most_recent_lts": 21}
    resp2 = MagicMock()
    resp2.raise_for_status = MagicMock()
    resp2.status_code = 200
    resp2.iter_content.return_value = [b"data"]

    def mock_get(url, *args, **kwargs):
        if "available_releases" in url:
            return resp1
        return resp2

    mock_tar = MagicMock()
    mock_tar.getnames.return_value = ["jdk-21/Contents/Home"]
    mock_tar_ctx = MagicMock()
    mock_tar_ctx.__enter__.return_value = mock_tar

    with patch("requests.get", side_effect=mock_get):
        with patch("tarfile.open", return_value=mock_tar_ctx):
            with patch(
                "shutil.move", side_effect=lambda src, dst: None
            ):  # don't create java binary
                with pytest.raises(Exception, match="Could not extract the JDK"):
                    download_jdk()


def test_ensure_jdk_installed_success_download(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda exe: None)
    fake_jdk = tmp_path / "jdk"
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.CACHE_DIR", tmp_path)
    res = ensure_jdk_installed(install_dir=tmp_path / "nonexistent")
    assert res == fake_jdk


def test_ensure_jdk_installed_download_error(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda exe: None)
    with patch(
        "cs1302_code_visualizer.trace_generator.download_jdk",
        side_effect=Exception("Download failed"),
    ):
        with pytest.raises(Exception, match="Failed to download JDK"):
            ensure_jdk_installed(install_dir=tmp_path / "nonexistent")


def test_ensure_code_tracer_installed():
    ensure_code_tracer_installed(update_existing=False)


def test_ensure_code_tracer_installed_304(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.status_code = 304
    with patch("requests.get", return_value=mock_resp):
        with patch("pathlib.Path.is_file", return_value=True):
            ensure_code_tracer_installed(update_existing=True)


def test_ensure_code_tracer_download_full(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.CACHE_DIR", tmp_path)
    url_sum = read_tracer_url_and_sum_from_toml()
    url = url_sum[0] if url_sum else "http://example.com/code-tracer.jar"

    content = b"DUMMY_JAR_DATA_CONTENT"
    mock_hash = hashlib.sha256(content).hexdigest()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_content.return_value = [content]
    mock_resp.headers = {"Last-Modified": "Fri, 14 Aug 2026 00:00:00 GMT"}

    with patch(
        "cs1302_code_visualizer.trace_generator.read_tracer_url_and_sum_from_toml",
        return_value=(url, mock_hash),
    ):
        with patch("requests.get", return_value=mock_resp):
            ensure_code_tracer_installed(update_existing=True)
            assert (tmp_path / "code-tracer.jar").exists()


def test_ensure_code_tracer_download_sha_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr("cs1302_code_visualizer.trace_generator.CACHE_DIR", tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_content.return_value = [b"BAD_CONTENT"]
    mock_resp.headers = {}

    with patch(
        "cs1302_code_visualizer.trace_generator.read_tracer_url_and_sum_from_toml",
        return_value=("http://example.com", "wrong_hash"),
    ):
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(
                Exception, match="Downloaded tracer JAR doesn't have the correct SHA256 sum"
            ):
                ensure_code_tracer_installed(update_existing=True)


def test_ensure_code_tracer_update_offline(monkeypatch):
    import socket

    with patch("socket.socket") as mock_sock_class:
        mock_sock_inst = MagicMock()
        mock_sock_inst.connect.side_effect = socket.error("Offline")
        mock_sock_class.return_value = mock_sock_inst
        ensure_code_tracer_installed(update_existing=True)


def test_generate_trace_error_handling(java_home):
    with pytest.raises(CodeVisTraceGeneratorError) as exc_info:
        generate_trace(java_home, "invalid java code {{{")
    err = exc_info.value
    assert err.exit_status != 0
    assert err.source_code == "invalid java code {{{"


def test_generate_trace_multiple_breakpoints_cli(java_home):
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.stdout = '{"9": {}, "11": {}}'
        mock_run.return_value = mock_proc
        _ = generate_trace(
            java_home=java_home,
            java_program=SAMPLE_ENUM_JAVA,
            breakpoints={9, 11},
        )
        cmd = mock_run.call_args[0][0]
        assert "--enable-native-access=ALL-UNNAMED" in cmd
        assert cmd.count("-b") == 2
        b_idx_9 = cmd.index("9")
        b_idx_11 = cmd.index("11")
        assert cmd[b_idx_9 - 1] == "-b"
        assert cmd[b_idx_11 - 1] == "-b"


def test_generate_trace_flags(java_home):
    trace_raw = generate_trace(
        java_home=java_home,
        java_program=SAMPLE_ENUM_JAVA,
        inline_strings=True,
        remove_main_args_parameter=False,
        accumulate_breakpoints=True,
        include_enum_static_fields=True,
    )
    assert isinstance(trace_raw, str)
    data = json.loads(trace_raw)
    assert len(data) > 0


def test_enum_helpers():
    sample_trace = {
        "trace": [
            {
                "globals": {
                    "Meal.$VALUES": ["REF", 1],
                    "Meal.LUNCH": ["REF", 2],
                    "OtherVar": 10,
                },
                "globals_attrs": {
                    "Meal.$VALUES": {},
                    "Meal.LUNCH": {},
                    "OtherVar": {},
                },
                "ordered_globals": ["Meal.$VALUES", "Meal.LUNCH", "OtherVar"],
            }
        ]
    }
    types = get_enum_types(sample_trace)
    assert "Meal" in types
    enum_globals = get_enum_globals(sample_trace, types)
    assert "Meal.LUNCH" in enum_globals
    delete_globals(sample_trace, enum_globals)
    assert "Meal.LUNCH" not in sample_trace["trace"][0]["globals"]


def test_trace_generator_main(tmp_path, monkeypatch):
    out_file = tmp_path / "trace.json"
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_ENUM_JAVA))
    monkeypatch.setattr(
        "sys.argv", ["generate_trace", "-o", str(out_file), "-v", "--include-enum-static-fields"]
    )
    generator_main()
    assert out_file.exists()
    content = out_file.read_text()
    assert len(content) > 0
    data = json.loads(content)
    assert len(data) > 0


def test_trace_generator_main_stdout(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_ENUM_JAVA))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    monkeypatch.setattr("sys.argv", ["generate_trace"])
    generator_main()
    out = captured.getvalue()
    assert len(out) > 0


def test_trace_generator_main_with_valid_jdk_arg(java_home, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_ENUM_JAVA))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    monkeypatch.setattr("sys.argv", ["generate_trace", "--jdk", str(java_home)])
    generator_main()
    assert len(captured.getvalue()) > 0


def test_trace_generator_main_invalid_jdk_path(java_home, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_ENUM_JAVA))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    monkeypatch.setattr("sys.argv", ["generate_trace", "--jdk", "/invalid/nonexistent/path"])
    with patch(
        "cs1302_code_visualizer.trace_generator.ensure_jdk_installed", return_value=java_home
    ):
        generator_main()
    assert len(captured.getvalue()) > 0


def test_trace_generator_runpy_main(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_ENUM_JAVA))
    captured = io.StringIO()
    monkeypatch.setattr(sys, "stdout", captured)
    monkeypatch.setattr("sys.argv", ["generate_trace"])
    runpy.run_module("cs1302_code_visualizer.trace_generator", run_name="__main__")
    out = captured.getvalue()
    assert len(out) > 0
