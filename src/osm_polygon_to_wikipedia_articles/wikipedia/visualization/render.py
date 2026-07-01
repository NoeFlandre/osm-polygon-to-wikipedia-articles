"""Render a folium map HTML to a PNG via headless Chrome.

Library API: :func:`render_map_png`.
CLI: ``uv run python scripts/render_map_png.py ...``
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def render_map_png(html_path: Path, png_path: Path, width: int = 1000, height: int = 600) -> Path:
    """Open ``html_path`` in headless Chrome and save a ``width x height`` PNG."""
    html_path = Path(html_path).resolve()
    png_path = Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"file://{html_path}"

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        try:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            # folium tiles render async after the initial paint; give them time
            time.sleep(2.0)
            page.screenshot(path=str(png_path), full_page=False)
        finally:
            browser.close()

    return png_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1000)
    parser.add_argument("--height", type=int, default=600)
    args = parser.parse_args()
    out = render_map_png(args.in_path, args.out, args.width, args.height)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()


__all__ = ["render_map_png"]