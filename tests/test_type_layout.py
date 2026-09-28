"""Browser checks for type space reserved across supplied execution states."""

import copy
import json
from xml.etree import ElementTree as ET

import pytest

from cs1302_code_visualizer import browser_driver
from tests.test_map_rendering import FIXTURE


@pytest.mark.parametrize("include_types", [True, False])
@pytest.mark.parametrize("globals_frame", [True, False])
@pytest.mark.parametrize("future_name", ["longVariableName", "__return__"])
def test_future_variable_names_do_not_move_existing_columns(
    rendering_session, include_types, globals_frame, future_name
):
    """Reserve future name widths even when declared-type labels are hidden."""
    trace = json.loads(FIXTURE.read_text())
    first = trace["trace"][0]
    first["heap"] = {}
    first["heap_attrs"] = {}
    frame = first["stack_to_render"][0]
    frame["encoded_locals"] = {"n": 1}
    frame["ordered_varnames"] = ["n"]
    frame["locals_attrs"] = {"n": {"type": "int"}}
    later = copy.deepcopy(first)
    later_frame = later["stack_to_render"][0]
    later_frame["encoded_locals"][future_name] = 2
    later_frame["ordered_varnames"].append(future_name)
    later_frame["locals_attrs"][future_name] = {"type": "int"}
    trace["trace"] = [first, later]
    if globals_frame:
        for state in trace["trace"]:
            local = state["stack_to_render"][0]
            state["globals"] = local["encoded_locals"]
            state["ordered_globals"] = local["ordered_varnames"]
            state["globals_attrs"] = local["locals_attrs"]
            state["stack_to_render"] = []
    with browser_driver.online_python_tutor_frontend(
        json.dumps(trace), include_types=include_types, session=rendering_session
    ) as frontend:
        positions = frontend["driver"].execute_script("""
            return [0, 1, 0].map(step => {
                window.optFrontend.renderStep(step);
                const row=document.querySelector('.stackFrameVarTable tr');
                const name=row.querySelector('.stackVarName');
                const range=document.createRange(); range.selectNodeContents(name);
                return [range.getBoundingClientRect().right,
                    row.querySelector('.stackFrameValue').getBoundingClientRect().left];
            });
        """)
        for name_right, value_left in positions[1:]:
            assert name_right == pytest.approx(positions[0][0], abs=0.1)
            assert value_left == pytest.approx(positions[0][1], abs=0.1)


@pytest.mark.parametrize("include_types", [True, False])
@pytest.mark.parametrize("globals_frame", [True, False])
def test_stack_columns_align_independently_of_variable_name(
    rendering_session, include_types, globals_frame
):
    """Unequal names, mixed types, and untyped return values retain column alignment."""
    trace = json.loads(FIXTURE.read_text())
    state = trace["trace"][0]
    trace["trace"] = [state]
    state["heap"] = {}
    state["heap_attrs"] = {}
    names = ["str", "other", "alias", "this", "n", "__return__"]
    frame = state["stack_to_render"][0]
    frame["encoded_locals"] = dict.fromkeys(names, None)
    frame["ordered_varnames"] = names
    frame["locals_attrs"] = {
        name: {"type": "int" if name == "n" else "String"} for name in names[:-1]
    }
    if globals_frame:
        state["globals"] = frame["encoded_locals"]
        state["ordered_globals"] = names
        state["globals_attrs"] = frame["locals_attrs"]
        state["stack_to_render"] = []
    with browser_driver.online_python_tutor_frontend(
        json.dumps(trace), include_types=include_types, session=rendering_session
    ) as frontend:
        result = frontend["driver"].execute_script("""
            const rows=[...document.querySelectorAll('.stackFrameVarTable tr')];
            return rows.map(row=>{
                const cell=row.querySelector('.stackFrameVar');
                const type=cell.querySelector('.fieldTypeLabel');
                const name=cell.lastChild;
                const range=document.createRange(); range.selectNodeContents(name);
                const n=range.getBoundingClientRect();
                const t=type?.getBoundingClientRect();
                const v=row.querySelector('.stackFrameValue').getBoundingClientRect();
                return {typeLeft:t?.left, typeRight:t?.right,
                    nameLeft:n.left, nameRight:n.right, valueLeft:v.left};
            });
        """)
        for column in ("nameRight", "valueLeft"):
            positions = [row[column] for row in result[:-1]]
            assert max(positions) - min(positions) < 0.1, column
        if include_types:
            positions = [row["typeLeft"] for row in result[:-1]]
            assert max(positions) - min(positions) < 0.1, "typeLeft"
            assert all(row["typeRight"] < row["nameLeft"] for row in result[:-1])
        else:
            assert all(row["typeLeft"] is None for row in result)
        assert all(row["nameRight"] < row["valueLeft"] for row in result)

    svg = ET.fromstring(
        browser_driver.generate_image(
            json.dumps(trace), include_types=include_types, format="SVG", session=rendering_session
        )
    )
    types = [
        text
        for text in svg.iter("{http://www.w3.org/2000/svg}text")
        if text.text in {"String", "int"}
    ]
    if include_types:
        assert len(types) == len(names) - 1
        positions = [float(text.attrib["x"]) for text in types]
        assert max(positions) - min(positions) < 0.1
    else:
        assert not types


def test_future_type_width_is_reserved_without_wrapping(rendering_session):
    trace = json.loads(FIXTURE.read_text())
    first = trace["trace"][0]
    first["heap"] = {}
    first["heap_attrs"] = {}
    frame = first["stack_to_render"][0]
    frame["encoded_locals"] = {"n": 1}
    frame["ordered_varnames"] = ["n"]
    frame["locals_attrs"] = {"n": {"type": "int"}}
    later = copy.deepcopy(first)
    later_frame = later["stack_to_render"][0]
    later_frame["encoded_locals"]["map"] = None
    later_frame["ordered_varnames"].append("map")
    later_frame["locals_attrs"]["map"] = {"type": "Map<String, Integer>"}
    widths = []
    for states in ([first, later], [first]):
        trace["trace"] = states
        with browser_driver.online_python_tutor_frontend(
            json.dumps(trace), session=rendering_session
        ) as frontend:
            result = frontend["driver"].execute_script("""
                const v=window.optFrontend;
                const measure=()=>[...document.querySelectorAll('.stackFrameVar .fieldTypeLabel')]
                    .map(e=>({width:e.getBoundingClientRect().width,
                        nowrap:getComputedStyle(e).whiteSpace==='nowrap'}));
                v.renderStep(0); const first=measure();
                v.renderStep(v.curTrace.length-1);
                return {first,last:measure()};
            """)
            widths.append(result["first"][0]["width"])
            assert all(item["nowrap"] for item in result["last"])
            assert all(abs(item["width"] - widths[-1]) < 0.1 for item in result["last"])
    assert widths[0] > widths[1] + 50
