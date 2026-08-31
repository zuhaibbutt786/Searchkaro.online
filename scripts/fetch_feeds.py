#!/usr/bin/env python3
"""Pull scholarships + jobs from public RSS feeds, paraphrase with Groq, write JSON + pages."""

from __future__ import annotations

import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from groq_client import groq_chat_json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

HEADERS = {"User-Agent": "LearnWithZuhaibBot/1.0 (+https://github.com/zuhaibbutt786/tech-blog-courses)"}

SCHOLARSHIP_FEEDS = [
    "https://scholarship-positions.com/feed/",
    "https://www.scholars4dev.com/feed/",
    "https://www.scholarshipportal.com/rss",
]

JOB_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://stackoverflow.com/jobs/feed",
    "https://remoteok.com/remote-dev-jobs.rss",
]


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:90] or f"item-{int(datetime.now().timestamp())}"


def parse_rss(url: str, limit: int = 15) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            print(f"  feed {url} status={r.status_code}")
            return []
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  feed fail {url}: {e}")
        return []

    items = []
    # RSS 2.0
    for item in root.findall(".//item")[:limit]:
        title = clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc = clean(item.findtext("description") or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or "")
        pub = item.findtext("pubDate") or ""
        if not title or not link:
            continue
        items.append({"title": title[:200], "url": link, "summary": desc[:500], "published": pub, "source": urlparse(url).netloc})
    # Atom
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns)[:limit]:
            title = clean(entry.findtext("a:title", default="", namespaces=ns))
            link_el = entry.find("a:link", ns)
            link = (link_el.get("href") if link_el is not None else "") or ""
            summary = clean(entry.findtext("a:summary", default="", namespaces=ns) or entry.findtext("a:content", default="", namespaces=ns))
            if title and link:
                items.append({"title": title[:200], "url": link, "summary": summary[:500], "published": "", "source": urlparse(url).netloc})
    return items


def paraphrase(kind: str, title: str, summary: str) -> dict:
    prompt = f"""Rewrite this {kind} listing for a career/education website. Keep facts accurate. Do not invent deadlines or amounts.

Title: {title}
Notes: {summary[:400]}

Return ONLY JSON:
{{
  "title": "clear SEO title under 70 chars",
  "blurb": "2 sentences, natural, keyword-rich but human",
  "who": "who should apply / who this job fits",
  "keywords": ["kw1", "kw2", "kw3"]
}}
JSON only."""
    data = groq_chat_json(
        system="Editor for education and tech careers. Accurate. JSON only.",
        user=prompt,
        temperature=0.45,
        max_tokens=500,
        timeout=40,
    )
    if data and data.get("blurb"):
        return data
    return {
        "title": title[:70],
        "blurb": summary[:280] or f"Latest {kind} listing: {title}",
        "who": f"People searching for {kind} opportunities in tech and related fields.",
        "keywords": [kind, "apply online", "international"],
    }


def collect(feeds: list[str], kind: str, max_items: int) -> list[dict]:
    raw: list[dict] = []
    seen_urls: set[str] = set()
    for feed in feeds:
        print(f"Feed ({kind}): {feed}")
        for item in parse_rss(feed):
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            raw.append(item)
    # light sort by having a pubDate
    def key(it):
        try:
            return parsedate_to_datetime(it.get("published") or "").timestamp()
        except Exception:
            return 0

    raw.sort(key=key, reverse=True)
    out = []
    for i, item in enumerate(raw[:max_items]):
        # paraphrase every item is slow; every 2nd uses Groq
        if i % 2 == 0 and os.getenv("GROQ_API_KEY"):
            copy = paraphrase(kind, item["title"], item.get("summary", ""))
        else:
            copy = {
                "title": item["title"][:70],
                "blurb": (item.get("summary") or item["title"])[:280],
                "who": f"Candidates interested in {kind} opportunities.",
                "keywords": [kind],
            }
        out.append(
            {
                "title": copy.get("title") or item["title"],
                "slug": slugify(copy.get("title") or item["title"]),
                "url": item["url"],
                "blurb": copy.get("blurb") or "",
                "who": copy.get("who") or "",
                "keywords": copy.get("keywords") or [],
                "source": item.get("source") or "",
                "published": item.get("published") or "",
            }
        )
    return out


def write_list_page(kind: str, items: list[dict], path: Path, heading: str, intro: str) -> None:
    cards = []
    for it in items:
        cards.append(
            f"""<article class="card list-card">
  <h2><a href="{html.escape(it['url'])}" target="_blank" rel="noopener nofollow">{html.escape(it['title'])}</a></h2>
  <p class="excerpt">{html.escape(it.get('blurb') or '')}</p>
  <p class="meta">{html.escape(it.get('source') or '')} · {html.escape((it.get('who') or '')[:120])}</p>
  <a class="btn secondary" href="{html.escape(it['url'])}" target="_blank" rel="noopener nofollow">View details →</a>
</article>"""
        )
    body = "\n".join(cards) or '<p class="empty">New listings appear after the next daily update.</p>'
    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(heading)} | LearnWithZuhaib</title>
  <meta name="description" content="{html.escape(intro[:160])}" />
  <meta name="keywords" content="{kind}, MS scholarship, PhD scholarship, remote jobs, tech jobs, free learning" />
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../index.html">Learn<span>With</span>Zuhaib</a>
      <nav>
        <a href="../index.html">Home</a>
        <a href="../blog/">Tech Blog</a>
        <a href="../courses/">Free Courses</a>
        <a href="../scholarships/" {'class="active"' if kind=='scholarship' else ''}>Scholarships</a>
        <a href="../jobs/" {'class="active"' if kind=='job' else ''}>Jobs</a>
      </nav>
    </div>
  </header>
  <section class="page-head container">
    <h1>{html.escape(heading)}</h1>
    <p class="sub">{html.escape(intro)}</p>
  </section>
  <main class="container post-list">
{body}
  </main>
  <footer class="site-footer"><div class="container"><p>Aggregated from public feeds. Always verify on the official page.</p></div></footer>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_page, encoding="utf-8")


def main() -> None:
    max_s = int(os.getenv("MAX_SCHOLARSHIPS", "12"))
    max_j = int(os.getenv("MAX_JOBS", "12"))

    scholarships = collect(SCHOLARSHIP_FEEDS, "scholarship", max_s)
    jobs = collect(JOB_FEEDS, "job", max_j)

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "scholarships.json").write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "items": scholarships}, indent=2),
        encoding="utf-8",
    )
    (DATA / "jobs.json").write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "items": jobs}, indent=2),
        encoding="utf-8",
    )

    write_list_page(
        "scholarship",
        scholarships,
        ROOT / "scholarships" / "index.html",
        "MS & PhD Scholarships",
        "Fully funded and partial scholarships for Master's and PhD students. Updated from trusted education feeds.",
    )
    write_list_page(
        "job",
        jobs,
        ROOT / "jobs" / "index.html",
        "Tech & Remote Jobs",
        "Fresh developer, data, and remote engineering roles from major public job feeds.",
    )
    print(f"Scholarships={len(scholarships)} Jobs={len(jobs)}")


if __name__ == "__main__":
    main()
