#!/usr/bin/env python3

import os
import sys
import fileinput
import argparse
import logging

from textwrap import dedent, indent
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from io import BytesIO
from PIL import Image
from urllib.parse import urlencode
from tempfile import _TemporaryFileWrapper, NamedTemporaryFile, TemporaryFile


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
    options.add_argument("--headless=new")
    options.add_argument(f"--force-device-scale-factor={dpi}")
    options.add_argument("--allow-file-access-from-files")
    options.add_argument("--no-sandbox")
    options.add_argument("start-maximized")
    options.add_argument("--hide-scrollbars")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(4)
    return driver


def tidy_set_window_size_for_element(driver: webdriver.Chrome, element: WebElement) -> None:
    """Set the driver's window size for the target element."""
    driver.set_window_size(
        element.location["x"] + element.size["width"],
        element.location["y"] + element.size["height"],
    )
    window_size: dict[str, int] = driver.get_window_size()
    client_size: dict[str, int] = {
        "width": driver.execute_script("return document.documentElement.clientWidth;"),
        "height": driver.execute_script("return document.documentElement.clientHeight;"),
    }
    offset_size: dict[str, int] = {
        "width": window_size["width"] - client_size["width"],
        "height": window_size["height"] - client_size["height"],
    }
    from pprint import pformat

    print("window_size", pformat(window_size), file=sys.stderr)
    print("client_size", pformat(client_size), file=sys.stderr)
    print("offset_size", pformat(offset_size), file=sys.stderr)

    new_width = max(
        element.location["x"] + element.size["width"],
        element.location["x"] + element.size["width"] + offset_size["width"],
    )

    new_height = max(
        element.location["y"] + element.size["height"],
        element.location["y"] + element.size["height"] + offset_size["height"]
    ) + 20

    print(f"{element.location['x']=}", f"{element.location['y']=}", file=sys.stderr)
    print(f"{new_width=}", f"{new_height=}", file=sys.stderr)

    driver.set_window_size(new_width, new_height)

def tidy_set_font(driver: webdriver.Chrome) -> None:
    """Set the font used by the data visualization."""
    driver.execute_script(
        """
        document.head.insertAdjacentHTML(
            'beforeend',
            `
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Recursive:wght,CRSV,MONO@300..1000,0,1&display=swap" rel="stylesheet">
            `
        );
        document.head.insertAdjacentHTML(
            'beforeend',
            `
            <style>
                #vizDiv, #vizDiv * {
                    font-family: "Recursive", monospace;
                    font-variation-settings: "MONO" 1;
                    font-optical-sizing: auto;
                    font-smooth: auto;
                    -webkit-font-smoothing: auto;
                }
                #vizDiv .typeLabel {
                    width: max-content;
                }
            </style>
            `
        );
        document.querySelector("#vizDiv").style.fontFamily = "Recursive";
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

class OnlinePythonTutor(TypedDict):
    driver: webdriver.Chrome
    vizDiv: WebElement
    dataViz: WebElement
    traceFile: _TemporaryFileWrapper

@contextmanager
def online_python_tutor_frontend(trace: str, *, dpi: int = 1):
    """TODO."""
    frontend_path = (this_files_dir / "frontend" / "iframe-embed.html").as_uri()
    driver = get_webdriver(dpi)
    trace_file = NamedTemporaryFile()

    with open(trace_file.name, "w") as f:
        print(trace, file=f)

    frontend_query: dict = {
        "tracePath": trace_file.name,
    }

    frontend_uri: str = frontend_path + "?" + urlencode(frontend_query)

    # from pprint import pformat
    # print(f"{trace=}", file=sys.stderr)
    # print(f"frontend_query={pformat(frontend_query)}", file=sys.stderr)
    # print(f"{frontend_uri=}", file=sys.stderr)

    driver.get(frontend_uri)
    tidy_set_font(driver)

    vizDiv = driver.find_element(By.ID, "vizDiv")
    dataViz = driver.find_element(By.ID, "dataViz")

    driver.execute_script(
        """
        // remove displayed code
        document.querySelector("#vizDiv .visualizer .vizLayoutTd").remove();
        """
    )

    tidy_set_window_size_for_element(driver, dataViz);
    tidy_string_objects(driver)

    #print(f"#dataViz.innerHTML={dataViz.get_attribute('innerHTML')}", file=sys.stderr)

    frontend: OnlinePythonTutor = OnlinePythonTutor(
        driver=driver,
        vizDiv=vizDiv,
        dataViz=dataViz,
    )

    try:
        yield frontend
    finally:
        driver.quit()
        trace_file.close()

def generate_html(trace: str, *, dpi: int = 1, include_style: bool = False) -> str:
    """Generate HTML depicting the final state of an execution trace file.

    The trace file is expected to be formatted using JSON as specified by OnlinePythonTutor.

    Args:
        trace: The execution trace file.
        dpi: Dots Per Inch (DPI), a positive integer used to scale the driver's display resolution.
        include_style: If True, prefix the output with a style tag that contains some default CSS.

    Return:
        The bytes of the generated image in the format specified by the ``format`` argument.

    """
    # TODO: implement include_style
    with online_python_tutor_frontend(trace, dpi=dpi) as frontend:
        dataViz: str | None = frontend["dataViz"].get_attribute('outerHTML')
        if dataViz:
            return dedent(f"""
            <div id="vizDiv">
                <div class="ExecutionVisualizer">
                    <div class="visualizer">
                        <div class="vizLayoutTd" id="vizLayoutTdSecond">
                            {indent(dataViz," " * 4 * 5)}
                        </div>
                    </div>
                </div>
            </div>
            """)
        else:
            raise Exception("unable to generate an HTML visualization for this trace")

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

    # print(f"#dataViz.outerHTML={generate_html(trace, dpi=dpi)}", file=sys.stderr)

    with online_python_tutor_frontend(trace, dpi=dpi) as frontend:

        driver: webdriver.Chrome = frontend["driver"]
        viz: WebElement = frontend["dataViz"]

        (left, top, right, bottom) = (
            viz.location["x"],
            viz.location["y"],
            viz.location["x"] + viz.size["width"],
            viz.location["y"] + viz.size["height"],
        )

        screenshot = driver.get_screenshot_as_png()

        # crop the screenshot down to the element borders
        screenshot_bytes = BytesIO(screenshot)
        pil_img = Image.open(BytesIO(screenshot)).crop(
            tuple(dpi * x for x in [left, top, right, bottom])
        )
        pil_img.save(
            screenshot_bytes,
            format=format,
            dpi=(dpi * 100, dpi * 100),
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
