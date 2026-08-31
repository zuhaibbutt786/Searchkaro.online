#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://zuhaibbutt786.github.io/tech-blog-courses"


def main() -> None:
    urls = [
        f"{BASE}/",
        f"{BASE}/blog/",
        f"{BASE}/courses/",
        f"{BASE}/scholarships/",
        f"{BASE}/jobs/",
        f"{BASE}/about.html",
        f"{BASE}/contact.html",
        f"{BASE}/privacy.html",
    ]
    posts = []
    try:
        posts = json.loads((ROOT / "data" / "posts.json").read_text(encoding="utf-8")).get("posts") or []
    except Exception:
        pass
    for p in posts[:200]:
        slug = p.get("slug")
        if slug:
            urls.append(f"{BASE}/blog/{slug}.html")
    courses = []
    try:
        courses = json.loads((ROOT / "data" / "courses.json").read_text(encoding="utf-8")).get("courses") or []
    except Exception:
        pass
    for c in courses[:200]:
        page = c.get("page")
        if page:
            urls.append(f"{BASE}/courses/{page}")

    body = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?>", '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in dict.fromkeys(urls):
        body.append(f"  <url><loc>{u}</loc></url>")
    body.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"sitemap urls={len(urls)}")


if __name__ == "__main__":
    main()
