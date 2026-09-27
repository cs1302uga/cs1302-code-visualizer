"""Regenerate the real Java trace and representative production exports."""

import json
from pathlib import Path

from cs1302_code_visualizer import RenderingSession, generate_image
from cs1302_code_visualizer.trace_generator import ensure_jdk_installed, generate_trace

ROOT = Path(__file__).resolve().parent


def main():
    """Capture the supported string styles from one identity-preserving trace."""
    source = (ROOT / "fixtures/Lists.java").read_text()
    raw = generate_trace(ensure_jdk_installed(), source, breakpoints={10}, inline_strings=False)
    (ROOT / "fixtures/lists.json").write_text(raw)
    trace = json.dumps(json.loads(raw)["10"])
    output = ROOT / "images"
    output.mkdir(exist_ok=True)
    cases = [
        ("compact", orientation, theme)
        for orientation in ("horizontal", "vertical")
        for theme in ("light", "dark")
    ]
    cases += [(style, "horizontal", "light") for style in ("default", "inline")]
    with RenderingSession(max_browsers=1) as session:
        for style, orientation, theme in cases:
            for format in ("PNG", "SVG"):
                data = generate_image(
                    trace,
                    string_style=style,
                    array_orientation=orientation,
                    theme=theme,
                    format=format,
                    session=session,
                    strip_type_prefixes=["java.lang."],
                )
                path = output / f"{style}-{orientation}-{theme}.{format.lower()}"
                path.write_bytes(data)
                print(path.name)


if __name__ == "__main__":
    main()
