import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from cs1302_code_visualizer import RenderingSession, trace_generator


@pytest.fixture
def tracing(monkeypatch):
    generate = Mock(return_value=json.dumps({"-1": {"trace": []}}))
    monkeypatch.setattr(trace_generator, "generate_trace", generate)
    monkeypatch.setattr(trace_generator, "ensure_code_tracer_installed", Mock())
    monkeypatch.setattr(trace_generator, "read_tracer_url_and_sum_from_toml", lambda: ("url", "version-a"))
    return generate


def test_persistent_traces_invalidate_and_recover(tmp_path, tracing, monkeypatch):
    with RenderingSession(cache_dir=tmp_path) as session:
        original = session.generate_trace(Path("/jdk"), "source", breakpoints={1, 2})
        assert original == session.generate_trace(Path("/jdk"), "source", breakpoints={2, 1})
    assert tracing.call_count == 1
    with RenderingSession(cache_dir=tmp_path) as session:
        assert original == session.generate_trace(Path("/jdk"), "source", breakpoints={1, 2})
        session.generate_trace(Path("/jdk"), "changed", breakpoints={1, 2})
        session.generate_trace(Path("/jdk"), "source", breakpoints={1, 3})
        session.generate_trace(Path("/jdk"), "source", breakpoints={1, 2}, inline_strings=True)
    assert tracing.call_count == 4
    for path in tmp_path.glob("*.json"):
        path.write_text("broken")
    with RenderingSession(cache_dir=tmp_path) as session:
        session.generate_trace(Path("/jdk"), "source", breakpoints={1, 2})
    assert tracing.call_count == 5
    monkeypatch.setattr(trace_generator, "read_tracer_url_and_sum_from_toml", lambda: ("url", "version-b"))
    with RenderingSession(cache_dir=tmp_path) as session:
        session.generate_trace(Path("/jdk"), "source", breakpoints={1, 2})
    assert tracing.call_count == 6


def test_trace_requests_share_inflight_work(tmp_path, tracing):
    tracing.side_effect = lambda *args, **kwargs: (time.sleep(.03) or '{"-1": {"trace": []}}')
    with RenderingSession(cache_dir=tmp_path) as session, ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: session.generate_trace(Path("/jdk"), "source"), range(4)))
    assert len(set(results)) == 1
    assert tracing.call_count == 1


def test_browser_reuse_dpi_eviction_and_failures():
    drivers = []
    def factory(**kwargs):
        driver = Mock()
        drivers.append(driver)
        return driver
    with RenderingSession(max_browsers=2) as session:
        for dpi in (1, 2, 1):
            with session.browser(dpi, factory):
                pass
        assert len(drivers) == 2
        with pytest.raises(RuntimeError), session.browser(1, factory):
            raise RuntimeError("failed frame")
        assert drivers[0].quit.call_count == 1
        with session.browser(1, factory):
            pass
        assert len(drivers) == 3
        with session.browser(3, factory):
            pass
        assert len(drivers) == 4
    assert all(driver.quit.call_count == 1 for driver in drivers)
    session.close()
    assert all(driver.quit.call_count == 1 for driver in drivers)
    with pytest.raises(RuntimeError, match="closed"), session.browser(1, factory):
        pass


def test_browser_limit_is_global_across_dpi():
    lock = threading.Lock()
    alive = peak = 0
    def factory(**kwargs):
        nonlocal alive, peak
        with lock:
            alive += 1
            peak = max(peak, alive)
        def quit():
            nonlocal alive
            with lock:
                alive -= 1
        return Mock(quit=quit)
    with RenderingSession(max_browsers=2) as session, ThreadPoolExecutor(max_workers=6) as workers:
        def render(dpi):
            with session.browser(dpi, factory):
                time.sleep(.01)
        list(workers.map(render, [1, 2, 3, 1, 2, 3] * 3))
    assert peak == 2
    assert alive == 0


def test_failed_browser_start_releases_capacity():
    with RenderingSession(max_browsers=1) as session:
        with pytest.raises(OSError), session.browser(1, Mock(side_effect=OSError("startup"))):
            pass
        with session.browser(1, Mock(return_value=Mock())):
            pass


def test_closed_session_invalid_limits_and_trace_shapes(tracing):
    with pytest.raises(ValueError):
        RenderingSession(max_browsers=0)
    session = RenderingSession()
    session.close()
    with pytest.raises(RuntimeError, match="closed"):
        session.generate_trace(Path("/jdk"), "source")
    tracing.return_value = "[]"
    with RenderingSession() as session, pytest.raises(TypeError):
        session.generate_trace(Path("/jdk"), "source")
    with RenderingSession() as session, session.browser(
        1, Mock(return_value=Mock(quit=Mock(side_effect=OSError("gone"))))
    ):
        pass


def test_reused_browser_matches_legacy_pixels_and_clears_state(tmp_path):
    from io import BytesIO

    from PIL import Image

    from cs1302_code_visualizer import browser_driver
    code = """public class Main {
 public static void main(String[] args) {
  int[] xs = {1, 2, 3};
  xs[0] = 7;
  System.out.println(xs[0]);
 }
}"""
    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()
    traces = json.loads(trace_generator.generate_trace(java_home, code, breakpoints={3, 4, 5}))
    with RenderingSession(max_browsers=2, cache_dir=tmp_path) as session:
        for dpi, arrows in [(1, False), (2, True), (1, False)]:
            for frame in traces.values():
                options = {"dpi": dpi, "text_memory_labels": arrows, "include_types": True}
                expected = browser_driver.generate_image(json.dumps(frame), **options)
                actual = browser_driver.generate_image(json.dumps(frame), session=session, **options)
                a = Image.open(BytesIO(actual)).convert("RGBA")
                b = Image.open(BytesIO(expected)).convert("RGBA")
                assert a.size == b.size
                assert a.tobytes() == b.tobytes()


def test_prune_trace_cache_uses_last_access_and_honors_dry_run(tmp_path, monkeypatch):
    import os

    from cs1302_code_visualizer.session import prune_trace_cache
    old = tmp_path / "old.json"
    fresh = tmp_path / "fresh.json"
    old.write_text("{}")
    fresh.write_text("{}")
    os.utime(old, (1, 1))
    assert prune_trace_cache(tmp_path, dry_run=True) == (1, 2)
    assert old.exists()
    assert prune_trace_cache(tmp_path) == (1, 2)
    assert not old.exists() and fresh.exists()
    with pytest.raises(ValueError):
        prune_trace_cache(tmp_path, max_age_days=-1)
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == fresh:
            raise FileNotFoundError()
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "stat", stat)
    assert prune_trace_cache(tmp_path) == (0, 0)


def test_large_diagram_matches_legacy_pixels():
    from io import BytesIO

    from PIL import Image

    from cs1302_code_visualizer import browser_driver

    code = """public class Main {
 public static void main(String[] args) {
  int[][] rows = new int[35][4];
  System.out.println(rows.length);
 }
}"""
    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()
    traces = json.loads(trace_generator.generate_trace(java_home, code, breakpoints={4}))
    frame = json.dumps(traces["4"])
    expected = browser_driver.generate_image(frame)
    with RenderingSession() as session:
        actual = browser_driver.generate_image(frame, session=session)
    a = Image.open(BytesIO(actual)).convert("RGBA")
    b = Image.open(BytesIO(expected)).convert("RGBA")
    assert a.height > 1080
    assert a.size == b.size
    assert a.tobytes() == b.tobytes()


def test_close_during_active_request_discards_browser_and_wakes_waiter():
    driver = Mock()
    session = RenderingSession(max_browsers=1)
    with ThreadPoolExecutor(max_workers=1) as workers, session.browser(1, Mock(return_value=driver)):
        waiting = threading.Event()
        def waiting_request():
            waiting.set()
            with session.browser(1, Mock()):
                pytest.fail("closed session lent a browser")
        future = workers.submit(waiting_request)
        assert waiting.wait(2)
        session.close()
        with pytest.raises(RuntimeError, match="closed"):
            future.result(timeout=2)
        driver.quit.assert_not_called()
    driver.quit.assert_called_once()


@pytest.mark.parametrize("option,value", [
    ("timeout_secs", 2), ("remove_main_args_parameter", False),
    ("accumulate_breakpoints", True), ("include_enum_static_fields", True),
    ("auto_detect", True), ("type_style", "fqn"),
    ("stdin", "hello"), ("stdin_file", "input.txt"),
    ("extra_tracer_args", ["--debug"]),
])
def test_trace_execution_options_invalidate(tmp_path, tracing, option, value):
    with RenderingSession(cache_dir=tmp_path) as session:
        session.generate_trace(Path("/jdk"), "source")
        session.generate_trace(Path("/jdk"), "source", **{option: value})
    assert tracing.call_count == 2


def test_trace_stdin_file_content_change_invalidates(tmp_path, tracing):
    stdin_file = tmp_path / "guest_input.txt"
    stdin_file.write_text("initial input", encoding="utf-8")
    with RenderingSession(cache_dir=tmp_path) as session:
        session.generate_trace(Path("/jdk"), "source", stdin_file=stdin_file)
        session.generate_trace(Path("/jdk"), "source", stdin_file=stdin_file)
        assert tracing.call_count == 1

        # Modify file content
        stdin_file.write_text("changed input", encoding="utf-8")
        session.generate_trace(Path("/jdk"), "source", stdin_file=stdin_file)
        assert tracing.call_count == 2


def test_trace_jdk_identity_and_payload_corruption(tmp_path, tracing):
    jdk = tmp_path / "jdk"
    jdk.mkdir()
    release = jdk / "release"
    release.write_text("version-a")
    cache = tmp_path / "traces"
    with RenderingSession(cache_dir=cache) as session:
        session.generate_trace(jdk, "source")
    path = next(cache.glob("*.json"))
    payload = json.loads(path.read_text())
    payload["trace"] = {"incorrect": "payload"}
    path.write_text(json.dumps(payload))
    with RenderingSession(cache_dir=cache) as session:
        session.generate_trace(jdk, "source")
    assert tracing.call_count == 2
    release.write_text("version-b")
    with RenderingSession(cache_dir=cache) as session:
        session.generate_trace(jdk, "source")
    assert tracing.call_count == 3


def test_failed_trace_is_not_cached(tmp_path, tracing):
    tracing.side_effect = [RuntimeError("java failed"), '{"-1": {"trace": []}}']
    with RenderingSession(cache_dir=tmp_path) as session:
        with pytest.raises(RuntimeError, match="java failed"):
            session.generate_trace(Path("/jdk"), "source")
        assert not list(tmp_path.iterdir())
        session.generate_trace(Path("/jdk"), "source")
    assert tracing.call_count == 2


def test_lambda_wrapping_matches_legacy_capture():
    from io import BytesIO

    from PIL import Image

    from cs1302_code_visualizer import browser_driver

    code = """public class Main {
 public static void main(String[] args) {
  int x = 42;
  String s = "hello";
  final java.util.function.Function<Integer, Integer> f = (Integer num) -> num + 1;
 }
}"""
    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()
    traces = json.loads(trace_generator.generate_trace(java_home, code, breakpoints={-1}, type_style="simple"))
    frame = json.dumps(traces["-1"])
    expected = browser_driver.generate_image(frame)
    with RenderingSession() as session:
        actual = browser_driver.generate_image(frame, session=session)
    a = Image.open(BytesIO(actual)).convert("RGBA")
    b = Image.open(BytesIO(expected)).convert("RGBA")
    assert a.size == b.size
    assert a.tobytes() == b.tobytes()
