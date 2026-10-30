"""Screenshot every page of the running app at laptop width, for review and the README.

Usage: python scripts/screenshots.py http://localhost:8501 docs/screenshots
The Ask page asks one example question, so it needs a model key in the environment.
Streamlit scrolls inside its own panel, so each page is captured by growing the window to
the panel's full height rather than with a full-page screenshot.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 1366, 900
PAGES = {"benchmark": "benchmark", "sources": "sources", "method": "method"}
QUESTION = "Which five states collected the most GST in August 2026?"
FULL_HEIGHT = """() => Math.max(...[...document.querySelectorAll(
  '[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main')]
  .map(e => e.scrollHeight), document.body.scrollHeight)"""


def settle(page) -> None:
    page.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=60_000)
    page.wait_for_load_state("networkidle")
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stSpinner\"]')", timeout=300_000
    )
    page.wait_for_timeout(6_000)  # charts and tables draw after the data arrives


def capture(page, path: Path, top_only: bool = False) -> None:
    height = HEIGHT if top_only else min(page.evaluate(FULL_HEIGHT) + 80, 6_000)
    page.set_viewport_size({"width": WIDTH, "height": height})
    page.wait_for_timeout(3_000)
    page.screenshot(path=path)
    page.set_viewport_size({"width": WIDTH, "height": HEIGHT})
    print(f"saved {path.name} ({height} px)")


def main(base: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        for name, path in PAGES.items():
            page.goto(f"{base}/{path}")
            settle(page)
            capture(page, out / f"{name}.png")
        page.goto(base)
        settle(page)
        page.get_by_role("button", name=QUESTION).click()
        page.wait_for_timeout(1_000)
        page.get_by_role("button", name="Ask", exact=True).click()
        page.wait_for_timeout(2_000)
        settle(page)
        capture(page, out / "ask.png")
        capture(page, out / "ask-top.png", top_only=True)  # for the README
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
