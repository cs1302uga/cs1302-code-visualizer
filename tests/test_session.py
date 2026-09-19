import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

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
    with RenderingSession(cache_traces=True) as session, pytest.raises(TypeError):
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


def test_browser_only_session_executes_each_trace_request(tracing):
    with RenderingSession() as session:
        for _ in range(2):
            assert session.generate_trace(Path("/jdk"), "source") == '{"-1": {"trace": []}}'
    assert tracing.call_count == 2
    assert trace_generator.ensure_code_tracer_installed.call_count == 2


def test_memory_trace_cache_requires_explicit_opt_in(tracing):
    with RenderingSession(cache_traces=True) as session:
        for _ in range(2):
            session.generate_trace(Path("/jdk"), "source")
    assert tracing.call_count == 1


def test_browser_configuration_change_replaces_idle_browser():
    factory = Mock(side_effect=lambda **kwargs: Mock())
    with RenderingSession(max_browsers=1) as session:
        with session.browser(1, factory, configuration=(True, False)) as first:
            pass
        with session.browser(1, factory, configuration=(False, False)) as second:
            assert second is not first
        first.quit.assert_called_once()
    assert factory.call_count == 2
    second.quit.assert_called_once()


def test_reset_failure_discards_browser_without_retry():
    first = Mock()
    second = Mock()
    factory = Mock(side_effect=[first, second])
    with RenderingSession(max_browsers=1) as session:
        with session.browser(1, factory):
            pass
        first.set_window_size.side_effect = RuntimeError("reset failed")
        with pytest.raises(RuntimeError, match="reset failed"), session.browser(1, factory):
            pytest.fail("failed reset must not lend browser")
        first.quit.assert_called_once()
        assert factory.call_count == 1
        with session.browser(1, factory) as replacement:
            assert replacement is second
    second.quit.assert_called_once()


def test_render_sequence_is_order_independent():
    from io import BytesIO

    from PIL import Image

    from cs1302_code_visualizer import browser_driver

    root = Path(__file__).resolve().parents[1] / "small-trace-examples"
    traces = [(root / f"example{i}/Driver.java.json").read_text() for i in (0, 4)]
    cases = [
        (traces[0], {"dpi": 1, "include_types": False}),
        (traces[1], {"dpi": 1, "text_memory_labels": True}),
        (traces[0], {"dpi": 2, "strip_type_prefixes": ["java.lang."]}),
        (traces[1], {"dpi": 1, "visualizer": "json-pre"}),
    ]

    def pixels(data):
        with Image.open(BytesIO(data)) as image:
            return image.size, image.convert("RGBA").tobytes()

    expected = [pixels(browser_driver.generate_image(trace, **options)) for trace, options in cases]
    with RenderingSession(max_browsers=1) as session:
        for index in [0, 1, 2, 3, 3, 2, 1, 0]:
            trace, options = cases[index]
            assert pixels(browser_driver.generate_image(trace, session=session, **options)) == expected[index]


def test_close_while_preparing_cache_key_prevents_trace_execution(tracing, monkeypatch):
    with RenderingSession(cache_traces=True) as session:
        def tracer_identity():
            session.close()
            return "url", "version-a"

        monkeypatch.setattr(trace_generator, "read_tracer_url_and_sum_from_toml", tracer_identity)
        with pytest.raises(RuntimeError, match="closed"):
            session.generate_trace(Path("/jdk"), "source")
    tracing.assert_not_called()


def test_session_batch_tracer_lifecycle_and_validation():
    with pytest.raises(ValueError, match="tracer_workers must be positive"):
        RenderingSession(tracer_workers=0)
    with pytest.raises(ValueError, match="max_jobs_per_worker must be positive"):
        RenderingSession(max_jobs_per_worker=0)

    with patch("cs1302_code_visualizer.batch_tracer.ensure_jdk_installed"), patch(
        "cs1302_code_visualizer.batch_tracer.ensure_code_tracer_installed"
    ):
        session = RenderingSession(tracer_workers=2, max_jobs_per_worker=50, extra_jvm_args=["-Xmx128m"])
        # Lazily created
        bt = session.batch_tracer
        assert bt is not None
        assert session.batch_tracer is bt
        session.close()
        assert session._closed is True
        with pytest.raises(RuntimeError, match="closed"):
            _ = session.batch_tracer


def test_session_generate_trace_batch_tracer(tmp_path):
    mock_batch_client = Mock()
    mock_batch_client.execute.return_value = {
        "status": "completed",
        "trace": [{"line": 1, "event": "step_line"}],
    }

    stdin_file = tmp_path / "in.txt"
    stdin_file.write_text("file content", encoding="utf-8")

    session = RenderingSession(use_batch_tracer=True, cache_traces=True, cache_dir=tmp_path / "cache")
    session._batch_tracer = mock_batch_client

    with patch("cs1302_code_visualizer.trace_generator.read_tracer_url_and_sum_from_toml", return_value=("u", "s")):
        # First call hits batch_tracer.execute
        res = session.generate_trace(
            Path("/jdk"),
            "public class A {}",
            stdin_file=stdin_file,
            breakpoints={5, 10},
            extra_tracer_args=["-a"],
        )
        assert json.loads(res) == mock_batch_client.execute.return_value
        assert mock_batch_client.execute.call_count == 1
        job_arg = mock_batch_client.execute.call_args[0][0]
        assert job_arg.stdin == "file content"
        assert job_arg.all_breakpoints is True
        assert job_arg.breakpoints == [5, 10]

        # Second identical call hits memory cache
        res2 = session.generate_trace(
            Path("/jdk"),
            "public class A {}",
            stdin_file=stdin_file,
            breakpoints={5, 10},
            extra_tracer_args=["-a"],
        )
        assert res2 == res
        assert mock_batch_client.execute.call_count == 1

        # Unsupported extra args triggers fallback to trace_generator.generate_trace
        with patch("cs1302_code_visualizer.trace_generator.generate_trace", return_value='{"legacy": true}') as mock_gen, patch(
            "cs1302_code_visualizer.trace_generator.ensure_code_tracer_installed"
        ):
            fallback_res = session.generate_trace(
                Path("/jdk"),
                "public class B {}",
                extra_tracer_args=["--some-unsupported-arg"],
            )
            assert fallback_res == '{"legacy": true}'
            assert mock_gen.call_count == 1

    session.close()


def test_session_generate_trace_uncached_batch(tmp_path):
    mock_batch_client = Mock()
    mock_batch_client.execute.return_value = {"trace": []}

    session = RenderingSession(use_batch_tracer=True, cache_traces=False)
    session._batch_tracer = mock_batch_client

    res = session.generate_trace(
        Path("/jdk"),
        "public class C {}",
        timeout_secs=5,
    )
    assert json.loads(res) == {"trace": []}
    assert mock_batch_client.execute.call_count == 1
    session.close()


def test_session_generate_trace_batch_extra_args_all_breakpoints():
    mock_batch_client = Mock()
    mock_batch_client.execute.return_value = {"trace": []}

    session = RenderingSession(use_batch_tracer=True, cache_traces=False)
    session._batch_tracer = mock_batch_client

    res = session.generate_trace(
        Path("/jdk"),
        "public class C {}",
        extra_tracer_args=["-a"],
    )
    assert json.loads(res) == {"trace": []}
    job_arg = mock_batch_client.execute.call_args[0][0]
    assert job_arg.all_breakpoints is True
    session.close()


def test_session_generate_trace_batch_unreadable_stdin_file(tmp_path):
    from cs1302_code_visualizer.errors import CodeVisTraceGeneratorError

    session = RenderingSession(use_batch_tracer=True, cache_traces=False)
    session._batch_tracer = Mock()
    with pytest.raises(CodeVisTraceGeneratorError, match="Unable to read stdin file"):
        session.generate_trace(
            Path("/jdk"),
            "public class D {}",
            stdin_file=tmp_path / "non_existent.txt",
        )
    session.close()
