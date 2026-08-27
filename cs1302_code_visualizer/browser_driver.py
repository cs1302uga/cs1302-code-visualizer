"""Browser automation and screenshot rendering driver."""

import argparse
import fileinput
import json
import logging
import os
import shutil
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from importlib import metadata
from io import BytesIO
from pathlib import Path
from pprint import pformat
from tempfile import NamedTemporaryFile
from textwrap import dedent, indent
from typing import Any, TypedDict
from urllib.parse import urlencode

from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

logger: logging.Logger = logging.getLogger(__name__)

this_files_dir = Path(os.path.realpath(os.path.dirname(__file__)))

# Enable DEBUG_MODE with
# CS1302_DEBUG=1
# CS1302_DEBUG=True
DEBUG_MODE: bool = os.getenv("CS1302_DEBUG", "").strip().lower() in ["1", "true"]


def is_headless_enabled() -> bool:
    """Return True if headless mode is active (the default), False if explicitly disabled."""
    if os.getenv("CS1302_DISABLE_HEADLESS", "").strip().lower() in ["1", "true"]:
        return False
    if os.getenv("CS1302_HEADLESS", "").strip().lower() in ["0", "false"]:
        return False
    return True


DISABLE_HEADLESS_MODE: bool = not is_headless_enabled()

if DEBUG_MODE:
    # our logger
    logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    # selenium loggers
    logging.getLogger("selenium").setLevel(logging.DEBUG)
    logging.getLogger("selenium.webdriver.remote").setLevel(logging.DEBUG)
    logging.getLogger("selenium.webdriver.common").setLevel(logging.DEBUG)


logger.debug(f"{DEBUG_MODE=}")
logger.debug(f"{DISABLE_HEADLESS_MODE=}")

for package in ["cs1302_code_visualizer", "selenium"]:
    version = metadata.version(package)
    logger.debug(f"{package}: {version}")


def new_webdriver_options(dpi: int = 1) -> Options:
    """Create Chrome options configured for headless rendering and DPI scaling."""
    options: Options = Options()

    if DEBUG_MODE:
        options.add_experimental_option("detach", True)

    if is_headless_enabled():
        options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        options.add_argument("--screen-info={1920x1080}")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")

    options.add_argument(f"--force-device-scale-factor={dpi}")
    options.add_argument("--allow-file-access-from-files")
    options.add_argument("--no-sandbox")
    options.add_argument("--hide-scrollbars")

    return options


def new_webdriver(dpi: int = 1) -> webdriver.Chrome:
    """Get a new instance of a webdriver to use for the frontend.

    Args:
        dpi: Dots Per Inch (DPI), a positive integer used to scale the driver's display resolution.

    Return:
        The webdriver used to display the frontend.
    """
    logger.debug(f"creating new webdriver instance for {dpi=}")

    options: Options = new_webdriver_options(dpi)
    service: Service = Service()

    if executable_path := shutil.which("chromedriver"):
        service = Service(executable_path=executable_path)

    driver: webdriver.Chrome = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(4)
    return driver


def get_webdriver(dpi: int = 1) -> webdriver.Chrome:
    """Get the webdriver used to display the frontend.

    Args:
        dpi: Dots Per Inch (DPI), a positive integer used to scale the driver's display resolution.

    Return:
        The webdriver used to display the frontend.
    """
    return new_webdriver(dpi)


def tidy_set_window_size_for_element(driver: webdriver.Remote, element: WebElement) -> None:
    """Set the driver's window size for the target element."""
    driver.set_window_size(
        int(element.location["x"] + element.size["width"]),
        int(element.location["y"] + element.size["height"]),
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

    new_width = int(
        max(
            element.location["x"] + element.size["width"],
            element.location["x"] + element.size["width"] + offset_size["width"],
        )
    )

    new_height = int(
        max(
            element.location["y"] + element.size["height"],
            element.location["y"] + element.size["height"] + offset_size["height"],
        )
    )

    driver.set_window_size(new_width, new_height)


class OnlinePythonTutor(TypedDict):
    """Dictionary container holding frontend web driver and element handles."""

    driver: webdriver.Chrome
    vizDiv: WebElement
    dataViz: WebElement
    traceFile: Any
    wait: WebDriverWait[webdriver.Chrome]


@contextmanager
def online_python_tutor_frontend(
    trace: str,
    *,
    dpi: int = 1,
    include_types: bool = True,
    text_memory_labels: bool = True,
    strip_type_prefixes: Sequence[str] | None = None,
):
    """Context manager for interacting with the OnlinePythonTutor frontend in Chrome."""
    prefixes = list(strip_type_prefixes) if strip_type_prefixes is not None else []
    frontend_path = (this_files_dir / "frontend" / "render-trace.html").as_uri()
    driver = get_webdriver(dpi=dpi)
    try:
        trace_file = NamedTemporaryFile()
        try:
            wait: WebDriverWait[webdriver.Chrome] = WebDriverWait(driver, 10)
            logger.debug(f"webdriver: {pformat(driver.capabilities)}")

            with open(trace_file.name, "w", encoding="utf-8") as f:
                print(trace, file=f)

            frontend_query: dict[str, str] = {
                "tracePath": trace_file.name,
                "includeTypes": str(include_types).lower(),
                "textMemoryLabels": str(text_memory_labels).lower(),
                "stripTypePrefixes": json.dumps(prefixes),
            }

            frontend_uri: str = frontend_path + "?" + urlencode(frontend_query)

            driver.get(frontend_uri)

            vizDiv = driver.find_element(By.ID, "visualizerDiv")
            dataViz = driver.find_element(By.ID, "dataViz")

            _ = driver.find_element(By.ID, "screenshotReadyIndicator")

            frontend: OnlinePythonTutor = {
                "driver": driver,
                "vizDiv": vizDiv,
                "dataViz": dataViz,
                "traceFile": trace_file,
                "wait": wait,
            }

            yield frontend
        finally:
            trace_file.close()
    finally:
        driver.quit()


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
        dataViz: str | None = frontend["dataViz"].get_attribute("outerHTML")
        if dataViz:
            return dedent(
                f"""
            <div id="vizDiv">
                <div class="ExecutionVisualizer">
                    <div class="visualizer">
                        <div class="vizLayoutTd" id="vizLayoutTdSecond">
                            {indent(dataViz, " " * 4 * 5)}
                        </div>
                    </div>
                </div>
            </div>
            """
            )
        else:
            raise Exception("unable to generate an HTML visualization for this trace")


def generate_image(
    trace: str,
    *,
    dpi: int = 1,
    format: str = "PNG",
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    breakpoint: int | None = -1,
) -> bytes:
    """Generate an image of the final state of an execution trace file.

    The trace file is expected to be formatted using JSON as specified by OnlinePythonTutor.

    Args:
        trace: The execution trace file.
        dpi: Dots Per Inch (DPI), a positive integer used to scale the driver's display resolution.
        format: The image output format. This gets passed directly into PIL's ``Image.save()``.
        include_types: Whether or not type tags should be included in this visualization.
        text_memory_labels: Whether or not memory connections should be rendered as text instead of arrows.
        strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.
        breakpoint: Breakpoint line to visualize.

    Return:
        The bytes of the generated image in the format specified by the ``format`` argument.

    """
    trace_json: Any = json.loads(trace)
    if isinstance(trace_json, dict):
        if "trace" not in trace_json:
            if breakpoint is not None:
                if isinstance(breakpoint, tuple) and len(breakpoint) == 2:
                    bp_line, bp_idx = str(breakpoint[0]), breakpoint[1] - 1
                    if bp_line in trace_json:
                        val = trace_json[bp_line]
                        if isinstance(val, list):
                            trace_json = val[bp_idx] if 0 <= bp_idx < len(val) else val[-1]
                        else:
                            trace_json = val
                elif str(breakpoint) in trace_json:
                    trace_json = trace_json.get(str(breakpoint))
            elif "-1" in trace_json:
                trace_json = trace_json.get("-1")
            elif len(trace_json) == 1:
                trace_json = next(iter(trace_json.values()))

    # If trace_json is a list of traces (e.g. from --accumulate-breakpoints), take the last trace or specified hit
    if isinstance(trace_json, list) and len(trace_json) > 0:
        if isinstance(breakpoint, tuple) and len(breakpoint) == 2:
            bp_idx = breakpoint[1] - 1
            trace_json = trace_json[bp_idx] if 0 <= bp_idx < len(trace_json) else trace_json[-1]
        else:
            trace_json = trace_json[-1]

    trace = json.dumps(trace_json)

    with online_python_tutor_frontend(
        trace=trace,
        dpi=dpi,
        include_types=include_types,
        text_memory_labels=text_memory_labels,
        strip_type_prefixes=strip_type_prefixes,
    ) as frontend:
        driver: webdriver.Chrome = frontend["driver"]
        viz: WebElement = frontend["dataViz"]

        tidy_set_window_size_for_element(driver, viz)

        (left, top, right, bottom) = (
            int(viz.location["x"]),
            int(viz.location["y"]),
            int(viz.location["x"] + viz.size["width"]),
            int(viz.location["y"] + viz.size["height"]),
        )

        _ = driver.execute_script("window.optFrontend.redrawConnectors()")

        screenshot = driver.get_screenshot_as_png()

        # crop the screenshot down to the element borders
        screenshot_bytes = BytesIO()
        pil_img = Image.open(BytesIO(screenshot))

        crop_box: tuple[float, float, float, float] = (
            float(dpi * left),
            float(dpi * top),
            float(dpi * right),
            float(dpi * bottom),
        )
        pil_img = pil_img.crop(crop_box)

        pil_img.save(
            screenshot_bytes,
            format=format,
        )

        return screenshot_bytes.getvalue()


def main() -> None:
    """Command-line entry point for generating screenshot from Java execution trace."""
    parser = argparse.ArgumentParser(
        description="Generate a screenshot from a Java execution trace"
    )

    def require_geq_one(value: str | float) -> float:
        number = float(value)
        if number < 1:
            raise argparse.ArgumentTypeError(f"Number {value} must be >= 1.")
        return number

    _ = parser.add_argument(
        "--dpi",
        help="DPI scale to apply to the screenshot.",
        type=require_geq_one,
        default=1,
    )

    args = parser.parse_args()

    stdin_data = "".join(fileinput.input("-"))

    image_bytes = generate_image(stdin_data, dpi=args.dpi)

    # dump png to stdout, should be redirected to destination
    _ = sys.stdout.buffer.write(image_bytes)


if __name__ == "__main__":
    main()
