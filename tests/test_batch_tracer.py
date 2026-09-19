"""Unit tests for code-tracer batch-trace client."""

import concurrent.futures
import io
import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cs1302_code_visualizer.batch_tracer import (
    BatchTraceJob,
    BatchTracerClient,
)
from cs1302_code_visualizer.errors import CodeVisTraceGeneratorError


def test_batch_trace_job_defaults_and_conversion():
    job = BatchTraceJob(source="public class Main {}")
    req = job.to_request_dict()
    assert req["source"] == "public class Main {}"
    assert req["format"] == "pytutor"
    assert req["stdin"] == ""
    assert "breakpoints" not in req
    assert req["allBreakpoints"] is True
    assert req["typeStyle"] == "simple"
    assert req["limits"]["timeoutMillis"] == 30000

    custom_job = BatchTraceJob(
        id="job-123",
        source="public class Custom {}",
        stdin="hello",
        breakpoints=[5, 10],
        all_breakpoints=True,
        accumulate_breakpoints=True,
        remove_main_args=False,
        inline_strings=True,
        remove_method_this=True,
        type_style="fqn",
        timeout_ms=5000,
        max_snapshots=100,
        inspection="FIELDS",
    )
    custom_req = custom_job.to_request_dict()
    assert custom_req["id"] == "job-123"
    assert custom_req["breakpoints"] == ["5", "10"]
    assert custom_req["allBreakpoints"] is True
    assert custom_req["accumulateBreakpoints"] is True
    assert custom_req["removeMainArgs"] is False
    assert custom_req["inlineStrings"] is True
    assert custom_req["removeMethodThis"] is True
    assert custom_req["typeStyle"] == "fqn"
    assert custom_req["limits"]["timeoutMillis"] == 5000
    assert custom_req["limits"]["snapshots"] == 100
    assert custom_req["inspection"] == "FIELDS"


def test_batch_tracer_client_validation():
    with pytest.raises(ValueError, match="workers must be positive"):
        BatchTracerClient(workers=0)
    with pytest.raises(ValueError, match="max_jobs_per_worker must be positive"):
        BatchTracerClient(max_jobs_per_worker=0)


class MockPipe:
    def __init__(self):
        self._lines: list[str] = []
        self._index: int = 0
        self._closed: bool = False
        self._cond = threading.Condition()

    def feed_line(self, line: str):
        with self._cond:
            self._lines.append(line + "\n")
            self._cond.notify_all()

    def readline(self) -> str:
        with self._cond:
            while self._index >= len(self._lines) and not self._closed:
                self._cond.wait(timeout=0.1)
            if self._index < len(self._lines):
                line = self._lines[self._index]
                self._index += 1
                return line
            return ""

    def close(self):
        with self._cond:
            self._closed = True
            self._cond.notify_all()


class MockProcess:
    def __init__(self):
        self.stdin = io.StringIO()
        self.stdout = MockPipe()
        self.stderr = MockPipe()
        self.stderr.close()
        self.returncode = None
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def communicate(self, *args, **kwargs):
        return ("stdout", "stderr")

    def end_stdout(self):
        self.returncode = 0
        self.stdout.close()

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = 0
        self.stdout.close()
        self.stderr.close()

    def kill(self):
        self.returncode = -9
        self.stdout.close()
        self.stderr.close()

    def close(self):
        self._closed = True
        self.returncode = 0
        self.stdout.close()
        self.stderr.close()


@pytest.fixture
def mock_tracer_env(monkeypatch):
    monkeypatch.setattr(
        "cs1302_code_visualizer.batch_tracer.ensure_jdk_installed",
        lambda: Path("/mock/jdk"),
    )
    monkeypatch.setattr(
        "cs1302_code_visualizer.batch_tracer.ensure_code_tracer_installed",
        lambda: None,
    )


def test_batch_tracer_client_successful_execution(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient(workers=2, extra_jvm_args=["-Xmx256m"])
    job = BatchTraceJob(id="test-1", source="class Foo {}")

    mock_resp = {
        "id": "test-1",
        "result": {
            "status": "completed",
            "phase": "trace",
            "trace": {
                "code": "class Foo {}",
                "trace": [
                    {
                        "line": 1,
                        "event": "step_line",
                        "ordered_globals": [],
                        "stack_to_render": [],
                        "heap": {},
                    }
                ],
            },
        },
    }
    mock_proc.stdout.feed_line(json.dumps(mock_resp))

    result = client.execute(job, timeout_secs=2.0)
    assert result["code"] == "class Foo {}"
    assert len(result["trace"]) == 1
    assert result["trace"][0]["line"] == 1

    client.close()
    assert client._closed is True
    with pytest.raises(RuntimeError, match="BatchTracerClient is closed"):
        client.submit(job)


def test_batch_tracer_client_failed_trace(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient()
    job = BatchTraceJob(id="fail-job", source="invalid java code")

    mock_resp = {
        "id": "fail-job",
        "result": {
            "status": "failed",
            "phase": "compile",
            "diagnostics": ["Syntax error on token Foo"],
        },
    }
    mock_proc.stdout.feed_line(json.dumps(mock_resp))

    with pytest.raises(CodeVisTraceGeneratorError) as exc_info:
        client.execute(job, timeout_secs=2.0)
    assert "Syntax error on token Foo" in exc_info.value.stderr
    client.close()


def test_batch_tracer_client_eof_fails_pending_and_respawns(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient()
    job = BatchTraceJob(id="pending-job", source="class A {}")
    fut = client.submit(job)

    # End the process unexpectedly (EOF on stdout)
    mock_proc.end_stdout()

    with pytest.raises(CodeVisTraceGeneratorError, match="terminated unexpectedly"):
        fut.result(timeout=2.0)

    # Subsequent submission respawns new process
    mock_proc2 = MockProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc2)
    mock_resp = {
        "id": "new-job",
        "result": {
            "status": "completed",
            "trace": {"code": "class B {}", "trace": []},
        },
    }
    mock_proc2.stdout.feed_line(json.dumps(mock_resp))
    job2 = BatchTraceJob(id="new-job", source="class B {}")
    res = client.execute(job2, timeout_secs=2.0)
    assert res["code"] == "class B {}"
    client.close()


def test_batch_tracer_client_malformed_and_unknown_lines(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient()
    job = BatchTraceJob(id="valid-job", source="class C {}")
    fut = client.submit(job)

    # Send malformed JSON line
    mock_proc.stdout.feed_line("{invalid json line")
    # Send unknown ID
    mock_proc.stdout.feed_line(
        json.dumps({"id": "unknown-id", "result": {"status": "completed", "trace": {}}})
    )
    # Send valid response
    mock_proc.stdout.feed_line(
        json.dumps(
            {
                "id": "valid-job",
                "result": {
                    "status": "completed",
                    "trace": {"code": "class C {}", "trace": []},
                },
            }
        )
    )

    res = fut.result(timeout=2.0)
    assert res["code"] == "class C {}"
    client.close()


def test_batch_tracer_client_timeout(mock_tracer_env):
    mock_proc = MockProcess()
    with patch("subprocess.Popen", return_value=mock_proc):
        client = BatchTracerClient()
        job = BatchTraceJob(id="timeout-job", source="class D {}")
        with pytest.raises(TimeoutError):
            client.execute(job, timeout_secs=0.05)
        client.close()


def test_batch_tracer_client_stdin_error(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    broken_stdin = Mock()
    broken_stdin.write.side_effect = OSError("Broken pipe")
    broken_stdin.closed = False
    mock_proc.stdin = broken_stdin

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient()
    job = BatchTraceJob(id="broken-job", source="class E {}")
    with pytest.raises(CodeVisTraceGeneratorError, match="Failed to write"):
        client.execute(job)
    client.close()


def test_batch_tracer_client_post_processing():
    client = BatchTracerClient()
    job = BatchTraceJob(id="norm-job", source="", include_enum_static_fields=False)
    fut = concurrent.futures.Future()
    result = {
        "status": "completed",
        "trace": {
            "code": "",
            "trace": [
                {
                    "ordered_globals": ["Day", "NORTH", "COUNT"],
                    "globals": {
                        "Day": ["REF", 1],
                        "NORTH": ["REF", 2],
                        "COUNT": 5,
                    },
                    "stack_to_render": [
                        {
                            "ordered_varnames": ["flag", "num"],
                            "encoded_locals": {
                                "flag": ["REF", 3],
                                "num": ["REF", 4],
                            },
                        }
                    ],
                    "heap": {
                        "1": ["CLASS", "Day", ["$VALUES", ["REF", 5]]],
                        "2": ["INSTANCE", "Day", ["ordinal", 0]],
                        "3": True,
                        "4": 42,
                    },
                }
            ],
        },
    }
    client._handle_response(fut, job, {"result": result})
    processed = fut.result()
    heap = processed["trace"][0]["heap"]
    assert heap["3"][2][1] is True
    assert heap["4"][2][1] == 42


def test_batch_tracer_client_context_manager(mock_tracer_env):
    mock_proc = MockProcess()
    with patch("subprocess.Popen", return_value=mock_proc):
        with BatchTracerClient() as client:
            assert client._closed is False
        assert client._closed is True


def test_batch_tracer_client_ensure_process_existing_and_closed(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient()
    p1 = client._ensure_process()
    p2 = client._ensure_process()
    assert p1 is p2

    client.close()
    with pytest.raises(RuntimeError, match="BatchTracerClient is closed"):
        client._ensure_process()


def test_batch_tracer_drain_stderr_and_various_stdout_lines(mock_tracer_env, monkeypatch):
    mock_proc = MockProcess()
    mock_proc.stderr = MockPipe()
    mock_proc.stderr.feed_line("some stderr message")
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    client = BatchTracerClient()
    job = BatchTraceJob(id="var-job", source="class V {}")
    fut = client.submit(job)

    # Send empty line to stdout
    mock_proc.stdout.feed_line("   ")
    # Send json without id to stdout
    mock_proc.stdout.feed_line(json.dumps({"no_id": True}))
    # Send bad trace shape
    bad_job = BatchTraceJob(id="bad-shape", source="class Bad {}")
    bad_fut = client.submit(bad_job)
    mock_proc.stdout.feed_line(
        json.dumps({"id": "bad-shape", "result": {"status": "completed", "trace": "not-a-dict"}})
    )

    with pytest.raises(TypeError, match="unexpected trace shape"):
        bad_fut.result(timeout=1.0)

    # Send valid response for var-job
    mock_proc.stdout.feed_line(
        json.dumps({"id": "var-job", "result": {"status": "completed", "trace": {"trace": []}}})
    )
    res = fut.result(timeout=1.0)
    assert res == {"trace": []}
    client.close()


def test_batch_tracer_none_streams():
    client = BatchTracerClient()
    proc = Mock()
    proc.stderr = None
    proc.stdout = None
    # Calling directly should return safely
    client._drain_stderr(proc)
    client._reader_loop(proc)


def test_batch_tracer_close_with_pending_and_exceptions(mock_tracer_env):
    client = BatchTracerClient()
    mock_proc = Mock()
    mock_proc.__enter__ = Mock(return_value=mock_proc)
    mock_proc.__exit__ = Mock(return_value=None)
    mock_proc.stdin = Mock()
    mock_proc.stdin.closed = False
    mock_proc.stdout = Mock()
    mock_proc.stdout.readline.return_value = ""
    mock_proc.stdin.close.side_effect = Exception("stdin close err")
    mock_proc.terminate.side_effect = Exception("terminate err")
    mock_proc.kill.side_effect = Exception("kill err")

    client._process = mock_proc
    fut = concurrent.futures.Future()
    job = BatchTraceJob(id="orphan", source="")
    client._pending["orphan"] = (fut, job)

    # Test submit without job id hits line 314 auto-uuid
    job_no_id = BatchTraceJob(source="class NoId {}")
    # Popen mock for submit
    with patch("subprocess.Popen", return_value=mock_proc):
        fut_no_id = client.submit(job_no_id)

    # Make terminate fail, kill succeed, wait fail
    mock_proc.terminate.side_effect = Exception("terminate err")
    mock_proc.kill.side_effect = None
    mock_proc.wait.side_effect = Exception("wait err")

    client.close()
    assert client._closed is True
    assert fut.cancelled()
    assert fut_no_id.cancelled()
    # repeated close hits early return
    client.close()
    with pytest.raises(RuntimeError, match="BatchTracerClient is closed"):
        client.submit(job)


def test_batch_tracer_custom_java_home(tmp_path):
    mock_proc = MockProcess()
    mock_proc.stdout.close()
    with patch("subprocess.Popen", return_value=mock_proc), patch(
        "cs1302_code_visualizer.batch_tracer.ensure_code_tracer_installed"
    ):
        custom_java = tmp_path / "custom_java"
        client = BatchTracerClient(java_home=custom_java)
        proc = client._ensure_process()
        assert proc is mock_proc
        client.close()
