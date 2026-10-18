"""Real binary-only generic metadata survives tracing and SVG export."""

import json
import subprocess
from xml.etree import ElementTree as ET

import pytest

from cs1302_code_visualizer import browser_driver, trace_generator

SOURCE = """import dependency.Leaf;
import dependency.View;
public class Main {
    public static void main(String[] args) {
        View<String> value = new Leaf<String>();
        System.out.println(value != null);
    }
}
"""


@pytest.fixture(scope="module")
def generic_library(tmp_path_factory):
    java_home = trace_generator.ensure_jdk_installed()
    trace_generator.ensure_code_tracer_installed()
    root = tmp_path_factory.mktemp("binary generic library")
    classes = root / "classes"
    classes.mkdir()
    sources = {
        "View": "public interface View<T> {}",
        "Box": "public class Box<E> { public E item; public Box<E> next; }",
        "Middle": "public class Middle<U> extends Box<U> implements View<U> {"
        " public java.util.Comparator<U> comparator ="
        " java.util.Comparator.<U>comparingInt(value -> 0); }",
        "Leaf": "public class Leaf<X> extends Middle<X> {}",
    }
    paths = []
    for name, declaration in sources.items():
        path = root / f"{name}.java"
        path.write_text(f"package dependency; {declaration}\n", encoding="utf-8")
        paths.append(str(path))
    subprocess.run(
        [str(java_home / "bin/javac"), "-g:none", "-d", str(classes), *paths],
        capture_output=True,
        text=True,
        check=True,
    )
    library = root / "generic library.jar"
    subprocess.run(
        [str(java_home / "bin/jar"), "--create", "--file", str(library), "-C", str(classes), "."],
        capture_output=True,
        text=True,
        check=True,
    )
    for name in sources:
        (root / f"{name}.java").unlink()
    return java_home, library


@pytest.mark.parametrize("trace_format", ["pytutor", "modern"])
def test_binary_generic_null_fields_reach_svg(generic_library, rendering_session, trace_format):
    java_home, library = generic_library
    trace_text = trace_generator.generate_trace(
        java_home,
        SOURCE,
        all_breakpoints=True,
        type_style="fqn",
        extra_tracer_args=[
            f"--class-path={library}",
            f"--format={trace_format}",
        ],
    )
    trace = json.loads(trace_text)
    assert trace["code"] == SOURCE
    assert trace["entryFile"] == "Main.java"
    assert trace["sources"] == {"Main.java": SOURCE}
    if trace_format == "modern":
        final = trace["steps"][-1]
        value = next(
            obj for obj in final["heap"].values() if obj["type"].startswith("dependency.Leaf")
        )
        heading = value["type"]
        fields = {field["name"]: field["type"] for field in value["fields"]}
        # Modern omits value members for null fields.
        values = {field["name"]: field.get("value") for field in value["fields"]}
        comparator_id = str(values["comparator"]["ref"])
        comparator = final["heap"][comparator_id]
        comparator_heading = comparator["type"]
    else:
        final = trace["trace"][-1]
        identity, value = next(
            (key, obj)
            for key, obj in final["heap"].items()
            if obj[0] == "INSTANCE" and obj[1].startswith("dependency.Leaf")
        )
        heading = value[1]
        fields = dict(
            zip(
                [field[0] for field in value[2:]],
                final["heap_attrs"][identity]["type"],
                strict=True,
            )
        )
        values = dict(value[2:])
        comparator_id = str(values["comparator"][1])
        comparator = final["heap"][comparator_id]
        comparator_heading = comparator[1]
    assert final["stdout"] == "true\n"
    assert heading == "dependency.Leaf<java.lang.String>"
    assert fields == {
        "item": "java.lang.String",
        "next": "dependency.Box<java.lang.String>",
        "comparator": "java.util.Comparator<java.lang.String>",
    }
    assert values["item"] is None
    assert values["next"] is None
    assert comparator_heading == "java.util.Comparator<java.lang.String>λ"

    svg = ET.fromstring(
        browser_driver.generate_image(
            trace_text, format="SVG", strip_type_prefixes=[], session=rendering_session
        )
    )
    labels = [
        "".join(element.itertext()) for element in svg.iter("{http://www.w3.org/2000/svg}text")
    ]
    assert any(label.startswith("dependency.Leaf<java.lang.String>@") for label in labels)
    assert "dependency.Box<java.lang.String>" in labels
    assert "java.util.Comparator<java.lang.String>" in labels
    assert f"{comparator_heading}@{comparator_id}" in labels
