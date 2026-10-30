"""Benchmark commands.

python -m bharat.eval gold                       gold answers and eval/REVIEW.md
python -m bharat.eval run --setup full --split dev [--limit N]
python -m bharat.eval report                     eval/results/REPORT.md, error_analysis.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from bharat.eval.gold import SERVING_DB, write_gold


def _summarise_llm(llm) -> None:
    """Post which provider answered how often, and why calls failed, as a run notice."""
    import os
    from collections import Counter

    used = Counter(c.provider for c in llm.calls)
    failures = Counter(f[:240] for f in llm.failures)
    lines = [f"calls answered: {dict(used)}", f"provider failures: {len(llm.failures)}"]
    lines += [f"{n} x {text}" for text, n in failures.most_common(6)]
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        body = text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::notice title=LLM providers::{body}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bharat.eval")
    parser.add_argument("command", choices=["gold", "run", "report"])
    parser.add_argument("--database", type=Path, default=SERVING_DB)
    parser.add_argument("--setup", choices=["plain", "no_metrics", "full", "all"], default="full")
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--limit", type=int, default=0, help="at most this many new questions")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command == "gold":
        gold_path, review_path = write_gold(args.database)
        print(f"wrote {gold_path} and {review_path}")
    elif args.command == "run":
        from bharat.agent.llm import OpenAICompatibleLLM
        from bharat.eval.run import SETUPS, run

        llm = OpenAICompatibleLLM()
        try:
            for setup in SETUPS if args.setup == "all" else (args.setup,):
                print(f"wrote {run(setup, args.split, llm, limit=args.limit)}")
        finally:
            _summarise_llm(llm)
    else:
        from bharat.eval.run import report

        report_path, errors_path = report()
        print(report_path.read_text(encoding="utf-8"))
        print(f"wrote {report_path} and {errors_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
