"""Browser automation and screenshot rendering driver.

Normative References:
    W3C WebDriver Specification (W3C Recommendation, https://www.w3.org/TR/webdriver2/)
    Scalable Vector Graphics (SVG) 2 (W3C Recommendation, https://www.w3.org/TR/SVG2/)
    HTML Living Standard (WHATWG, https://html.spec.whatwg.org/)
    PEP 257 – Docstring Conventions (https://peps.python.org/pep-0257/)
    PEP 484 – Type Hints (https://peps.python.org/pep-0484/)
"""

from __future__ import annotations

import argparse
import base64
import fileinput
import json
import logging
import os
import shutil
import sys
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager, nullcontext
from importlib import metadata
from io import BytesIO
from pathlib import Path
from pprint import pformat
from tempfile import NamedTemporaryFile
from textwrap import dedent, indent
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from .session import RenderingSession
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from weakref import WeakKeyDictionary

from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .array_options import (
    ArrayOrientation,
    add_array_arguments,
    array_options_from_args,
    validate_array_options,
)
from .errors import CodeVisRenderError
from .theme_options import Theme, add_theme_argument, theme_options
from .util.certificates import ensure_certifi_bundle

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
    return os.getenv("CS1302_HEADLESS", "").strip().lower() not in ["0", "false"]


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

    # Configure trust before Selenium Manager or ChromeDriver starts. Refresh a
    # stale override on every launch using this environment's installed bundle.
    ensure_certifi_bundle()

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


class OnlinePythonTutor(TypedDict):
    """Dictionary container holding frontend web driver and element handles."""

    driver: webdriver.Chrome
    vizDiv: WebElement
    dataViz: WebElement
    traceFile: Any
    wait: WebDriverWait[webdriver.Chrome]


_minimum_window_sizes: WeakKeyDictionary[webdriver.Chrome, dict[str, int]] = WeakKeyDictionary()


def _prepare_session_viewport(driver: webdriver.Chrome) -> None:
    """Reset emulation and measure this browser's minimum window size once."""
    driver.execute_cdp_cmd("Emulation.clearDeviceMetricsOverride", {})
    if driver not in _minimum_window_sizes:
        initial = driver.get_window_size()
        driver.set_window_size(1, 1)
        _minimum_window_sizes[driver] = driver.get_window_size()
        driver.set_window_size(initial["width"], initial["height"])


def _fit_session_viewport(driver: webdriver.Chrome, element: WebElement, dpi: int) -> None:
    """Reproduce native window fitting using a virtual viewport for fast capture.

    Native resizing can stall Chrome's direct screenshot path. Emulation applies
    the same two layout passes, browser chrome offsets, and minimum dimensions
    without changing the native capture surface.
    """
    window = driver.get_window_size()
    client = driver.execute_script(
        "return [document.documentElement.clientWidth, document.documentElement.clientHeight]"
    )
    offset = {"width": window["width"] - client[0], "height": window["height"] - client[1]}
    minimum = _minimum_window_sizes[driver]

    def resize(width: int, height: int) -> None:
        driver.execute_cdp_cmd(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": max(1, max(minimum["width"], width) - offset["width"]),
                "height": max(1, max(minimum["height"], height) - offset["height"]),
                "deviceScaleFactor": dpi,
                "mobile": False,
            },
        )

    rect = element.rect
    resize(int(rect["x"] + rect["width"]), int(rect["y"] + rect["height"]))
    rect = element.rect
    resize(
        int(rect["x"] + rect["width"] + offset["width"]),
        int(rect["y"] + rect["height"] + offset["height"]),
    )


@contextmanager
def _browser_scope(dpi: int, session: RenderingSession | None):
    """Lease a session browser or own a standalone browser for this request."""
    if session is not None:
        with session.browser(
            dpi, get_webdriver, configuration=(is_headless_enabled(), DEBUG_MODE)
        ) as driver:
            yield driver
    else:
        driver = get_webdriver(dpi=dpi)
        try:
            yield driver
        finally:
            driver.quit()


def _wait_for_screenshot_ready(driver: webdriver.Chrome) -> WebElement:
    """Wait for the frontend's existing readiness signal without polling.

    Args:
        driver: Browser currently displaying the frontend document.

    Returns:
        The readiness indicator inserted by the frontend.

    Raises:
        NoSuchElementException: If the indicator is absent after four seconds.
    """
    result: object = driver.execute_async_script(
        """
        const done = arguments[arguments.length - 1];
        const existing = document.getElementById('screenshotReadyIndicator');
        if (existing) { done(existing); return; }
        let finished = false;
        const observer = new MutationObserver(() => {
            const element = document.getElementById('screenshotReadyIndicator');
            if (element) finish(element);
        });
        const timer = setTimeout(() => finish(null), 4000);
        function finish(element) {
            if (finished) return;
            finished = true;
            observer.disconnect();
            clearTimeout(timer);
            done(element);
        }
        observer.observe(document, {childList: true, subtree: true});
        """
    )
    if not isinstance(result, WebElement):
        raise NoSuchElementException("screenshotReadyIndicator was not found within four seconds")
    return result


@contextmanager
def online_python_tutor_frontend(
    trace: str,
    *,
    dpi: int = 1,
    include_types: bool = True,
    text_memory_labels: bool = True,
    strip_type_prefixes: Sequence[str] | None = None,
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    visualizer: str = "pytutor",
    session: RenderingSession | None = None,
):
    """Context manager for interacting with the OnlinePythonTutor frontend in Chrome."""
    theme_options(theme)
    validate_array_options(array_orientation, alternate_array_orientations, array_orientations)
    prefixes = list(strip_type_prefixes) if strip_type_prefixes is not None else []
    frontend_path = (this_files_dir / "frontend" / "render-trace.html").as_uri()
    with (
        _browser_scope(dpi, session) as driver,
        NamedTemporaryFile(mode="w", encoding="utf-8") as trace_file,
    ):
        if session is not None:
            _prepare_session_viewport(driver)
        wait: WebDriverWait[webdriver.Chrome] = WebDriverWait(driver, 10)
        logger.debug(f"webdriver: {pformat(driver.capabilities)}")

        trace_file.write(trace)
        trace_file.flush()

        frontend_query: dict[str, str] = {
            "tracePath": trace_file.name,
            "includeTypes": str(include_types).lower(),
            "textMemoryLabels": str(text_memory_labels).lower(),
            "stripTypePrefixes": json.dumps(prefixes),
            "visualizer": visualizer,
            "arrayOrientation": array_orientation,
            "alternateArrayOrientations": str(alternate_array_orientations).lower(),
            "arrayOrientations": json.dumps(array_orientations or {}),
        }

        if theme is not None:
            frontend_query["theme"] = theme

        frontend_uri: str = frontend_path + "?" + urlencode(frontend_query)

        driver.get(frontend_uri)

        _ = _wait_for_screenshot_ready(driver)
        vizDiv = driver.find_element(By.ID, "visualizerDiv")
        if visualizer == "json-pre":
            try:
                dataViz = vizDiv.find_element(By.CSS_SELECTOR, "pre")
            except NoSuchElementException:
                dataViz = vizDiv
        else:
            dataViz = driver.find_element(By.ID, "dataViz")

        frontend: OnlinePythonTutor = {
            "driver": driver,
            "vizDiv": vizDiv,
            "dataViz": dataViz,
            "traceFile": trace_file,
            "wait": wait,
        }

        yield frontend


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
            raise CodeVisRenderError("unable to generate an HTML visualization for this trace")


def get_default_bundle_url() -> str:
    """Return the default GitHub release asset URL for vis-module.bundle.js."""
    try:
        ver = metadata.version("cs1302_code_visualizer")
    except metadata.PackageNotFoundError:
        ver = "0.7.1"
    return f"https://github.com/cs1302uga/cs1302-code-visualizer/releases/download/v{ver}/vis-module.bundle.js"


def resolve_trace_payload(
    trace: str | dict[str, Any] | list[Any],
    breakpoint: int | tuple[int, int] | None = None,
) -> Any:
    """Resolve a target execution trace from raw or breakpoint-keyed trace data."""
    trace_json: Any = json.loads(trace) if isinstance(trace, str) else trace
    if isinstance(trace_json, dict):
        if "breakpoints" in trace_json and isinstance(trace_json["breakpoints"], dict):
            bps = trace_json["breakpoints"]
            if breakpoint is not None:
                if isinstance(breakpoint, tuple) and len(breakpoint) == 2:
                    bp_line, bp_idx = str(breakpoint[0]), breakpoint[1] - 1
                    if bp_line in bps:
                        val = bps[bp_line]
                        trace_json["breakpoints"] = {
                            bp_line: (
                                val[bp_idx]
                                if isinstance(val, list) and 0 <= bp_idx < len(val)
                                else val
                            )
                        }
                elif str(breakpoint) in bps:
                    trace_json["breakpoints"] = {str(breakpoint): bps[str(breakpoint)]}
                elif len(bps) == 1:
                    k, v = next(iter(bps.items()))
                    trace_json["breakpoints"] = {k: v}
            elif "-1" in bps:
                trace_json["breakpoints"] = {"-1": bps["-1"]}
            elif len(bps) == 1:
                k, v = next(iter(bps.items()))
                trace_json["breakpoints"] = {k: v}
        elif (
            "trace" not in trace_json
            and "steps" not in trace_json
            and trace_json.get("format") != "modern"
        ):
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
                elif len(trace_json) == 1:
                    trace_json = next(iter(trace_json.values()))
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

    return trace_json


def render_html(
    trace: str | dict[str, Any] | list[Any],
    *,
    container_id: str | None = None,
    bundle_url: str | None = None,
    include_bundle_script: bool = True,
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    hide_fields: Sequence[str] | None = None,
    hide_vars: Sequence[str] | None = None,
    visualizer: str = "pytutor",
    lang: str = "java",
    breakpoint: int | tuple[int, int] | None = None,
) -> str:
    """Generate an HTML snippet with a script tag to embed an interactive execution trace visualization.

    Args:
        trace: The execution trace, either as a JSON string or parsed dictionary/list.
        container_id: Optional ID for the container element. If None, a unique ID is generated.
        bundle_url: URL for the CodeVisualizer frontend bundle. If None, defaults to the GitHub release asset URL.
        include_bundle_script: Whether to include the external <script src="..."> tag for the bundle.
        include_types: Whether type labels should be included in the visualization.
        text_memory_labels: Whether memory connections should be rendered as text instead of arrows.
        strip_type_prefixes: List of package prefixes to strip from displayed types.
        theme: Light, dark, auto, or None for the default host-inherited theme.
        array_orientation: Base array orientation, or the 1D orientation when alternating.
        alternate_array_orientations: Flip orientation for each additional dimension.
        array_orientations: Per-heap-object orientation overrides, taking precedence over the base.
        hide_fields: List of field names (e.g. ClassName:fieldName) to hide.
        hide_vars: List of variable names to hide.
        visualizer: Visualizer mode ('pytutor' or 'json-pre').
        lang: Language mode ('java').
        breakpoint: Optional breakpoint to resolve from multi-trace payload.

    Returns:
        HTML snippet containing the container <div>, optional bundle <script> tag, and inline initialization <script>.
    """
    theme_options(theme)
    validate_array_options(array_orientation, alternate_array_orientations, array_orientations)
    trace_data = resolve_trace_payload(trace, breakpoint=breakpoint)

    if container_id is None:
        container_id = f"codevis-{uuid.uuid4().hex[:8]}"

    if bundle_url is None:
        bundle_url = get_default_bundle_url()

    # Safely escape '</' in JSON string to prevent premature </script> closing in HTML parsers
    safe_json_trace = json.dumps(trace_data).replace("</", r"<\/")

    options_dict: dict[str, Any] = {
        **theme_options(theme),
        "includeTypes": include_types,
        "textualMemoryLabels": text_memory_labels,
        "stripTypePrefixes": list(strip_type_prefixes) if strip_type_prefixes is not None else [],
        "visualizer": visualizer,
        "hideFields": list(hide_fields) if hide_fields is not None else [],
        "hideVars": list(hide_vars) if hide_vars is not None else [],
        "arrayOrientation": array_orientation,
        "alternateArrayOrientations": alternate_array_orientations,
        "arrayOrientations": array_orientations or {},
    }
    options_json = json.dumps(options_dict).replace("</", r"<\/")

    bundle_tag = f'<script src="{bundle_url}"></script>\n' if include_bundle_script else ""

    return (
        f'<div id="{container_id}"></div>\n'
        f"{bundle_tag}"
        f"<script>\n"
        f"  (function() {{\n"
        f"    function init() {{\n"
        f'      var target = document.getElementById("{container_id}");\n'
        f'      if (typeof CodeVisualizer !== "undefined" && CodeVisualizer.create && target) {{\n'
        f"        CodeVisualizer.create({{\n"
        f'          lang: "{lang}",\n'
        f"          trace: {safe_json_trace},\n"
        f"          element: target,\n"
        f"          options: {options_json}\n"
        f"        }});\n"
        f"      }}\n"
        f"    }}\n"
        f'    if (document.readyState === "loading") {{\n'
        f'      document.addEventListener("DOMContentLoaded", init);\n'
        f"    }} else {{\n"
        f"      init();\n"
        f"    }}\n"
        f"  }})();\n"
        f"</script>"
    )


def generate_image(
    trace: str,
    *,
    dpi: int = 1,
    format: str = "PNG",
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    breakpoint: int | tuple[int, int] | None = -1,
    visualizer: str = "pytutor",
    session: RenderingSession | None = None,
) -> bytes:
    """Generate an image of the final state of an execution trace file.

    The trace file is expected to be formatted using JSON as specified by OnlinePythonTutor.

    Args:
        trace: The execution trace file.
        dpi: Positive integer output scale; diagram layout stays in CSS pixels.
        format: SVG for standalone vector output; raster formats use PIL's ``Image.save()``.
        include_types: Whether or not type tags should be included in this visualization.
        text_memory_labels: Whether or not memory connections should be rendered as text instead of arrows.
        strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.
        theme: Light, dark, auto, or None for the default host-inherited theme.
        array_orientation: Base array orientation, or the 1D orientation when alternating.
        alternate_array_orientations: Flip orientation for each additional dimension.
        array_orientations: Per-heap-object orientation overrides, taking precedence over the base.
        breakpoint: Breakpoint line to visualize.
        session: Optional build-scoped browser owner.
        visualizer: The visualizer implementation to use ('pytutor' or 'json-pre').

    Return:
        The bytes of the generated image in the format specified by the ``format`` argument.

    """
    trace_json = resolve_trace_payload(trace, breakpoint=breakpoint)
    trace = json.dumps(trace_json)

    # Lay out every format at 1x; scale raster capture instead of changing font
    # metrics through the browser's device scale factor.
    with online_python_tutor_frontend(
        trace=trace,
        dpi=1,
        include_types=include_types,
        text_memory_labels=text_memory_labels,
        strip_type_prefixes=strip_type_prefixes,
        array_orientation=array_orientation,
        alternate_array_orientations=alternate_array_orientations,
        array_orientations=array_orientations,
        visualizer=visualizer,
        **{**theme_options(theme), **({"session": session} if session is not None else {})},
    ) as frontend:
        driver: webdriver.Chrome = frontend["driver"]
        viz: WebElement = frontend["dataViz"]

        return _capture_viz(
            driver,
            viz,
            dpi=dpi,
            format=format,
            visualizer=visualizer,
            session=session,
        )


def _fit_capture_viewport(
    driver: webdriver.Chrome, viz: WebElement, session: RenderingSession | None
) -> None:
    """Fit once before export; sequences retain this viewport for every step."""
    driver.execute_async_script(
        "const done = arguments[arguments.length - 1]; document.fonts.ready.then(() => done());"
    )
    if session is None:
        _prepare_session_viewport(driver)
    # Use virtual fitting in both ownership modes: native resizing can stall
    # Chrome's direct screenshot capture. Output scale is applied at capture time.
    _fit_session_viewport(driver, viz, 1)


def _export_bounds(driver: webdriver.Chrome, viz: WebElement) -> dict[str, int]:
    """Wait for layout and connectors, then measure padded document coordinates."""
    result = driver.execute_async_script(
        "const [root, done] = arguments;"
        "window.prepareVisualizationExport(root).then("
        "bounds => done({bounds}), error => done({error: String(error)}));",
        viz,
    )
    if "error" in result:
        raise ValueError(f"Export bounds failed: {result['error']}")
    return result["bounds"]


def _capture_viz(
    driver: webdriver.Chrome,
    viz: WebElement,
    *,
    dpi: int,
    format: str,
    visualizer: str,
    session: RenderingSession | None,
    bounds: dict[str, int] | None = None,
) -> bytes:
    if bounds is None:
        _fit_capture_viewport(driver, viz, session)
        bounds = _export_bounds(driver, viz)
    else:
        current = _export_bounds(driver, viz)
        if any(current[edge] < bounds[edge] for edge in ("left", "top")) or any(
            current[edge] > bounds[edge] for edge in ("right", "bottom")
        ):
            raise ValueError("Visualization layout changed after measuring sequence bounds")

    if format.upper() == "SVG":
        result = driver.execute_async_script(
            "const [root, scale, bounds, done] = arguments;"
            "window.exportVisualizationSvg(root, scale, bounds).then("
            "svg => done({svg}), error => done({error: String(error)}));",
            viz,
            dpi,
            bounds,
        )
        if "error" in result:
            raise ValueError(f"SVG export failed: {result['error']}")
        return result["svg"].encode("utf-8")

    # Both browser ownership modes capture beyond the viewport. Native screenshots
    # truncate overflowing steps and cannot guarantee a shared sequence canvas.
    left, top = max(0, bounds["left"]), max(0, bounds["top"])
    result = driver.execute_cdp_cmd(
        "Page.captureScreenshot",
        {
            "format": "png",
            "captureBeyondViewport": True,
            "clip": {
                "x": left,
                "y": top,
                "width": bounds["right"] - left,
                "height": bounds["bottom"] - top,
                "scale": dpi,
            },
        },
    )
    captured = Image.open(BytesIO(base64.b64decode(result["data"])))
    if left != bounds["left"] or top != bounds["top"]:
        # Padding may extend beyond the document origin; fill it with the canvas
        # color rather than asking Chrome for negative screenshot coordinates.
        background = driver.execute_script("return getComputedStyle(document.body).backgroundColor")
        padded = Image.new(
            "RGB",
            ((bounds["right"] - bounds["left"]) * dpi, (bounds["bottom"] - bounds["top"]) * dpi),
            background,
        )
        padded.paste(captured, ((left - bounds["left"]) * dpi, (top - bounds["top"]) * dpi))
        captured = padded
    output = BytesIO()
    captured.save(output, format=format)
    return output.getvalue()


def generate_step_images(
    trace: str,
    *,
    dpi: int = 1,
    format: str = "PNG",
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    breakpoint: int | tuple[int, int] | None = None,
    visualizer: str = "pytutor",
    session: RenderingSession | None = None,
) -> list[bytes]:
    """Generate images for every step of an execution trace file.

    Args:
        trace: The execution trace file.
        dpi: Positive integer output scale; diagram layout stays in CSS pixels.
        format: SVG for standalone vector output; raster formats use PIL's ``Image.save()``.
        include_types: Whether or not type tags should be included in this visualization.
        text_memory_labels: Whether or not memory connections should be rendered as text instead of arrows.
        strip_type_prefixes: A list of prefix strings to strip from the beginning of type labels.
        theme: Light, dark, auto, or None for the default host-inherited theme.
        array_orientation: Base array orientation, or the 1D orientation when alternating.
        alternate_array_orientations: Flip orientation for each additional dimension.
        array_orientations: Per-heap-object orientation overrides, taking precedence over the base.
        breakpoint: Breakpoint line to visualize.
        visualizer: The visualizer implementation to use ('pytutor' or 'json-pre').
        session: Optional build-scoped browser owner.

    Returns:
        List of raw image bytes, one for each execution step in chronological order.
    """
    trace_json = resolve_trace_payload(trace, breakpoint=breakpoint)
    num_steps = 1
    if (
        isinstance(trace_json, dict)
        and "trace" in trace_json
        and isinstance(trace_json["trace"], list)
    ):
        num_steps = len(trace_json["trace"])

    if num_steps <= 1 or visualizer == "json-pre":
        return [
            generate_image(
                trace,
                dpi=dpi,
                format=format,
                include_types=include_types,
                text_memory_labels=text_memory_labels,
                strip_type_prefixes=strip_type_prefixes,
                **theme_options(theme),
                array_orientation=array_orientation,
                alternate_array_orientations=alternate_array_orientations,
                array_orientations=array_orientations,
                breakpoint=breakpoint,
                visualizer=visualizer,
                session=session,
            )
        ]

    trace_str = json.dumps(trace_json)
    images: list[bytes] = []

    with online_python_tutor_frontend(
        trace=trace_str,
        dpi=1,
        include_types=include_types,
        text_memory_labels=text_memory_labels,
        strip_type_prefixes=strip_type_prefixes,
        array_orientation=array_orientation,
        alternate_array_orientations=alternate_array_orientations,
        array_orientations=array_orientations,
        visualizer=visualizer,
        **{**theme_options(theme), **({"session": session} if session is not None else {})},
    ) as frontend:
        driver = frontend["driver"]
        viz = frontend["dataViz"]

        _fit_capture_viewport(driver, viz, session)
        step_bounds = []
        for step in range(num_steps):
            driver.execute_script("window.optFrontend.renderStep(arguments[0]);", step)
            step_bounds.append(_export_bounds(driver, viz))
        bounds = {
            edge: combine(rect[edge] for rect in step_bounds)
            for edge, combine in (("left", min), ("top", min), ("right", max), ("bottom", max))
        }
        for step in range(num_steps):
            driver.execute_script("window.optFrontend.renderStep(arguments[0]);", step)
            img_bytes = _capture_viz(
                driver,
                viz,
                dpi=dpi,
                format=format,
                visualizer=visualizer,
                session=session,
                bounds=bounds,
            )
            images.append(img_bytes)

    return images


@contextmanager
def _snapshot_frame(
    driver: webdriver.Chrome, payload: str, frontend_uri: str
) -> Generator[WebElement]:
    """Load one independent document while retaining the surrounding browser host.

    A new document retains the original font-loading and heap-layout behavior.
    Replacing only the diagram would reuse loaded fonts during construction and
    change its heap spacing. The borderless frame occupies the full viewport, so
    element coordinates match a top-level document during virtual viewport fitting.
    """
    with NamedTemporaryFile(mode="w", encoding="utf-8") as trace_file:
        trace_file.write(payload)
        trace_file.flush()
        address = urlsplit(frontend_uri)
        parameters = dict(parse_qsl(address.query))
        parameters["tracePath"] = trace_file.name
        uri = urlunsplit(address._replace(query=urlencode(parameters)))
        frame = driver.execute_script(
            "document.getElementById('visualizerDiv').style.display = 'none';"
            "const frame = document.createElement('iframe');"
            "frame.style.cssText = 'position:fixed;left:0;top:0;width:100vw;height:100vh;border:0';"
            "frame.src = arguments[0]; document.body.appendChild(frame); return frame;",
            uri,
        )
        try:
            driver.switch_to.frame(frame)
            _ = _wait_for_screenshot_ready(driver)
            yield driver.find_element(By.ID, "dataViz")
        finally:
            driver.switch_to.default_content()
            driver.execute_script("arguments[0].remove();", frame)


def generate_snapshot_images(
    traces: Sequence[str],
    *,
    dpi: int = 1,
    format: str = "PNG",
    include_types: bool = True,
    text_memory_labels: bool = False,
    strip_type_prefixes: Sequence[str] | None = None,
    theme: Theme | None = None,
    array_orientation: ArrayOrientation = "horizontal",
    alternate_array_orientations: bool = False,
    array_orientations: dict[str, ArrayOrientation] | None = None,
    breakpoint: int | tuple[int, int] | None = -1,
    visualizer: str = "pytutor",
    session: RenderingSession | None = None,
) -> list[bytes]:
    """Render independent payloads in order while retaining one browser host.

    Each payload has its own source and trace history. Subsequent payloads load
    the unchanged frontend in a fresh full-viewport frame, preserving original
    font timing, heap spacing, and connector state. No partial list is returned
    on failure. The JSON text visualizer uses the existing individual-image path.

    Args:
        traces: Independent JSON payload strings, in requested output order.
        dpi: Positive output scale; diagram layout stays in CSS pixels.
        format: SVG or a raster format supported by Pillow.
        include_types: Whether to display type tags.
        text_memory_labels: Whether to replace reference arrows with labels.
        strip_type_prefixes: Prefixes removed from displayed type names.
        theme: Light, dark, auto, or None for the default adaptive theme.
        array_orientation: Base orientation of array objects.
        alternate_array_orientations: Whether successive dimensions alternate.
        array_orientations: Per-object orientation overrides.
        breakpoint: Breakpoint selection applied independently to each payload.
        visualizer: Visualizer implementation, either pytutor or json-pre.
        session: Optional build-scoped browser owner.

    Returns:
        One image per payload, or an empty list without opening a browser.

    """
    if not traces:
        return []
    payloads = [resolve_trace_payload(trace, breakpoint=breakpoint) for trace in traces]
    if len(traces) == 1 or visualizer == "json-pre":
        return [
            generate_image(
                trace,
                dpi=dpi,
                format=format,
                include_types=include_types,
                text_memory_labels=text_memory_labels,
                strip_type_prefixes=strip_type_prefixes,
                array_orientation=array_orientation,
                alternate_array_orientations=alternate_array_orientations,
                array_orientations=array_orientations,
                breakpoint=breakpoint,
                visualizer=visualizer,
                **theme_options(theme),
                session=session,
            )
            for trace in traces
        ]
    images: list[bytes] = []
    with online_python_tutor_frontend(
        trace=json.dumps(payloads[0]),
        dpi=1,
        include_types=include_types,
        text_memory_labels=text_memory_labels,
        strip_type_prefixes=strip_type_prefixes,
        array_orientation=array_orientation,
        alternate_array_orientations=alternate_array_orientations,
        array_orientations=array_orientations,
        visualizer=visualizer,
        **{**theme_options(theme), **({"session": session} if session is not None else {})},
    ) as frontend:
        driver = frontend["driver"]
        frontend_uri = driver.current_url
        for index, payload in enumerate(payloads):
            if index:
                # Each document starts with the same un-fitted viewport as an
                # individual request, including when no session was supplied.
                _prepare_session_viewport(driver)
            context = (
                _snapshot_frame(driver, json.dumps(payload), frontend_uri)
                if index
                else nullcontext(frontend["dataViz"])
            )
            with context as viz:
                images.append(
                    _capture_viz(
                        driver,
                        viz,
                        dpi=dpi,
                        format=format,
                        visualizer=visualizer,
                        session=session,
                    )
                )
    return images


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

    _ = parser.add_argument(
        "--visualizer",
        help="Visualizer implementation to use ('pytutor' or 'json-pre').",
        choices=["pytutor", "json-pre"],
        default="pytutor",
    )

    _ = parser.add_argument(
        "-b",
        "--breakpoint",
        dest="breakpoint",
        help="Breakpoint line to visualize (optional).",
        default=None,
    )

    _ = parser.add_argument(
        "-a",
        "--all-steps",
        action="store_true",
        help="Generate images for all execution steps in the trace.",
    )

    _ = parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Output image path (e.g. Driver.java.png). When --all-steps is set, numbered step files are also saved.",
        default=None,
    )

    _ = parser.add_argument(
        "--html",
        action="store_true",
        help="Generate an HTML embed snippet instead of rendering a screenshot.",
    )

    _ = parser.add_argument(
        "--container-id",
        help="Optional custom container ID for the HTML element.",
        default=None,
    )

    _ = parser.add_argument(
        "--bundle-url",
        help="Optional URL for the CodeVisualizer bundle JS.",
        default=None,
    )

    _ = parser.add_argument(
        "--no-bundle-script",
        action="store_true",
        help="Omit the external bundle script tag in the HTML snippet.",
    )

    add_theme_argument(parser)
    add_array_arguments(parser)
    args = parser.parse_args()
    array_options = {**array_options_from_args(args), **theme_options(args.theme)}

    bp: int | tuple[int, int] | None = -1
    if args.breakpoint is not None:
        if "," in args.breakpoint:
            parts = [int(p.strip()) for p in args.breakpoint.split(",") if p.strip()]
            if len(parts) == 2:
                bp = (parts[0], parts[1])
            elif len(parts) == 1:
                bp = parts[0]
        else:
            bp = int(args.breakpoint)

    with fileinput.input("-") as f:
        stdin_data = "".join(f)

    if args.html:
        html_snippet = render_html(
            stdin_data,
            container_id=args.container_id,
            bundle_url=args.bundle_url,
            include_bundle_script=not args.no_bundle_script,
            visualizer=args.visualizer,
            **array_options,
            breakpoint=bp,
        )
        sys.stdout.write(html_snippet + "\n")
        return

    if args.all_steps:
        step_images = generate_step_images(
            stdin_data,
            dpi=args.dpi,
            visualizer=args.visualizer,
            **array_options,
            breakpoint=bp,
        )
        if args.output:
            out_path = Path(args.output)
            out_dir = out_path.parent
            base_stem = out_path.stem if out_path.suffix == ".png" else out_path.name
            main_out = out_path if out_path.suffix == ".png" else (out_dir / f"{base_stem}.png")
            for i, step_bytes in enumerate(step_images):
                step_file = out_dir / f"{base_stem}.{i}.png"
                step_file.write_bytes(step_bytes)
            if step_images:
                main_out.write_bytes(step_images[-1])
        else:
            if step_images:
                _ = sys.stdout.buffer.write(step_images[-1])
        return

    image_bytes = generate_image(
        stdin_data,
        dpi=args.dpi,
        visualizer=args.visualizer,
        **array_options,
        breakpoint=bp,
    )

    if args.output:
        Path(args.output).write_bytes(image_bytes)
    else:
        # dump png to stdout, should be redirected to destination
        _ = sys.stdout.buffer.write(image_bytes)


def render_html_cli() -> None:
    """Command-line entry point for generating an HTML embed snippet from execution trace."""
    parser = argparse.ArgumentParser(
        description="Generate an HTML script tag embed from a Java execution trace"
    )

    _ = parser.add_argument(
        "--container-id",
        help="Optional custom container ID for the HTML element.",
        default=None,
    )

    _ = parser.add_argument(
        "--bundle-url",
        help="Optional URL for the CodeVisualizer bundle JS.",
        default=None,
    )

    _ = parser.add_argument(
        "--no-bundle-script",
        action="store_true",
        help="Omit the external bundle script tag in the HTML snippet.",
    )

    _ = parser.add_argument(
        "--visualizer",
        help="Visualizer implementation to use ('pytutor' or 'json-pre').",
        choices=["pytutor", "json-pre"],
        default="pytutor",
    )

    _ = parser.add_argument(
        "-b",
        "--breakpoint",
        dest="breakpoint",
        help="Breakpoint line to visualize (optional).",
        default=None,
    )

    _ = parser.add_argument(
        "--text-memory-labels",
        action="store_true",
        help="Render object connections as text labels instead of arrows.",
    )

    _ = parser.add_argument(
        "--no-include-types",
        action="store_true",
        help="Omit type tags from the visualization.",
    )

    add_theme_argument(parser)
    add_array_arguments(parser)
    args = parser.parse_args()
    array_options = {**array_options_from_args(args), **theme_options(args.theme)}

    bp: int | tuple[int, int] | None = -1
    if args.breakpoint is not None:
        if "," in args.breakpoint:
            parts = [int(p.strip()) for p in args.breakpoint.split(",") if p.strip()]
            if len(parts) == 2:
                bp = (parts[0], parts[1])
            elif len(parts) == 1:
                bp = parts[0]
        else:
            bp = int(args.breakpoint)

    with fileinput.input("-") as f:
        stdin_data = "".join(f)

    html_snippet = render_html(
        stdin_data,
        container_id=args.container_id,
        bundle_url=args.bundle_url,
        include_bundle_script=not args.no_bundle_script,
        include_types=not args.no_include_types,
        text_memory_labels=args.text_memory_labels,
        visualizer=args.visualizer,
        **array_options,
        breakpoint=bp,
    )
    sys.stdout.write(html_snippet + "\n")


if __name__ == "__main__":
    main()
