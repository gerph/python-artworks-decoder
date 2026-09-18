#!/usr/bin/env python3
"""Run the riscos-artworks command line directly from a source checkout."""

from pathlib import Path
import sys

try:
    from riscos_artworks.cli import main
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from riscos_artworks.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
