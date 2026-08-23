import io
import sys
import importlib
import pytest

SAMPLE_JAVA = """
public class Driver {
    public static void main(String[] args) {
        int x = 42;
    }
}
"""


class MockStdout:
    def __init__(self, buffer):
        self.buffer = buffer


def test_main_module_execution(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_JAVA))
    monkeypatch.setattr("sys.argv", ["__main__"])
    output_buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", MockStdout(output_buffer))

    # Reload or import __main__ module to execute lines 1-3
    if "cs1302_code_visualizer.__main__" in sys.modules:
        del sys.modules["cs1302_code_visualizer.__main__"]

    importlib.import_module("cs1302_code_visualizer.__main__")

    val = output_buffer.getvalue()
    assert len(val) > 0
    assert val[:8] == b"\x89PNG\r\n\x1a\n"
