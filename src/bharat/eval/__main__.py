"""Benchmark commands: `python -m bharat.eval gold` writes eval/gold.json and eval/REVIEW.md."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bharat.eval.gold import SERVING_DB, write_gold


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bharat.eval")
    parser.add_argument("command", choices=["gold"])
    parser.add_argument("--database", type=Path, default=SERVING_DB)
    args = parser.parse_args(argv)
    gold_path, review_path = write_gold(args.database)
    print(f"wrote {gold_path} and {review_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
