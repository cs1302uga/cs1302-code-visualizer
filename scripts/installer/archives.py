"""Load the shared ZIP helper without initializing the application package."""

from pathlib import Path
from runpy import run_path

extract_zip = run_path(
    str(Path(__file__).resolve().parents[2] / "cs1302_code_visualizer/util/archives.py")
)["extract_zip"]
