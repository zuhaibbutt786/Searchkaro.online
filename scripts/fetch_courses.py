#!/usr/bin/env python3
"""
Scrape free Udemy listings from jobs.e-next.in, resolve ONLY udemy.com links,
write data/courses.json, and build on-site detail pages (no couponami/third-party).
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup

from groq_client import groq_chat_json

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "courses.json"
PAGES_DIR = ROOT / "courses" / "p"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

ENEXT_PAGES = [f"https://jobs.e-next.in/course/udemy/{i}" for i in range(1, 8)]

BLOCKED_HOSTS = {
    "couponami.com",
    "www.couponami.com",
    "discudemy.com",
    "www.discudemy.com",
    "coursevania.com",
    "www.coursevania.com",
    "real.discount",
    "www.real.discount",
    "cdn.real.discount",
}


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:90] or f"course-{int(time.time())}"


def is_udemy_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return host in {"udemy.com", "www.udemy.com"} and "/course/" in url


def is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return True
    return host in BLOCKED_HOSTS or any(b in host for b in ("couponami", "discudemy", "coursevania"))


def normalize_udemy(url: str) -> str:
    if not is_udemy_url(url):
        return ""
    p = urlparse(url)
    qs = parse_qs(p.query)
    keep = {}
    if "couponCode" in qs:
        keep["couponCode"] = qs["couponCode"][0]
    new_q = urlencode(keep)
    return urlunparse(("https", "www.udemy.com", p.path.rstrip("/") + "/", "", new_q, ""))


def extract_udemy_from_html(text: str) -> str:
    for m in re.finditer(
        r"https?://(?:www\.)?udemy\.com/course/[a-zA-Z0-9\-_/]+(?:\?[^\"'\s]*)?",
        text,
    ):
        u = m.group(0).rstrip("\"').,;")
        if "couponCode=" in u:
            return normalize_udemy(u)
    for m in re.finditer(
        r"https?://(?:www\.)?udemy\.com/course/[a-zA-Z0-9\-_/]+",
        text,
    ):
        return normalize_udemy(m.group(0))
    return ""


def parse_enext_list(html_text: str, base: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    items: list[dict] = []
    seen: set[str] = set()

    for a in soup.select("a[href*='/course/udemy/']"):
        href = a.get("href") or ""
        if href.startswith("/"):
            href = urljoin(base, href)
        if re.search(r"/course/udemy/\d+/?$", href):
            continue
        if "/course/udemy/enroll" in href:
            continue

        title = clean_text(a.get_text(" ", strip=True))
        if len(title) < 10:
            parent = a.find_parent(["div", "article", "li"])
            if parent:
                h = parent.select_one("h2, h3, h4, h5, .title")
                if h:
                    title = clean_text(h.get_text(" ", strip=True))
        if len(title) < 10 or title.lower() in seen:
            continue
        if title.lower() in {"enroll now free", "view course", "home"}:
            continue

        image = ""
        parent = a.find_parent(["div", "article", "li", "section"]) or a.parent
        if parent:
            img = parent.select_one("img[src*='udemycdn'], img[data-src*='udemycdn'], img")
            if img:
                image = img.get("src") or img.get("data-src") or ""
                if image.startswith("//"):
                    image = "https:" + image

        meta = clean_text(parent.get_text(" ", strip=True) if parent else "")
        language = "English"
        for lang in ("English", "Spanish", "Portuguese", "German", "French", "Hindi", "Arabic"):
            if re.search(rf"\b{lang}\b", meta, re.I):
                language = lang
                break
        category = "IT & Software"
        for cat in (
            "Development", "Business", "Design", "Marketing",
            "Finance & Accounting", "IT & Software", "Personal Development",
            "Health & Fitness", "Office Productivity", "Photography", "Music",
        ):
            if cat.lower() in meta.lower():
                category = cat
                break

        seen.add(title.lower())
        items.append(
            {
                "title": title[:180],
                "enext_url": href,
                "image": image,
                "category": category,
                "language": language,
            }
        )
    return items


def resolve_udemy(enext_url: str) -> tuple[str, str, dict]:
    meta: dict = {}
    image = ""
    try:
        r = requests.get(enext_url, headers=HEADERS, timeout=25, allow_redirects=True)
        if r.status_code != 200:
            return "", "", meta
        if is_udemy_url(r.url):
            return normalize_udemy(r.url), image, meta

        soup = BeautifulSoup(r.text, "html.parser")
        udemy = ""
        for a in soup.select("a[href*='udemy.com/course']"):
            href = a.get("href") or ""
            if is_udemy_url(href):
                udemy = normalize_udemy(href)
                if "couponCode=" in href:
                    break
        if not udemy:
            udemy = extract_udemy_from_html(r.text)

        img = soup.select_one("img[src*='udemycdn']")
        if img and img.get("src"):
            image = img["src"]
            if image.startswith("//"):
                image = "https:" + image

        text = soup.get_text("\n", strip=True)
        for line in text.splitlines():
            low = line.lower()
            if low.startswith("language"):
                meta["language"] = line.split(None, 1)[-1][:40]
            elif low.startswith("category") and "sub" not in low:
                meta["category"] = line.split(None, 1)[-1][:80]
            elif low.startswith("creator") or low.startswith("instructor"):
                meta["instructor"] = line.split(None, 1)[-1][:100]
            elif low.startswith("length") or ("hours" in low and len(line) < 40):
                meta["length"] = line[:40]

        p = soup.select_one(".description, #description, .course-description, article p")
        if p:
            meta["raw_desc"] = clean_text(p.get_text(" ", strip=True))[:600]

        return udemy, image, meta
    except Exception as e:
        print(f"  resolve fail {enext_url}: {e}")
        return "", "", meta


def fallback_copy(title: str, category: str, raw_desc: str) -> dict:
    return {
        "summary": raw_desc
        or f"{title} is listed with a free Udemy coupon in {category}. Open the Udemy page and confirm the price shows free before checkout.",
        "learn": [
            "Core ideas covered in the course",
            "Practical examples you can apply",
            "Certificate of completion when eligible",
            "Lifetime access after successful enrollment",
        ],
        "who": f"Learners interested in {category} who want a free coupon seat while it lasts.",
        "note": "Coupons expire or hit limits — confirm $0 on Udemy before enrolling.",
    }


def groq_course_copy(title: str, category: str, language: str, raw_desc: str) -> dict:
    prompt = f"""Write a short course landing page for a free Udemy coupon listing.

Title: {title}
Category: {category}
Language: {language}
Source notes: {raw_desc[:400]}

Return ONLY JSON:
{{
  "summary": "2-3 sentences, plain and useful",
  "learn": ["bullet 1", "bullet 2", "bullet 3", "bullet 4"],
  "who": "one sentence who this is for",
  "note": "one line: coupon may expire; confirm $0 on Udemy"
}}
No marketing fluff. No 'game-changer'. JSON only."""
    data = groq_chat_json(
        system="Clear course copywriter. JSON only.",
        user=prompt,
        temperature=0.5,
        max_tokens=700,
        timeout=40,
    )
    if not data:
        return fallback_copy(title, category, raw_desc)
    data["learn"] = list(data.get("learn") or [])[:6]
    if not data.get("summary"):
        return fallback_copy(title, category, raw_desc)
    return data


def render_detail_page(course: dict) -> str:
    title = html.escape(course.get("title") or "Course")
    summary = html.escape(course.get("summary") or "")
    who = html.escape(course.get("who") or "")
    note = html.escape(course.get("note") or "")
    category = html.escape(course.get("category") or "")
    language = html.escape(course.get("language") or "English")
    instructor = html.escape(course.get("instructor") or "")
    length = html.escape(course.get("length") or "")
    image = html.escape(course.get("image") or "")
    udemy = html.escape(course.get("udemy_url") or "#")
    learn = course.get("learn") or []
    learn_html = "\n".join(f"<li>{html.escape(str(x))}</li>" for x in learn)

    img_block = (
        f'<div class="detail-hero"><img src="{image}" alt="" referrerpolicy="no-referrer" /></div>'
        if image
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — Free Udemy Coupon | LearnWithZuhaib</title>
  <meta name="description" content="{summary[:160]}" />
  <link rel="stylesheet" href="../../assets/style.css" />
  <style>
    .detail {{ max-width: 820px; margin: 0 auto; padding: 28px 0 56px; }}
    .detail-hero {{ border-radius: 14px; overflow: hidden; border: 1px solid var(--line); margin-bottom: 18px; }}
    .detail-hero img {{ width: 100%; display: block; aspect-ratio: 16/9; object-fit: cover; }}
    .detail h1 {{ font-size: 1.65rem; color: var(--brand); margin: 0 0 10px; line-height: 1.25; }}
    .detail-meta {{ color: var(--muted); margin-bottom: 16px; }}
    .detail-box {{ background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; margin-bottom: 14px; box-shadow: var(--shadow); }}
    .detail-box h2 {{ margin: 0 0 10px; font-size: 1.05rem; color: var(--brand); }}
    .detail-box ul {{ margin: 0; padding-left: 1.2rem; color: #374151; }}
    .detail-actions {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../../index.html">Learn<span>With</span>Zuhaib</a>
      <nav>
        <a href="../../index.html">Home</a>
        <a href="../../blog/">Tech Blog</a>
        <a href="../" class="active">Free Courses</a>
      </nav>
    </div>
  </header>

  <main class="container detail">
    {img_block}
    <p><span class="badge-free" style="position:static">100% OFF coupon</span></p>
    <h1>{title}</h1>
    <p class="detail-meta">
      {language}{f' · {category}' if category else ''}{f' · {instructor}' if instructor else ''}{f' · {length}' if length else ''}
    </p>

    <div class="detail-box">
      <h2>About this course</h2>
      <p>{summary}</p>
    </div>

    <div class="detail-box">
      <h2>What you'll learn</h2>
      <ul>
        {learn_html}
      </ul>
    </div>

    <div class="detail-box">
      <h2>Who this is for</h2>
      <p>{who}</p>
      <p class="note">{note}</p>
    </div>

    <div class="detail-actions">
      <a class="btn green" href="{udemy}" target="_blank" rel="noopener noreferrer">Enroll on Udemy (free)</a>
      <a class="btn secondary" href="../">← Back to course list</a>
    </div>
  </main>

  <footer class="site-footer">
    <div class="container">
      <p>Not affiliated with Udemy. Final enrollment happens only on udemy.com.</p>
    </div>
  </footer>
</body>
</html>
"""


def main() -> None:
    collected: list[dict] = []
    seen: set[str] = set()

    for page in ENEXT_PAGES:
        print(f"List: {page}")
        try:
            resp = requests.get(page, headers=HEADERS, timeout=30)
            print(f"  status={resp.status_code}")
            if resp.status_code != 200:
                continue
            for item in parse_enext_list(resp.text, page):
                key = item["title"].lower()
                if key in seen:
                    continue
                seen.add(key)
                collected.append(item)
        except Exception as e:
            print(f"  error: {e}")
        time.sleep(1.0)

    print(f"Collected {len(collected)} list items from e-next")

    courses: list[dict] = []
    max_detail = int(os.getenv("MAX_COURSE_DETAIL", "60"))
    for i, item in enumerate(collected[:max_detail]):
        print(f"Detail {i+1}/{min(max_detail, len(collected))}: {item['title'][:50]}")
        udemy, image, meta = resolve_udemy(item["enext_url"])
        if not udemy or is_blocked(udemy) or not is_udemy_url(udemy):
            print("  skip — no direct Udemy URL")
            time.sleep(0.5)
            continue

        category = meta.get("category") or item.get("category") or "IT & Software"
        language = meta.get("language") or item.get("language") or "English"
        image = image or item.get("image") or ""
        copy = groq_course_copy(item["title"], category, language, meta.get("raw_desc", ""))

        slug = slugify(item["title"])
        course = {
            "title": item["title"],
            "slug": slug,
            "udemy_url": udemy,
            "image": image,
            "category": category,
            "language": language,
            "instructor": meta.get("instructor", ""),
            "length": meta.get("length", ""),
            "summary": copy.get("summary", ""),
            "learn": copy.get("learn", []),
            "who": copy.get("who", ""),
            "note": copy.get("note", ""),
            "page": f"p/{slug}.html",
        }
        courses.append(course)
        time.sleep(0.7)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "jobs.e-next.in",
        "count": len(courses),
        "courses": courses,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(courses)} courses → {OUT}")

    if PAGES_DIR.exists():
        for old in PAGES_DIR.glob("*.html"):
            old.unlink()
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for course in courses:
        path = PAGES_DIR / f"{course['slug']}.html"
        path.write_text(render_detail_page(course), encoding="utf-8")
    print(f"Wrote {len(courses)} detail pages → {PAGES_DIR}")


if __name__ == "__main__":
    main()
