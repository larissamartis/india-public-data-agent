"""Print the raw source text behind chosen gold answers, read independently of the parsers.

For the PDF sources there is no human-readable cell to open on the build machine, so this
shows exactly what the PDF says: the Table 11 column headers and year rows for named areas
(as plain text, and as pdfplumber's table extractor sees them), and TRAI Annexure II rows.
A reviewer compares these with eval/REVIEW.md and records the result in eval/hand_checks.md.
"""

from __future__ import annotations

import os
from pathlib import Path

from bharat.ingest.manual import entries_for, fetch_files

POPULATION_AREAS = {
    "ODISHA": ["2030"],
    "PUDUCHERRY": ["2020", "2030"],
    "DAMAN": ["2026"],
    "DADRA": ["2026"],
    "LADAKH": ["2026"],
    "HARYANA": ["2026"],
    "RAJASTHAN": ["2026"],
    "KERALA": ["2030"],
}
TRAI_AREAS = ["Kerala", "Mumbai", "U.P. (E)", "U.P.(E)", "Bihar", "Himachal", "North East", "Total"]


def _note(title: str, text: str) -> None:
    print(f"==== {title}\n{text}\n")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        body = text[:5500].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
        print(f"::notice title={title}::{body}", flush=True)


def population(path: Path) -> None:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        for number in range(85, 99):  # PDF pages 86-98 hold Table 11
            page = pdf.pages[number]
            lines = (page.extract_text() or "").splitlines()
            head = " ".join(lines[:6])
            found = [area for area in POPULATION_AREAS if area in head.upper()]
            if not found:
                continue
            header = [ln for ln in lines[:12] if "Persons" in ln or "Male" in ln]
            out = [f"page {number + 1}", *lines[:4], *header]
            for area in found:
                for year in POPULATION_AREAS[area]:
                    rows = [ln for ln in lines if ln.strip().startswith(year)]
                    out.append(f"text row {year} (for {area}): {rows}")
            table = page.extract_table() or []
            out.append("table extractor, header rows:")
            out += [f"  {row}" for row in table[:4]]
            for area in found:
                for year in POPULATION_AREAS[area]:
                    out += [f"  {row}" for row in table if row and str(row[0]).strip() == year]
            _note(f"population p{number + 1} {'/'.join(found)}", "\n".join(out))


def trai(path: Path) -> None:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "Annexure-II" not in text or "Wireless (Mobile)" not in text:
                continue
            lines = text.splitlines()
            out = [ln for ln in lines[:6]]
            out += [ln for ln in lines if any(ln.startswith(a) for a in TRAI_AREAS)]
            _note("trai annexure II", "\n".join(out))
            return


def main() -> int:
    out = Path("data")
    for source, reader in (("population", population), ("trai", trai)):
        [path] = fetch_files(entries_for(source), out / "raw" / "manual" / source)
        reader(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
