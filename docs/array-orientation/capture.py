"""Capture real browser screenshots of the array orientation fixtures.

Run with: uv run --no-project --with selenium python docs/array-orientation/capture.py
Use --phase before against a build of the baseline revision first.
"""

import argparse
import json
import tempfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CASES = {
    "horizontal": {},
    "vertical": {"arrayOrientation": "vertical"},
    "alternate-horizontal": {"alternateArrayOrientations": True},
    "alternate-vertical": {
        "arrayOrientation": "vertical",
        "alternateArrayOrientations": True,
    },
    "horizontal-override": {"arrayOrientations": {"4": "vertical"}},
    "vertical-override": {
        "arrayOrientation": "vertical",
        "arrayOrientations": {"4": "horizontal"},
    },
    "alternate-horizontal-override": {
        "alternateArrayOrientations": True,
        "arrayOrientations": {"2": "horizontal"},
    },
    "alternate-vertical-override": {
        "arrayOrientation": "vertical",
        "alternateArrayOrientations": True,
        "arrayOrientations": {"2": "vertical"},
    },
}


def main():
    """Render each configuration and save its screenshots and capture manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["before", "after"], default="after")
    parser.add_argument(
        "--build", type=Path, default=ROOT / "cs1302_code_visualizer/frontend/build"
    )
    args = parser.parse_args()
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--allow-file-access-from-files")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--hide-scrollbars")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1280, 1200)
    captures = []
    try:
        with tempfile.TemporaryDirectory() as temp:
            page = Path(temp) / "gallery.html"
            bundle = (args.build.resolve() / "vis-module.bundle.js").as_uri()
            page.write_text(f"""<!doctype html><meta charset="utf-8">
<style>body {{margin:0;background:#fff}} #capture {{padding:24px;width:1200px;box-sizing:border-box;min-height:560px}}</style>
<div id="capture"><div id="visualizer"></div></div>
<script src="{bundle}"></script>""")
            for fixture in ["dimensions", "edges"]:
                trace = json.loads((HERE / "fixtures" / f"{fixture}.json").read_text())
                cases = (
                    CASES
                    if fixture == "dimensions"
                    else {
                        "horizontal": {},
                        "vertical": {"arrayOrientation": "vertical"},
                        "alternate": {"alternateArrayOrientations": True},
                    }
                )
                if args.phase == "before":
                    cases = {"horizontal": {}}
                for name, config in cases.items():
                    driver.get(page.as_uri())
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script("return !!window.CodeVisualizer")
                    )
                    driver.execute_script(
                        """window.instance = CodeVisualizer.create({
                        lang: 'java', element: document.getElementById('visualizer'),
                        trace: arguments[0], options: arguments[1]});
                        instance.visualizer.stepBack();""",
                        trace,
                        config,
                    )
                    for step in [0, 1]:
                        if step:
                            driver.execute_script("instance.visualizer.stepForward()")
                        driver.execute_async_script("""const done = arguments[0];
                            document.fonts.ready.then(() => requestAnimationFrame(() => {
                                instance.redrawConnectors();
                                requestAnimationFrame(done);
                            }));""")
                        element = driver.find_element("id", "capture")
                        filename = f"{args.phase}-{fixture}-{name}-step{step}.png"
                        element.screenshot(str(HERE / "images" / filename))
                        errors = [e for e in driver.get_log("browser") if e["level"] == "SEVERE"]
                        if errors:
                            raise RuntimeError(errors)
                        captures.append({
                            "image": filename,
                            "fixture": fixture,
                            "step": step,
                            "options": config,
                        })
                        print(filename, flush=True)
    finally:
        driver.quit()
    (HERE / f"{args.phase}-captures.json").write_text(json.dumps(captures, indent=2) + "\n")


if __name__ == "__main__":
    main()
