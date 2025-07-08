#!/bin/env python3

import fileinput
from sys import stdout
from pathlib import Path

import browser_driver
import trace_generator


def render_image(
    java_source: str,
    *,
    java_home: Path | None = None,
    timeout_secs: int | None = None,
    dpi: int = 1,
    format: str = "PNG",
) -> bytes:
    """Visualize the state of a Java program just before exiting as an image.
    java_source:  The Java 8 source code to visualize.
    java_home:    A path to a JDK 8 installation home. If not provided, a JDK will be fetched
                  automatically.
    timeout_secs: Maximum execution time for the Java source's trace generation, or no limit if
                  None.
    dpi:          A positive, integer multiplicative factor for the output image's resolution.
    format:       The image output format. This gets passed directly into PIL's Image.save() method,
                  refer to that method's documentation for acceptable values.

    out:          Raw bytes of the visualization image.

    Note that exceptions may be raised if image generation fails.
    """
    if java_home and not trace_generator.jdk8_exists(java_home):
        raise FileNotFoundError(
            f"Provided {java_home=} is not a valid JDK 8 installation."
        )
    elif not java_home:
        java_home = trace_generator.install_jdk8()

    trace_generator.compile_backend(java_home)
    trace = trace_generator.generate_trace(java_home, java_source, timeout_secs)

    if (v := trace_generator.validate_trace(trace)) is not None:
        raise Exception(v)

    return browser_driver.generate_image(trace, dpi=dpi)


if __name__ == "__main__":
    stdout.buffer.write(render_image("".join(fileinput.input())))
