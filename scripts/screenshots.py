"""Screenshot every page of the running app at laptop width, for review and the README.

Usage: python scripts/screenshots.py http://localhost:8501 docs/screenshots
The Ask page asks one example question, so it needs a model key in the environment.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = {"benchmark": "benchmark", "sources": "sources", "method": "method"}
QUESTION = "Which five states collected the most GST in August 2026?"


def settle(page) -> None:
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=60_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3_000)


def main(base: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        for name, path in PAGES.items():
            page.goto(f"{base}/{path}")
            settle(page)
            page.screenshot(path=out / f"{name}.png", full_page=True)
            print(f"saved {name}")
        page.goto(base)
        settle(page)
        page.get_by_role("button", name=QUESTION).click()
        page.wait_for_timeout(1_000)
        page.get_by_role("button", name="Ask", exact=True).click()
        try:
            page.get_by_text("Sources").first.wait_for(timeout=240_000)
        except Exception as error:  # still save what the page shows
            print(f"no answer seen: {error}")
        page.wait_for_timeout(3_000)
        page.screenshot(path=out / "ask.png", full_page=True)
        print("saved ask")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
