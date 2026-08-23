import json
import pytest
from pathlib import Path
from cs1302_code_visualizer.trace_generator import generate_trace, ensure_jdk_installed
from cs1302_code_visualizer.breakpoint_lister import list_breakpoints_json
from cs1302_code_visualizer.browser_driver import generate_image

SAMPLE_JAVA = """
public class Driver {
    public static void main(String[] args) {
        Person alice = new Person("Alice", 30);
    }
}
record Person(String name, int age) {}
"""


@pytest.fixture(scope="module")
def java_home():
    return ensure_jdk_installed()


def test_jdk_installation(java_home):
    assert java_home.exists()
    assert (java_home / "bin" / "java").is_file()


def test_list_breakpoints(java_home):
    breakpoints = list_breakpoints_json(SAMPLE_JAVA, java_home)
    assert isinstance(breakpoints, list)
    assert len(breakpoints) > 0
    assert any(b.get("validBreakpoint") for b in breakpoints)


def test_generate_trace(java_home):
    trace_raw = generate_trace(java_home, SAMPLE_JAVA, breakpoints={-1})
    assert isinstance(trace_raw, str)
    trace_json = json.loads(trace_raw)
    assert "-1" in trace_json or len(trace_json) > 0


def test_generate_image(java_home):
    trace_raw = generate_trace(java_home, SAMPLE_JAVA, breakpoints={-1})
    trace_json = json.loads(trace_raw)
    inner_trace = trace_json.get("-1", list(trace_json.values())[0])
    img_bytes = generate_image(json.dumps(inner_trace))
    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 0
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic header
