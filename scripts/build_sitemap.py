#!/usr/bin/env python3
"""Build sitemap.xml with absolute URLs for searchkaro.online."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = (os.getenv("SITE_BASE_URL") or "https://searchkaro.online").rstrip("/")

SKIP_DIRS = {".git", ".github", "scripts", "data", "node_modules"}
SKIP_FILES = {"README.md", "CNAME"}


def main() -> None:
    urls: list[str] = [f"{BASE}/"]

    # All HTML files in the site
    for path in sorted(ROOT.rglob("*.html")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        # index.html → directory URL
        if path.name == "index.html":
            parent = str(rel.parent).replace("\\", "/")
            if parent == ".":
                continue  # already added as BASE/
            urls.append(f"{BASE}/{parent}/")
        else:
            urls.append(f"{BASE}/{str(rel).replace(chr(92), '/')}")

    # Prefer stable order, unique
    seen = []
    for u in urls:
        if u not in seen:
            seen.append(u)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for u in seen:
        lines.append(f"  <url><loc>{u}</loc></url>")
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"sitemap urls={len(seen)} base={BASE}")


if __name__ == "__main__":
    main()
