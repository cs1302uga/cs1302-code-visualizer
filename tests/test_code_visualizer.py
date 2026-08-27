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


def test_generate_image_modern_format(java_home):
    trace_raw = generate_trace(
        java_home,
        SAMPLE_JAVA,
        breakpoints={-1},
        extra_tracer_args=["--format=modern"],
    )
    img_bytes = generate_image(trace_raw)
    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 0
    assert img_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_code_visualizer_json_pre(java_home):
    import base64
    from cs1302_code_visualizer.browser_driver import get_webdriver, this_files_dir

    trace_raw = generate_trace(
        java_home,
        SAMPLE_JAVA,
        breakpoints={-1},
        extra_tracer_args=["--format=modern"],
    )
    b64_trace = "data:application/json;base64," + base64.b64encode(
        trace_raw.encode("utf-8")
    ).decode("utf-8")

    driver = get_webdriver(dpi=1)
    try:
        html_uri = (this_files_dir / "frontend" / "codevis.html").as_uri()
        driver.get(html_uri)
        driver.execute_script(
            """
            const container = document.createElement("div");
            container.id = "test-pre-container";
            document.body.appendChild(container);
            window.testViz = CodeVisualizer.create({
                lang: "java",
                trace: arguments[0],
                element: container,
                options: { visualizer: "json-pre" }
            });
            """,
            b64_trace,
        )
        pre_code = driver.find_element(
            "css selector", "#test-pre-container pre code.language-json"
        )
        assert pre_code is not None
        assert "modern" in pre_code.text
    finally:
        driver.quit()

