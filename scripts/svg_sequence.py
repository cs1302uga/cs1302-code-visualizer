"""Build a self-contained experimental player from shared SVG sequence nodes."""

import argparse
from pathlib import Path

from cs1302_code_visualizer import RenderingSession
from cs1302_code_visualizer.browser_driver import generate_step_images
from cs1302_code_visualizer.svg_sequence import pack_frames, sequence_html

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with RenderingSession(max_browsers=1) as session:
        frames = generate_step_images(args.trace.read_text(), format="SVG", session=session)
    manifest = pack_frames(frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(sequence_html(manifest))
    print(f"{len(frames)} frames, {len(manifest['nodes'])} unique subtrees: {args.output}")


if __name__ == "__main__":
    main()
