#!/usr/bin/env python3
"""ClipForge CLI entrypoint. See `python clipforge.py --help`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "python"))

from clipforge.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
