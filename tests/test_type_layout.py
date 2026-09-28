"""Browser checks for type space reserved across supplied execution states."""

import copy
import json

from cs1302_code_visualizer import browser_driver
from tests.test_map_rendering import FIXTURE


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
