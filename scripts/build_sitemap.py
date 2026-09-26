#!/usr/bin/env python3
"""
Build sitemap.xml focused on indexable, high-value URLs.

Google Search Console showed ~800+ "Discovered – not indexed" mostly from
thin course coupon + mass news pages. Submitting every HTML file hurts more
than it helps. This builder:

  * Always includes core hubs and static pages
  * Includes all blog / scholarships / jobs / universities / calculators
  * Limits course detail + news detail to the newest N items from JSON
  * Emits lastmod + priority so Google can focus crawl budget
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
BASE = (os.getenv("SITE_BASE_URL") or "https://searchkaro.online").rstrip("/")

# How many deep pages to list (rest stay on site but out of sitemap)
MAX_COURSE_DETAIL = int(os.getenv("SITEMAP_MAX_COURSES", "40"))
MAX_NEWS_DETAIL = int(os.getenv("SITEMAP_MAX_NEWS", "40"))
MAX_JOB_DETAIL = int(os.getenv("SITEMAP_MAX_JOBS", "40"))
MAX_SCHOLARSHIP_DETAIL = int(os.getenv("SITEMAP_MAX_SCHOLARSHIPS", "40"))


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def add(
    entries: list[tuple[str, str, str]],
    path: str,
    *,
    priority: str = "0.5",
    changefreq: str = "weekly",
    lastmod: str | None = None,
) -> None:
    loc = f"{BASE}/{path.lstrip('/')}" if path not in ("", "/") else f"{BASE}/"
    if path in ("", "/"):
        loc = f"{BASE}/"
    lm = lastmod or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries.append((loc, lm, priority))


def main() -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries: list[tuple[str, str, str]] = []

    # --- Core (highest priority) ---
    add(entries, "/", priority="1.0", changefreq="daily", lastmod=today)
    for p, pr in [
        ("news/", "0.9"),
        ("courses/", "0.9"),
        ("scholarships/", "0.9"),
        ("jobs/", "0.9"),
        ("universities/", "0.8"),
        ("calculators/", "0.8"),
        ("blog/", "0.8"),
        ("about.html", "0.4"),
        ("contact.html", "0.4"),
        ("privacy.html", "0.3"),
    ]:
        add(entries, p, priority=pr, lastmod=today)

    # Calculators tools
    for name in ("loan.html", "age.html", "time.html", "bmi.html", "pregnancy.html"):
        path = ROOT / "calculators" / name
        if path.exists():
            add(entries, f"calculators/{name}", priority="0.7", lastmod=today)

    # Universities static pages
    uni_dir = ROOT / "universities"
    if uni_dir.exists():
        for path in sorted(uni_dir.glob("*.html")):
            if path.name == "index.html":
                continue
            add(entries, f"universities/{path.name}", priority="0.7", lastmod=today)

    # Blog posts (keep all — small set, higher quality signal)
    blog_dir = ROOT / "blog"
    if blog_dir.exists():
        for path in sorted(blog_dir.glob("*.html")):
            if path.name == "index.html":
                continue
            add(entries, f"blog/{path.name}", priority="0.6", lastmod=today)

    # Courses: only newest N detail pages from catalog
    courses_data = load_json(ROOT / "data" / "courses.json")
    courses = list(courses_data.get("courses") or [])
    courses.sort(key=lambda c: c.get("added_at") or c.get("title") or "", reverse=True)
    for c in courses[:MAX_COURSE_DETAIL]:
        page = c.get("page") or (f"p/{c['slug']}.html" if c.get("slug") else "")
        if not page:
            continue
        add(
            entries,
            f"courses/{page.lstrip('/')}",
            priority="0.5",
            lastmod=(c.get("added_at") or today)[:10],
        )

    # News: only newest N
    news_data = load_json(ROOT / "data" / "news.json")
    news = list(news_data.get("items") or [])
    news.sort(key=lambda n: n.get("date") or "", reverse=True)
    for n in news[:MAX_NEWS_DETAIL]:
        page = n.get("page") or (f"p/{n['slug']}.html" if n.get("slug") else "")
        if not page:
            continue
        add(
            entries,
            f"news/{page.lstrip('/')}",
            priority="0.5",
            lastmod=(n.get("date") or today)[:10],
        )

    # Jobs / scholarships detail (capped)
    for kind, max_n in (("jobs", MAX_JOB_DETAIL), ("scholarships", MAX_SCHOLARSHIP_DETAIL)):
        data = load_json(ROOT / "data" / f"{kind}.json")
        items = data.get("items") or data.get(kind) or []
        if isinstance(items, dict):
            items = list(items.values())
        for it in list(items)[:max_n]:
            page = it.get("page") or ""
            slug = it.get("slug") or ""
            if page:
                rel = f"{kind}/{page.lstrip('/')}"
            elif slug:
                rel = f"{kind}/p/{slug}.html"
            else:
                continue
            add(entries, rel, priority="0.5", lastmod=(it.get("date") or today)[:10])

    # Dedupe preserve order
    seen: set[str] = set()
    unique: list[tuple[str, str, str]] = []
    for loc, lm, pr in entries:
        if loc in seen:
            continue
        seen.add(loc)
        unique.append((loc, lm, pr))

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for loc, lm, pr in unique:
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(loc)}</loc>")
        lines.append(f"    <lastmod>{escape(lm)}</lastmod>")
        lines.append(f"    <priority>{escape(pr)}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    out = ROOT / "sitemap.xml"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"sitemap urls={len(unique)} base={BASE} (courses≤{MAX_COURSE_DETAIL}, news≤{MAX_NEWS_DETAIL})")


if __name__ == "__main__":
    main()
