#!/usr/bin/env python3
"""Fetch free Udemy coupon listings and write data/courses.json."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "courses.json"

# Public coupon aggregator pages (HTML list pages)
SOURCES = [
    "https://www.discudemy.com/all",
    "https://www.discudemy.com/all/2",
    "https://www.discudemy.com/all/3",
    "https://www.discudemy.com/all/4",
    "https://www.discudemy.com/all/5",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LearnWithZuhaibBot/1.0; +https://github.com/zuhaibbutt786/tech-blog-courses)",
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_discudemy(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    # DiscUdemy card layout varies; try common patterns
    for card in soup.select(".card, .content, article, .course"):
        title_el = card.select_one("a.card-header, .card-header a, h5 a, h4 a, h3 a, a.course-title")
        if not title_el:
            continue
        title = title_el.get_text(" ", strip=True)
        href = title_el.get("href") or ""
        if not title or not href:
            continue
        if href.startswith("/"):
            href = urljoin(base, href)

        cat_el = card.select_one(".category, .cat, .meta, .ui.label")
        category = cat_el.get_text(" ", strip=True) if cat_el else ""
        # language often near meta
        text = card.get_text(" ", strip=True)
        language = "English"
        if re.search(r"\bSpanish\b", text, re.I):
            language = "Spanish"
        elif re.search(r"\bPortuguese\b", text, re.I):
            language = "Portuguese"
        elif re.search(r"\bGerman\b", text, re.I):
            language = "German"
        elif re.search(r"\bFrench\b", text, re.I):
            language = "French"

        items.append(
            {
                "title": title[:180],
                "url": href,
                "category": category[:80] if category else "IT & Software",
                "language": language,
                "source": "discudemy",
            }
        )
    return items


def resolve_udemy_link(detail_url: str) -> str | None:
    """Follow aggregator detail page to a udemy.com coupon URL when possible."""
    try:
        r = requests.get(detail_url, headers=HEADERS, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='udemy.com']"):
            href = a.get("href") or ""
            if "udemy.com" in href and ("couponCode=" in href or "/course/" in href):
                return href.split()[0]
        # sometimes in buttons
        m = re.search(r"https?://(?:www\.)?udemy\.com/course/[^\"'\s]+", r.text)
        if m:
            return m.group(0)
    except Exception:
        return None
    return None


def main() -> None:
    collected: list[dict] = []
    seen_titles: set[str] = set()

    for url in SOURCES:
        print(f"Fetching {url}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            print(f"  status={resp.status_code} bytes={len(resp.content)}")
            if resp.status_code != 200:
                continue
            batch = parse_discudemy(resp.text, url)
            print(f"  parsed={len(batch)}")
            for item in batch:
                key = item["title"].lower()
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                collected.append(item)
        except Exception as e:
            print(f"  error: {e}")
        time.sleep(1.2)

    # Resolve a limited number of detail pages to real Udemy coupon links
    resolved = []
    for i, item in enumerate(collected[:120]):
        udemy = resolve_udemy_link(item["url"])
        if udemy:
            item = {**item, "url": udemy, "aggregator_url": item["url"]}
            resolved.append(item)
            print(f"Resolved {i+1}: {item['title'][:50]}")
        else:
            # keep aggregator link as fallback (user still reaches coupon page)
            resolved.append(item)
        time.sleep(0.8)

    # Prefer items that already point at udemy.com
    resolved.sort(key=lambda x: 0 if "udemy.com" in x.get("url", "") else 1)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "discudemy",
        "count": len(resolved),
        "courses": resolved[:200],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload['courses'])} courses → {OUT}")


if __name__ == "__main__":
    main()
