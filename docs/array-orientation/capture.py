"""Capture real browser screenshots of the array orientation fixtures.

Run with: uv run python docs/array-orientation/capture.py
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
    "dimensions": [
        ("horizontal", {}, 0),
        ("vertical", {"arrayOrientation": "vertical"}, 0),
        ("alternate-horizontal", {"alternateArrayOrientations": True}, 0),
        ("alternate-horizontal", {"alternateArrayOrientations": True}, 1),
        ("horizontal-override", {"arrayOrientations": {"4": "vertical"}}, 0),
    ],
    "edges": [("vertical", {"arrayOrientation": "vertical"}, 0)],
}


def main():
    """Render the representative configurations and save their screenshots."""
    parser = argparse.ArgumentParser(description=__doc__)
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
    (HERE / "images").mkdir(exist_ok=True)
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
                for name, config, step in CASES[fixture]:
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
                    if step:
                        driver.execute_script("instance.visualizer.stepForward()")
                    driver.execute_async_script("""const done = arguments[0];
                        document.fonts.ready.then(() => requestAnimationFrame(() => {
                            instance.redrawConnectors();
                            requestAnimationFrame(done);
                        }));""")
                    element = driver.find_element("id", "capture")
                    filename = f"{fixture}-{name}-step{step}.png"
                    element.screenshot(str(HERE / "images" / filename))
                    errors = [e for e in driver.get_log("browser") if e["level"] == "SEVERE"]
                    if errors:
                        raise RuntimeError(errors)
                    print(filename, flush=True)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
