"""Regression tests for sequential benchmark comparisons."""

import json
import runpy
import threading
from unittest.mock import MagicMock

import pytest

from scripts import benchmark_cli_batch


@pytest.mark.parametrize("skip", [False, True])
@pytest.mark.parametrize("duration", [0.0, 2.0])
def test_benchmark_speedup_requires_sequential_baseline(
    tmp_path, monkeypatch, capsys, skip, duration
):
    source = tmp_path / "examples" / "example0" / "Driver.java"
    source.parent.mkdir(parents=True)
    source.write_text("class Driver {}")
    monkeypatch.setattr(benchmark_cli_batch, "__file__", str(tmp_path / "scripts" / "benchmark.py"))
    monkeypatch.setattr(
        "sys.argv", ["benchmark", "--num-examples", "1"] + (["--skip-sequential"] if skip else [])
    )
    monkeypatch.setattr(benchmark_cli_batch.threading, "Thread", MagicMock())
    monkeypatch.setattr(
        benchmark_cli_batch.subprocess, "run", MagicMock(return_value=MagicMock(returncode=0))
    )
    monkeypatch.setattr(benchmark_cli_batch.time, "perf_counter", MagicMock(side_effect=[0.0, 4.0]))
    monkeypatch.setattr(
        benchmark_cli_batch,
        "run_benchmark_run",
        lambda name, cmd, out: {
            "name": name,
            "total_seconds": duration,
            "ttfi_seconds": duration,
            "images_emitted": 1,
            "throughput_img_per_sec": 1,
        },
    )
    benchmark_cli_batch.main()
    results = json.loads((tmp_path / "benchmark_cli_batch_results.json").read_text())
    expected = "2.00x" if not skip and duration else "N/A"
    assert all(result["speedup"] == expected for result in results[0 if skip else 1 :])
    assert expected in capsys.readouterr().out
    if not skip:
        assert results[0]["speedup"] == "1.00x"


def test_monitor_first_image_ignores_temporary_files(tmp_path, monkeypatch):
    (tmp_path / ".temporary.png").touch()
    (tmp_path / "result.png").touch()
    monkeypatch.setattr(benchmark_cli_batch.time, "perf_counter", lambda: 5.0)
    result = []
    benchmark_cli_batch.monitor_first_image(tmp_path, threading.Event(), result, 2.0)
    assert result == [3.0]


@pytest.mark.parametrize("exists", [False, True])
def test_monitor_first_image_stops_without_images(tmp_path, monkeypatch, exists):
    stop = threading.Event()
    monkeypatch.setattr(benchmark_cli_batch.time, "sleep", lambda _: stop.set())
    result = []
    benchmark_cli_batch.monitor_first_image(
        tmp_path if exists else tmp_path / "missing", stop, result, 0.0
    )
    assert result == []


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("duration", [0.0, 2.0])
def test_run_benchmark_run(tmp_path, monkeypatch, failed, duration):
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    (out_dir / "old.png").touch()
    monkeypatch.setattr(benchmark_cli_batch.threading, "Thread", MagicMock())
    monkeypatch.setattr(
        benchmark_cli_batch.time, "perf_counter", MagicMock(side_effect=[0.0, duration])
    )

    def run(*args, **kwargs):
        assert not (out_dir / "old.png").exists()
        (out_dir / "new.png").touch()
        return MagicMock(returncode=int(failed), stderr="command failed")

    monkeypatch.setattr(benchmark_cli_batch.subprocess, "run", run)
    if failed:
        with pytest.raises(RuntimeError, match="failed with exit code"):
            benchmark_cli_batch.run_benchmark_run("test", [], out_dir)
    else:
        result = benchmark_cli_batch.run_benchmark_run("test", [], out_dir)
        assert result["images_emitted"] == 1
        assert result["total_seconds"] == duration


def test_benchmark_no_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_cli_batch, "__file__", str(tmp_path / "scripts" / "benchmark.py"))
    monkeypatch.setattr("sys.argv", ["benchmark"])
    with pytest.raises(SystemExit, match="1"):
        benchmark_cli_batch.main()


def test_benchmark_existing_scratch_and_failed_sequential(tmp_path, monkeypatch, capsys):
    source = tmp_path / "examples" / "example0" / "Driver.java"
    source.parent.mkdir(parents=True)
    source.touch()
    (tmp_path / ".benchmark_scratch").mkdir()
    monkeypatch.setattr(benchmark_cli_batch, "__file__", str(tmp_path / "scripts" / "benchmark.py"))
    monkeypatch.setattr("sys.argv", ["benchmark", "--num-examples", "1"])
    monkeypatch.setattr(benchmark_cli_batch.threading, "Thread", MagicMock())
    monkeypatch.setattr(
        benchmark_cli_batch.subprocess,
        "run",
        MagicMock(return_value=MagicMock(returncode=1, stderr="failed")),
    )
    monkeypatch.setattr(benchmark_cli_batch.time, "perf_counter", MagicMock(side_effect=[0.0, 4.0]))
    monkeypatch.setattr(
        benchmark_cli_batch,
        "run_benchmark_run",
        lambda name, cmd, out: {
            "name": name,
            "total_seconds": 2.0,
            "ttfi_seconds": 1.0,
            "images_emitted": 1,
            "throughput_img_per_sec": 0.5,
        },
    )
    benchmark_cli_batch.main()
    assert "Error on sequential" in capsys.readouterr().err


def test_benchmark_main_entry(monkeypatch):
    monkeypatch.setattr("sys.argv", ["benchmark", "--help"])
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("scripts.benchmark_cli_batch", run_name="__main__")
