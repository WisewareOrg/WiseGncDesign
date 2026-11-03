"""The `gnc-analyze` command: the error report of one run file or a directory of run files."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from gnc_analysis.report import analyze
from gnc_analysis.runs import RunDataError

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """The `gnc-analyze` command. Returns 0 on success and 1 when the input is rejected by
    the loader, printing the loader's message to stderr; argparse exits with 2 on a usage
    error."""
    parser = argparse.ArgumentParser(
        prog="gnc-analyze",
        description="Attitude, position and velocity error of one run file or a directory of "
        "them, against truth.",
    )
    parser.add_argument(
        "path", type=Path, help="a run file, run_<NNNN>.h5, or a directory of run files"
    )
    parser.add_argument("--out", type=Path, required=True, help="directory for the report")
    args = parser.parse_args(argv)
    try:
        analyze(args.path, args.out)
    except RunDataError as exc:
        print(f"gnc-analyze: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
