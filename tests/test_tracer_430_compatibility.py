"""Real-JAR regressions for tracer 4.3 time components and live set views."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from cs1302_code_visualizer.batch_tracer import BatchTraceJob, BatchTracerClient
from cs1302_code_visualizer.browser_driver import generate_image
from cs1302_code_visualizer.trace_generator import (
    ensure_code_tracer_installed,
    ensure_jdk_installed,
    generate_trace,
)

SOURCE = (Path(__file__).resolve().parents[1] / "docs/tracer-compatibility/Main.java").read_text()
LOCAL_NAMES = {
    "date",
    "time",
    "meeting",
    "original",
    "elapsed",
    "item",
    "backing",
    "view",
    "second",
    "alias",
}


@pytest.fixture(scope="module")
def java_home():
    ensure_code_tracer_installed()
    return ensure_jdk_installed()


def reference(value, trace_format):
    return str(value["ref"] if trace_format == "modern" else value[1])


def fields(value, trace_format):
    if trace_format == "modern":
        return {field["name"]: field.get("value") for field in value["fields"]}
    return dict(value[2:])


def elements(value, trace_format):
    if trace_format == "modern":
        assert value["kind"] == "array"
        return value["elements"]
    assert value[0] == "SET"
    return value[1:]


def complete_states(trace, trace_format):
    states = []
    for step in trace["steps" if trace_format == "modern" else "trace"]:
        for frame in step["callStack" if trace_format == "modern" else "stack_to_render"]:
            locals_ = (
                {local["name"]: local["value"] for local in frame["locals"]}
                if trace_format == "modern"
                else frame["encoded_locals"]
            )
            if LOCAL_NAMES <= locals_.keys():
                states.append((step, locals_))
    assert states, "No state captured all representative locals"
    return states


def assert_compatibility(trace, trace_format, initial_value=1):
    states = complete_states(trace, trace_format)
    observed = []
    for step, locals_ in states:
        heap = step["heap"]
        ids = {name: reference(locals_[name], trace_format) for name in LOCAL_NAMES}
        meeting = fields(heap[ids["meeting"]], trace_format)
        assert reference(meeting["date"], trace_format) == ids["date"]
        assert reference(meeting["time"], trace_format) == ids["time"]
        assert fields(heap[ids["date"]], trace_format) == {"year": 2024, "month": 2, "day": 29}
        assert fields(heap[ids["time"]], trace_format) == {
            "hour": 12,
            "minute": 30,
            "second": 0,
            "nano": 123456789,
        }
        assert ids["original"] != ids["elapsed"]
        assert fields(heap[ids["original"]], trace_format) == {"seconds": -1, "nanos": 999999999}
        assert fields(heap[ids["elapsed"]], trace_format) == {"seconds": 1, "nanos": 999999999}
        if trace_format == "modern":
            duration_fields = heap[ids["original"]]["fields"]
            assert [
                (field["name"], field["type"], field["final"]) for field in duration_fields
            ] == [("seconds", "long", True), ("nanos", "int", True)]

        assert ids["view"] == ids["alias"]
        assert len({ids["backing"], ids["view"], ids["second"]}) == 3
        contents = elements(heap[ids["backing"]], trace_format)
        assert elements(heap[ids["view"]], trace_format) == contents
        assert elements(heap[ids["second"]], trace_format) == contents
        assert reference(contents[0], trace_format) == ids["item"]
        assert contents[1] is None
        assert len(contents) in (2, 3)
        if len(contents) == 3:
            last = heap[reference(contents[2], trace_format)]
            assert (last["value"] if trace_format == "modern" else last[2][1]) == "last"
        observed.append((len(contents), fields(heap[ids["item"]], trace_format)["value"]))
    assert observed[0] == (2, initial_value)
    assert observed[-1] == (3, 2)
    assert "PT-0.000000001S\nPT1.999999999S\n" in states[-1][0]["stdout"]
    return states[-1]


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
def test_time_and_set_graphs_reach_rendered_exports(
    java_home, trace_format, rendering_session, tmp_path
):
    raw = generate_trace(
        java_home,
        SOURCE,
        all_breakpoints=True,
        extra_tracer_args=[f"--format={trace_format}"],
        timeout_secs=60,
    )
    # Retain the actual JAR payload for inspection and fixture regeneration.
    (tmp_path / f"{trace_format}.json").write_text(raw)
    trace = json.loads(raw)
    step, locals_ = assert_compatibility(trace, trace_format)
    final = {**trace, "steps" if trace_format == "modern" else "trace": [step]}
    svg = generate_image(json.dumps(final), format="SVG", session=rendering_session)
    root = ET.fromstring(svg)
    text = " ".join(root.itertext())
    assert "999999999" in text
    assert "LocalDateTime" in text and "Duration" in text
    assert "UnmodifiableSet" in text and "size 3" in text
    assert "null" in text and "last" in text
    metadata = root.find("{http://www.w3.org/2000/svg}metadata")
    assert metadata is not None
    description = json.loads(metadata.text)
    sections = description["sections"]
    view_id = reference(locals_["view"], trace_format)
    item_id = reference(locals_["item"], trace_format)
    assert (
        sum(section["heading"].startswith(f"Heap object {view_id}:") for section in sections) == 1
    )
    assert f"reference to object {view_id}" in str(sections)
    assert f"reference to object {item_id}" in str(sections)


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
def test_consecutive_batch_jobs_keep_time_and_set_state_job_local(java_home, trace_format):
    with BatchTracerClient(java_home=java_home, workers=1) as client:
        for value in (1, 7):
            source = SOURCE.replace("int value = 1;", f"int value = {value};")
            trace = client.submit(BatchTraceJob(source=source, format=trace_format)).result(
                timeout=60
            )
            # The second job changes a stored initial component, proving this is
            # a fresh guest snapshot rather than a reused first-job result.
            assert_compatibility(trace, trace_format, initial_value=value)
