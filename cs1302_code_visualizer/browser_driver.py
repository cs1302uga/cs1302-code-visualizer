#!/usr/bin/env python3

import os
import sys
import fileinput
import argparse
import logging

from functools import cache
from pathlib import Path
from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from io import BytesIO
from PIL import Image
from urllib.parse import urlencode
from tempfile import NamedTemporaryFile


this_files_dir = Path(os.path.realpath(os.path.dirname(__file__)))


logging.getLogger('selenium').setLevel(logging.DEBUG)
logging.getLogger('selenium.webdriver.remote').setLevel(logging.DEBUG)
logging.getLogger('selenium.webdriver.common').setLevel(logging.DEBUG)


def get_webdriver(dpi: int = 1) -> webdriver.Chrome:
    """Get the webdriver used to display the frontend.

    Args:
        dpi: Dots Per Inch (DPI), a positive integer used to scale the driver's display resolution.

    Return:
        The webdriver used to display the frontend.
    """
    options = Options()
    #options.add_argument("--headless=new")
    options.add_argument(f"--force-device-scale-factor={dpi}")
    options.add_argument("--allow-file-access-from-files")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(2)
    return driver

def tidy_set_font(driver: webdriver.Chrome) -> None:
    """Set the font used by the data visualization."""
    driver.execute_script(
        """
        document.head.insertAdjacentHTML(
            'beforeend',
            `
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Recursive:slnt,wght,CASL,CRSV,MONO@-15..0,300..1000,0..1,0..1,0..1&display=swap" rel="stylesheet">
            <style>
                #dataViz, #dataViz * {
                    font-family: "Recursive", monospace;
                    font-variation-settings: "MONO" 1;
                    font-optical-sizing: auto;
                    font-smooth: auto;
                    -webkit-font-smoothing: auto;
                }
            </style>
            `
        );
        """
    )

def tidy_string_objects(driver: webdriver.Chrome) -> None:
    """Tidy up String instances by removing their instance variable identifiers."""
    driver.execute_script(
        """
        Array
            .from(document.querySelectorAll("#dataViz .heapObject"))
            .filter((element) => element.querySelector(".typeLabel").textContent.includes("String instance"))
            .forEach((element) => element.querySelector(".instKey").remove());
        """
    )

def generate_image(trace: str, *, dpi: int = 1, format: str ="PNG") -> bytes:
    """Generate an image of the final state of an execution trace file.

    The trace file is expected to be formatted using JSON as specified by OnlinePythonTutor.

    Args:
        trace: The execution trace file.
        dpi: Dots Per Inch (DPI), a positive integer used to scale the driver's display resolution.
        format: The image output format. This gets passed directly into PIL's ``Image.save()``.

    Return:
        The bytes of the generated image in the format specified by the ``format`` argument.

    """
    frontend_path = (this_files_dir / "frontend" / "iframe-embed.html").as_uri()
    driver = get_webdriver(dpi)

    trace_file = NamedTemporaryFile()
    with open(trace_file.name, "w") as f:
        print(trace, file=f)

    driver.get(frontend_path + "?" + urlencode({"tracePath": trace_file.name}))

    viz = driver.find_element(By.ID, "dataViz")

    tidy_set_font(driver)
    tidy_string_objects(driver)

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
    trace_file.close()

    # crop the screenshot down to the element borders
    screenshot_bytes = BytesIO(screenshot)
    pil_img = Image.open(BytesIO(screenshot)).crop(
        tuple(dpi * x for x in [left, top, right, bottom])
    )
    pil_img.save(
        screenshot_bytes,
        format=format,
        dpi=(300, 300),
    )

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
