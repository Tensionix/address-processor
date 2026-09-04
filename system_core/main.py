from __future__ import annotations

import sys
from pathlib import Path

# Allow importing the aligner from the same directory
sys.path.insert(0, str(Path(__file__).parent))

from Ultimate_GT_Aligner import batch_process


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    input_dir = root / "input"
    output_dir = root / "output"
    batch_process(input_dir, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
