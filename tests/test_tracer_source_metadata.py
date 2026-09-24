"""Real-JAR compatibility checks for tracer source metadata introduced in 3.1.1."""

import json

import pytest

from cs1302_code_visualizer.batch_tracer import BatchTraceJob, BatchTracerClient
from cs1302_code_visualizer.trace_generator import (
    ensure_code_tracer_installed,
    ensure_jdk_installed,
    generate_trace,
)

MAIN = """package demo;
public class Main {
    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            System.out.println(Helper.twice(i));
        }
    }
}
"""
HELPER = """package demo;
class Helper {
    static int twice(int value) {
        return value * 2;
    }
}
"""
SOURCE = f"// --- demo/Main.java ---\n{MAIN}// --- demo/Helper.java ---\n{HELPER}"


@pytest.fixture(scope="module")
def java_home():
    ensure_code_tracer_installed()
    return ensure_jdk_installed()


def assert_metadata(trace):
    assert trace["code"] == SOURCE
    assert trace["entryFile"] == "demo/Main.java"
    assert trace["sources"] == {"demo/Main.java": MAIN, "demo/Helper.java": HELPER}
    return trace


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
@pytest.mark.parametrize("mode", ["all", "selected", "accumulated"])
def test_single_trace_preserves_source_metadata(java_home, trace_format, mode):
    result = json.loads(
        generate_trace(
            java_home,
            SOURCE,
            all_breakpoints=mode == "all",
            breakpoints={-1} if mode == "all" else {5},
            accumulate_breakpoints=mode == "accumulated",
            extra_tracer_args=[f"--format={trace_format}"],
        )
    )
    if trace_format == "pytutor" and mode != "all":
        snapshots = result["5"] if mode == "accumulated" else [result["5"]]
        assert len(snapshots) == (3 if mode == "accumulated" else 1)
        for snapshot in snapshots:
            assert_metadata(snapshot)
    else:
        assert_metadata(result)
    if mode == "all":
        steps = result["trace"] if trace_format == "pytutor" else result["steps"]
        assert {step["file"] for step in steps} == {"demo/Main.java", "demo/Helper.java"}


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
def test_batch_worker_reuse_preserves_source_metadata(java_home, trace_format):
    with BatchTracerClient(java_home=java_home, workers=1) as client:
        for _ in range(2):
            result = client.submit(BatchTraceJob(source=SOURCE, format=trace_format)).result(
                timeout=60
            )
            assert_metadata(result)
