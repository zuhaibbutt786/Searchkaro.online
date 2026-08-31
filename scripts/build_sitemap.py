#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("SITE_BASE_URL", "https://searchkaro.online").rstrip("/")


def main() -> None:
    urls = [
        f"{BASE}/",
        f"{BASE}/blog/",
        f"{BASE}/courses/",
        f"{BASE}/scholarships/",
        f"{BASE}/jobs/",
        f"{BASE}/universities/",
        f"{BASE}/universities/pakistan.html",
        f"{BASE}/universities/medical.html",
        f"{BASE}/universities/engineering.html",
        f"{BASE}/universities/arts.html",
        f"{BASE}/universities/law.html",
        f"{BASE}/universities/allied-sciences.html",
        f"{BASE}/about.html",
        f"{BASE}/contact.html",
        f"{BASE}/privacy.html",
    ]
    for name, key in (("posts.json", "posts"),):
        try:
            data = json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
            for p in (data.get(key) or [])[:250]:
                if p.get("slug"):
                    urls.append(f"{BASE}/blog/{p['slug']}.html")
        except Exception:
            pass
    try:
        courses = json.loads((ROOT / "data" / "courses.json").read_text(encoding="utf-8")).get("courses") or []
        for c in courses[:250]:
            if c.get("page"):
                urls.append(f"{BASE}/courses/{c['page']}")
    except Exception:
        pass
    for fname, folder in (("scholarships.json", "scholarships"), ("jobs.json", "jobs")):
        try:
            items = json.loads((ROOT / "data" / fname).read_text(encoding="utf-8")).get("items") or []
            for it in items[:250]:
                if it.get("page"):
                    urls.append(f"{BASE}/{folder}/{it['page']}")
        except Exception:
            pass

    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in dict.fromkeys(urls):
        body.append(f"  <url><loc>{u}</loc></url>")
    body.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"sitemap urls={len(list(dict.fromkeys(urls)))}")


if __name__ == "__main__":
    main()
