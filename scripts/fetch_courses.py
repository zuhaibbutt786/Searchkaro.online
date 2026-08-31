#!/usr/bin/env python3
"""Fetch free Udemy courses (title, image, category, enroll URL) into data/courses.json."""

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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

ENEXT_PAGES = [
    "https://jobs.e-next.in/course/udemy/1",
    "https://jobs.e-next.in/course/udemy/2",
    "https://jobs.e-next.in/course/udemy/3",
    "https://jobs.e-next.in/course/udemy/4",
    "https://jobs.e-next.in/course/udemy/5",
]


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def parse_enext_list(html: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    # Cards / rows that contain a Udemy CDN image or enroll link
    candidates = soup.select(
        ".course-card, .card, .single-course, .course-item, .row .col-md-4, "
        ".row .col-lg-4, .row .col-sm-6, article, .item"
    )
    if not candidates:
        candidates = soup.find_all(["div", "article"], recursive=True)

    seen = set()
    for node in candidates:
        img = node.select_one("img[src*='udemycdn'], img[data-src*='udemycdn'], img[src*='udemy']")
        link = node.select_one(
            "a[href*='/course/udemy/'], a[href*='udemy.com'], a.btn, a.enroll"
        )
        title_el = node.select_one("h2, h3, h4, h5, .title, .course-title, a")
        if not title_el:
            continue
        title = clean_text(title_el.get_text(" ", strip=True))
        if len(title) < 8 or title.lower() in seen:
            continue
        # skip nav noise
        if title.lower() in {"enroll now free", "view course", "home", "search"}:
            continue

        href = ""
        if link and link.get("href"):
            href = link.get("href")
        elif title_el.name == "a" and title_el.get("href"):
            href = title_el.get("href")
        if href and href.startswith("/"):
            href = urljoin(base, href)

        image = ""
        if img:
            image = img.get("src") or img.get("data-src") or ""
            if image.startswith("//"):
                image = "https:" + image

        meta = clean_text(node.get_text(" ", strip=True))
        language = "English"
        for lang in ("English", "Spanish", "Portuguese", "German", "French", "Hindi", "Arabic"):
            if re.search(rf"\b{lang}\b", meta, re.I):
                language = lang
                break

        category = ""
        for cat in (
            "IT & Software",
            "Development",
            "Business",
            "Design",
            "Marketing",
            "Finance & Accounting",
            "Personal Development",
            "Health & Fitness",
            "Office Productivity",
            "Photography",
            "Music",
        ):
            if cat.lower() in meta.lower():
                category = cat
                break

        # Prefer rows that at least have an image or a course detail link
        if not image and "/course/udemy/" not in (href or ""):
            continue

        seen.add(title.lower())
        items.append(
            {
                "title": title[:180],
                "url": href or base,
                "image": image,
                "category": category or "IT & Software",
                "language": language,
                "source": "e-next",
            }
        )
    return items


def enrich_enext_detail(item: dict) -> dict:
    """Open e-next detail page to get Udemy coupon URL + better image when possible."""
    url = item.get("url") or ""
    if "jobs.e-next.in" not in url:
        return item
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return item
        soup = BeautifulSoup(r.text, "html.parser")
        # Udemy link
        for a in soup.select("a[href*='udemy.com']"):
            href = a.get("href") or ""
            if "/course/" in href:
                item["url"] = href
                break
        m = re.search(r"https?://(?:www\.)?udemy\.com/course/[^\"'\s>]+", r.text)
        if m and "udemy.com" not in item.get("url", ""):
            item["url"] = m.group(0)
        # image
        img = soup.select_one("img[src*='udemycdn']")
        if img and img.get("src"):
            item["image"] = img["src"]
        # meta table
        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            if line.lower().startswith("language"):
                parts = line.split()
                if len(parts) > 1:
                    item["language"] = parts[-1]
            if line.lower().startswith("category") and "sub" not in line.lower():
                item["category"] = line.split(None, 1)[-1][:80]
    except Exception:
        return item
    return item


def fetch_real_discount(limit: int = 150) -> list[dict]:
    """Public CDN used by real.discount free course listings."""
    api = "https://cdn.real.discount/api/courses?page=1&limit={}&sortBy=sale_start&store=Udemy&freeOnly=true".format(
        limit
    )
    headers = {
        **HEADERS,
        "Host": "cdn.real.discount",
        "Referer": "https://www.real.discount/",
    }
    try:
        r = requests.get(api, headers=headers, timeout=30)
        print(f"real.discount status={r.status_code}")
        if r.status_code != 200:
            return []
        data = r.json()
        rows = data.get("items") or data.get("courses") or data.get("results") or []
        if isinstance(data, list):
            rows = data
        out = []
        for row in rows:
            title = clean_text(row.get("name") or row.get("title") or "")
            if not title:
                continue
            url = row.get("url") or row.get("link") or row.get("coupon_url") or ""
            image = row.get("image") or row.get("image_url") or row.get("thumbnail") or ""
            if image and image.startswith("//"):
                image = "https:" + image
            category = clean_text(row.get("category") or row.get("subcategory") or "IT & Software")
            out.append(
                {
                    "title": title[:180],
                    "url": url,
                    "image": image,
                    "category": category[:80] if category else "IT & Software",
                    "language": clean_text(row.get("language") or "English") or "English",
                    "source": "real.discount",
                }
            )
        return out
    except Exception as e:
        print(f"real.discount error: {e}")
        return []


def main() -> None:
    collected: list[dict] = []
    seen: set[str] = set()

    # 1) e-next list pages
    for page in ENEXT_PAGES:
        print(f"Fetching {page}")
        try:
            resp = requests.get(page, headers=HEADERS, timeout=30)
            print(f"  status={resp.status_code} bytes={len(resp.content)}")
            if resp.status_code != 200:
                continue
            batch = parse_enext_list(resp.text, page)
            print(f"  parsed={len(batch)}")
            for item in batch:
                key = item["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(item)
        except Exception as e:
            print(f"  error: {e}")
        time.sleep(1.0)

    # Enrich first N detail pages for real Udemy links + images
    enriched = []
    for i, item in enumerate(collected[:80]):
        item = enrich_enext_detail(item)
        enriched.append(item)
        if i % 10 == 0:
            print(f"Enriched {i+1}/{min(80, len(collected))}")
        time.sleep(0.6)
    # keep remaining without enrichment
    if len(collected) > 80:
        enriched.extend(collected[80:])

    # 2) real.discount free API fallback / merge
    rd = fetch_real_discount(200)
    print(f"real.discount courses={len(rd)}")
    for item in rd:
        key = item["title"].lower()
        if key in seen:
            # fill missing image/url on existing
            for ex in enriched:
                if ex["title"].lower() == key:
                    if not ex.get("image") and item.get("image"):
                        ex["image"] = item["image"]
                    if "udemy.com" not in (ex.get("url") or "") and item.get("url"):
                        ex["url"] = item["url"]
                    break
            continue
        seen.add(key)
        enriched.append(item)

    # Prefer items with images and udemy links
    enriched.sort(
        key=lambda x: (
            0 if x.get("image") else 1,
            0 if "udemy.com" in (x.get("url") or "") else 1,
        )
    )

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "e-next+real.discount",
        "count": len(enriched),
        "courses": enriched[:300],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(payload['courses'])} courses → {OUT}")


if __name__ == "__main__":
    main()
