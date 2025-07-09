#!/usr/bin/env python3

import os
import sys
import fileinput
import argparse

from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from io import BytesIO
from PIL import Image

this_files_dir = Path(os.path.realpath(os.path.dirname(__file__)))


def generate_image(trace: str, *, dpi=1, format="PNG") -> bytes:
    """Generate an image of the final state of an OnlinePythonTutor trace file.
    trace:  The OnlinePythonTutor execution trace.
    dpi:    Multiplicative factor for output image resolution (positive integer).
    format: The image output format. This gets passed directly into PIL's Image.save(),
            see that function's docs for details on acceptable values.

    out:    Raw image bytes in the format specified by the format argument.
    """
    frontend_path = (this_files_dir / "frontend" / "iframe-embed.html").as_uri()

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(f"--force-device-scale-factor={dpi}")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)  # only wait 2 secods for element to show up
    driver.get(frontend_path)

    driver.find_element(By.ID, "indicatorElement")

    driver.execute_script(
        "seleniumRunHook(String.raw`" + trace.replace("`", "${'`'}") + "`);"
    )

    viz = driver.find_element(By.ID, "dataViz")
    left, top = (viz.location["x"], viz.location["y"])
    right, bottom = (left + viz.size["width"], top + viz.size["height"])

    # resize the window so it contains the dataViz component
    driver.set_window_size(max(right, 1280), max(bottom, 720))

    # resize again to get rid of the scrollbar (if one exists)
    client_width: int = driver.execute_script(
        "return document.documentElement.clientWidth;"
    )
    client_height: int = driver.execute_script(
        "return document.documentElement.clientHeight;"
    )
    window_width = driver.get_window_size()["width"]
    window_height = driver.get_window_size()["height"]
    width_offset = window_width - client_width
    height_offset = window_height - client_height
    driver.set_window_size(
        max(right + width_offset, 1280), max(bottom + height_offset, 720)
    )

    left, top = (viz.location["x"], viz.location["y"])
    right, bottom = (left + viz.size["width"], top + viz.size["height"])

    screenshot = driver.get_screenshot_as_png()
    driver.quit()

    # crop the screenshot down to the element borders
    screenshot_bytes = BytesIO(screenshot)
    pil_img = Image.open(BytesIO(screenshot)).crop(
        tuple(dpi * x for x in [left, top, right, bottom])
    )
    pil_img.save(screenshot_bytes, format=format)

    return screenshot_bytes.getvalue()


def main():
    parser = argparse.ArgumentParser(
        description="Generate a screenshot from a Java execution trace"
    )

    def require_geq_one(value):
        number = float(value)
        if number < 1:
            raise argparse.ArgumentTypeError(f"Number {value} must be >= 1.")
        return number

    parser.add_argument(
        "--dpi",
        help="DPI scale to apply to the screenshot.",
        type=require_geq_one,
        default=1,
    )

    args = parser.parse_args()

    stdin_data = "".join(fileinput.input("-"))

    image_bytes = generate_image(stdin_data, dpi=args.dpi)

    # dump png to stdout, should be redirected to destination
    sys.stdout.buffer.write(image_bytes)


if __name__ == "__main__":
    main()
