"""Run the pipeline directly from a source checkout."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from hold_explorer.pipeline import main

if __name__ == "__main__":
    main()
