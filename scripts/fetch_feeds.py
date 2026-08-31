#!/usr/bin/env python3
"""
Scholarships (MS/PhD) + jobs (Pakistan, Europe, remote/world) from public RSS/HTML.
Writes JSON, list pages, and per-item detail pages for SEO.
"""

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
from bs4 import BeautifulSoup

from groq_client import groq_chat_json

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = os.getenv("SITE_BASE_URL", "https://searchkaro.online").rstrip("/")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SCHOLARSHIP_FEEDS = [
    "https://scholarship-positions.com/feed/",
    "https://www.scholars4dev.com/feed/",
    "https://www.scholarshiptab.com/feed",
    "https://opportunitydesk.com/feed",
]

JOB_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-fullstack-programming-jobs.rss",
    "https://remoteok.com/remote-dev-jobs.rss",
    "https://jobicy.com/feed/jobs",
]

# Extra HTML list pages (best-effort)
SCHOLARSHIP_HTML = [
    "https://www.scholars4dev.com/",
    "https://scholarship-positions.com/",
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


def parse_rss(url: str, limit: int = 25) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=28)
        if r.status_code != 200:
            print(f"  feed {url} status={r.status_code}")
            return []
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  feed fail {url}: {e}")
        return []

    items = []
    for item in root.findall(".//item")[:limit]:
        title = clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        desc = clean(
            item.findtext("description")
            or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            or ""
        )
        pub = item.findtext("pubDate") or ""
        if title and link:
            items.append(
                {
                    "title": title[:220],
                    "url": link,
                    "summary": desc[:900],
                    "published": pub,
                    "source": urlparse(url).netloc,
                }
            )
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns)[:limit]:
            title = clean(entry.findtext("a:title", default="", namespaces=ns))
            link_el = entry.find("a:link", ns)
            link = (link_el.get("href") if link_el is not None else "") or ""
            summary = clean(
                entry.findtext("a:summary", default="", namespaces=ns)
                or entry.findtext("a:content", default="", namespaces=ns)
            )
            if title and link:
                items.append(
                    {
                        "title": title[:220],
                        "url": link,
                        "summary": summary[:900],
                        "published": "",
                        "source": urlparse(url).netloc,
                    }
                )
    return items


def scrape_html_links(url: str, limit: int = 15) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        seen = set()
        for a in soup.select("article a[href], h2 a[href], h3 a[href], .post-title a[href]"):
            href = a.get("href") or ""
            title = clean(a.get_text(" ", strip=True))
            if len(title) < 20 or href in seen:
                continue
            if href.startswith("/"):
                href = f"{urlparse(url).scheme}://{urlparse(url).netloc}{href}"
            if urlparse(href).netloc and urlparse(url).netloc not in urlparse(href).netloc:
                continue
            seen.add(href)
            out.append(
                {
                    "title": title[:220],
                    "url": href,
                    "summary": title,
                    "published": "",
                    "source": urlparse(url).netloc,
                }
            )
            if len(out) >= limit:
                break
        return out
    except Exception as e:
        print(f"  html scrape fail {url}: {e}")
        return []


def detect_level(text: str) -> str:
    t = text.lower()
    if "phd" in t or "doctoral" in t or "ph.d" in t:
        return "PhD"
    if "master" in t or "ms " in t or "m.sc" in t or "mba" in t or "postgraduate" in t:
        return "MS"
    if "undergraduate" in t or "bachelor" in t:
        return "Undergraduate"
    return "MS/PhD"


def detect_region(text: str) -> str:
    t = text.lower()
    pk = ("pakistan", "lahore", "karachi", "islamabad", "rawalpindi", "pkr", "rozee")
    eu = (
        "europe",
        "germany",
        "netherlands",
        "sweden",
        "france",
        "uk",
        "united kingdom",
        "ireland",
        "spain",
        "italy",
        "poland",
        "berlin",
        "amsterdam",
        "remote europe",
    )
    india = ("india", "bangalore", "mumbai", "delhi", "hyderabad", "chennai")
    if any(x in t for x in pk):
        return "Pakistan"
    if any(x in t for x in eu):
        return "Europe"
    if any(x in t for x in india):
        return "India"
    if "remote" in t:
        return "Remote / Worldwide"
    return "Worldwide"


def enrich_copy(kind: str, title: str, summary: str, region: str, level: str) -> dict:
    audience = "students in Pakistan and India applying abroad" if kind == "scholarship" else "candidates in Pakistan, India, and Europe"
    prompt = f"""Write SEO-friendly {kind} page copy targeting searchers in Pakistan and India (and global).

Title: {title}
Region hint: {region}
Level hint: {level}
Source notes: {summary[:500]}

Return ONLY JSON:
{{
  "title": "under 70 chars, include MS or PhD or job role keyword when true",
  "meta_description": "150-160 chars, natural, keyword rich",
  "summary": "3-4 sentences overview",
  "eligibility": ["bullet", "bullet", "bullet"],
  "benefits": ["bullet", "bullet"],
  "how_to_apply": ["step 1", "step 2", "step 3"],
  "faqs": [{{"q": "...", "a": "..."}}, {{"q": "...", "a": "..."}}],
  "keywords": ["primary keyword", "pakistan", "india"]
}}
Rules: do not invent exact deadlines or stipend amounts. Audience: {audience}. JSON only."""
    data = groq_chat_json(
        system="Education and careers SEO editor for Pakistan/India audience. Accurate. JSON only.",
        user=prompt,
        temperature=0.45,
        max_tokens=900,
        timeout=50,
    )
    if data and data.get("summary"):
        data["eligibility"] = list(data.get("eligibility") or [])[:6]
        data["benefits"] = list(data.get("benefits") or [])[:5]
        data["how_to_apply"] = list(data.get("how_to_apply") or [])[:6]
        data["faqs"] = list(data.get("faqs") or [])[:4]
        return data
    return {
        "title": title[:70],
        "meta_description": (summary or title)[:155],
        "summary": summary[:500] or f"{title} — check the official page for deadlines and eligibility.",
        "eligibility": [
            f"Open to applicants seeking {level} opportunities" if kind == "scholarship" else "Relevant degree or experience for the role",
            "Valid passport and academic documents as required",
            "Meet host country language/entry rules",
        ],
        "benefits": ["See official listing for funding or salary details", "International exposure and career growth"],
        "how_to_apply": [
            "Read the official announcement carefully",
            "Prepare CV, transcripts, and recommendation letters",
            "Submit before the deadline on the official portal",
        ],
        "faqs": [
            {"q": "Is this fully funded?", "a": "Funding varies — confirm on the official page before applying."},
            {"q": "Can students from Pakistan or India apply?", "a": "Many listings are open internationally; check nationality rules on the source page."},
        ],
        "keywords": [kind, level.lower(), region.lower(), "pakistan", "india"],
    }


def collect(feeds: list[str], kind: str, max_items: int, html_pages: list[str] | None = None) -> list[dict]:
    raw: list[dict] = []
    seen: set[str] = set()
    for feed in feeds:
        print(f"Feed ({kind}): {feed}")
        for item in parse_rss(feed, limit=30):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            raw.append(item)
    for page in html_pages or []:
        print(f"HTML ({kind}): {page}")
        for item in scrape_html_links(page):
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            raw.append(item)

    def key(it):
        try:
            return parsedate_to_datetime(it.get("published") or "").timestamp()
        except Exception:
            return 0

    raw.sort(key=key, reverse=True)
    out = []
    for i, item in enumerate(raw[:max_items]):
        blob = f"{item['title']} {item.get('summary','')}"
        level = detect_level(blob) if kind == "scholarship" else ""
        region = detect_region(blob)
        # Prefer enriching most items for SEO detail pages
        if os.getenv("GROQ_API_KEY") and (i < 20):
            copy = enrich_copy(kind, item["title"], item.get("summary", ""), region, level or "job")
        else:
            copy = enrich_copy.__wrapped__(kind, item["title"], item.get("summary", ""), region, level or "job") if False else {
                "title": item["title"][:70],
                "meta_description": (item.get("summary") or item["title"])[:155],
                "summary": (item.get("summary") or item["title"])[:500],
                "eligibility": ["See official page"],
                "benefits": ["See official page"],
                "how_to_apply": ["Apply on the official website"],
                "faqs": [],
                "keywords": [kind, region.lower()],
            }
            if os.getenv("GROQ_API_KEY") is None:
                pass

        slug = slugify(copy.get("title") or item["title"])
        out.append(
            {
                "title": copy.get("title") or item["title"],
                "slug": slug,
                "url": item["url"],
                "summary": copy.get("summary") or "",
                "meta_description": copy.get("meta_description") or "",
                "eligibility": copy.get("eligibility") or [],
                "benefits": copy.get("benefits") or [],
                "how_to_apply": copy.get("how_to_apply") or [],
                "faqs": copy.get("faqs") or [],
                "keywords": copy.get("keywords") or [],
                "level": level,
                "region": region,
                "source": item.get("source") or "",
                "published": item.get("published") or "",
                "page": f"p/{slug}.html",
            }
        )
    return out


def render_detail(kind: str, item: dict) -> str:
    title = html.escape(item.get("title") or "Listing")
    meta = html.escape(item.get("meta_description") or item.get("summary") or "")[:160]
    summary = html.escape(item.get("summary") or "")
    region = html.escape(item.get("region") or "")
    level = html.escape(item.get("level") or "")
    source = html.escape(item.get("source") or "")
    official = html.escape(item.get("url") or "#")
    kws = html.escape(", ".join(item.get("keywords") or []))
    back = "../" if kind != "job" else "../"

    def ul(key):
        return "\n".join(f"<li>{html.escape(str(x))}</li>" for x in (item.get(key) or []))

    faq_html = ""
    for f in item.get("faqs") or []:
        faq_html += f"<h3>{html.escape(f.get('q',''))}</h3><p>{html.escape(f.get('a',''))}</p>"

    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": item.get("title"),
        "description": item.get("meta_description") or item.get("summary"),
        "keywords": ", ".join(item.get("keywords") or []),
    }

    label = "Scholarship" if kind == "scholarship" else "Job"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} | {label} | SearchKaro</title>
  <meta name="description" content="{meta}" />
  <meta name="keywords" content="{kws}, fully funded scholarship pakistan, ms phd scholarship india, jobs in pakistan, europe jobs" />
  <link rel="canonical" href="{SITE}/{kind}s/{html.escape(item.get('page') or '')}" />
  <link rel="stylesheet" href="../../assets/style.css" />
  <script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../../index.html">Search<span>Karo</span></a>
      <button class="nav-toggle" aria-label="Menu" onclick="document.body.classList.toggle('nav-open')">☰</button>
      <nav>
        <a href="../../index.html">Home</a>
        <a href="../../scholarships/">Scholarships</a>
        <a href="../../jobs/">Jobs</a>
        <a href="../../universities/">Universities</a>
        <a href="../../courses/">Courses</a>
        <a href="../../blog/">Blog</a>
      </nav>
    </div>
  </header>
  <main class="container article">
    <p class="date">{label} · {region}{f' · {level}' if level else ''}</p>
    <h1>{title}</h1>
    <p class="lead">{summary}</p>
    <div class="detail-box"><h2>Eligibility</h2><ul>{ul('eligibility')}</ul></div>
    <div class="detail-box"><h2>Benefits</h2><ul>{ul('benefits')}</ul></div>
    <div class="detail-box"><h2>How to apply</h2><ol>{ul('how_to_apply')}</ol></div>
    {f'<div class="detail-box"><h2>FAQs</h2>{faq_html}</div>' if faq_html else ''}
    <p class="note">Source: {source}. Always verify on the official page.</p>
    <div class="detail-actions">
      <a class="btn green" href="{official}" target="_blank" rel="noopener nofollow">Official page</a>
      <a class="btn secondary" href="{back}">← All {label.lower()}s</a>
    </div>
  </main>
  <footer class="site-footer"><div class="container"><p>Not affiliated with the host institution. Confirm deadlines officially.</p></div></footer>
</body>
</html>
"""


def write_list_and_details(kind: str, items: list[dict], heading: str, intro: str, keywords: str) -> None:
    folder = ROOT / f"{kind}s"
    pages = folder / "p"
    if pages.exists():
        for old in pages.glob("*.html"):
            old.unlink()
    pages.mkdir(parents=True, exist_ok=True)

    cards = []
    for it in items:
        badge = html.escape(it.get("region") or "")
        level = html.escape(it.get("level") or "")
        cards.append(
            f"""<article class="card list-card">
  <div class="chip-row"><span class="tag">{badge}</span>{f'<span class="tag green">{level}</span>' if level else ''}</div>
  <h2><a href="{html.escape(it.get('page') or '#')}">{html.escape(it.get('title') or '')}</a></h2>
  <p class="excerpt">{html.escape((it.get('summary') or '')[:200])}</p>
  <a class="btn secondary" href="{html.escape(it.get('page') or '#')}">Read full details →</a>
</article>"""
        )
        (pages / f"{it['slug']}.html").write_text(render_detail(kind, it), encoding="utf-8")

    body = "\n".join(cards) or '<p class="empty">Listings refresh on the next daily run.</p>'
    # region filters simple anchors
    filters = ""
    if kind == "job":
        filters = """<div class="toolbar">
      <a class="btn secondary" href="#">All</a>
      <a class="btn secondary" href="?region=Pakistan">Pakistan</a>
      <a class="btn secondary" href="?region=Europe">Europe</a>
      <a class="btn secondary" href="?region=Remote">Remote</a>
    </div>"""

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(heading)} | SearchKaro</title>
  <meta name="description" content="{html.escape(intro[:160])}" />
  <meta name="keywords" content="{html.escape(keywords)}" />
  <link rel="canonical" href="{SITE}/{kind}s/" />
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../index.html">Search<span>Karo</span></a>
      <button class="nav-toggle" aria-label="Menu" onclick="document.body.classList.toggle('nav-open')">☰</button>
      <nav>
        <a href="../index.html">Home</a>
        <a href="../scholarships/" {'class="active"' if kind=='scholarship' else ''}>Scholarships</a>
        <a href="../jobs/" {'class="active"' if kind=='job' else ''}>Jobs</a>
        <a href="../universities/">Universities</a>
        <a href="../courses/">Courses</a>
        <a href="../blog/">Blog</a>
      </nav>
    </div>
  </header>
  <section class="page-head container">
    <h1>{html.escape(heading)}</h1>
    <p class="sub">{html.escape(intro)}</p>
  </section>
  {filters}
  <main class="container post-list" id="list">
{body}
  </main>
  <footer class="site-footer"><div class="container"><p>Aggregated listings. Verify on official sites. Updated daily.</p></div></footer>
  <script>
  (function(){{
    const p = new URLSearchParams(location.search).get('region');
    if(!p) return;
    document.querySelectorAll('.list-card').forEach(card=>{{
      const t = card.innerText.toLowerCase();
      card.style.display = t.includes(p.toLowerCase()) ? '' : 'none';
    }});
  }})();
  </script>
</body>
</html>
"""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    max_s = int(os.getenv("MAX_SCHOLARSHIPS", "30"))
    max_j = int(os.getenv("MAX_JOBS", "30"))

    # Fix enrich fallback without calling __wrapped__
    scholarships_raw = []
    jobs_raw = []

    # inline collect without broken fallback
    def collect_safe(feeds, kind, max_items, html_pages=None):
        raw = []
        seen = set()
        for feed in feeds:
            print(f"Feed ({kind}): {feed}")
            for item in parse_rss(feed, limit=30):
                if item["url"] in seen:
                    continue
                seen.add(item["url"])
                raw.append(item)
        for page in html_pages or []:
            print(f"HTML ({kind}): {page}")
            for item in scrape_html_links(page):
                if item["url"] in seen:
                    continue
                seen.add(item["url"])
                raw.append(item)

        def key(it):
            try:
                return parsedate_to_datetime(it.get("published") or "").timestamp()
            except Exception:
                return 0

        raw.sort(key=key, reverse=True)
        out = []
        for i, item in enumerate(raw[:max_items]):
            blob = f"{item['title']} {item.get('summary','')}"
            level = detect_level(blob) if kind == "scholarship" else ""
            region = detect_region(blob)
            if os.getenv("GROQ_API_KEY") and i < int(os.getenv("GROQ_ENRICH_LIMIT", "18")):
                copy = enrich_copy(kind, item["title"], item.get("summary", ""), region, level or "job")
            else:
                copy = {
                    "title": item["title"][:70],
                    "meta_description": (item.get("summary") or item["title"])[:155],
                    "summary": (item.get("summary") or item["title"])[:500],
                    "eligibility": ["See official page for eligibility"],
                    "benefits": ["See official page for benefits or salary"],
                    "how_to_apply": ["Apply on the official website"],
                    "faqs": [
                        {"q": "Who can apply?", "a": "Check nationality and degree rules on the official listing."}
                    ],
                    "keywords": [kind, region.lower(), "pakistan", "india"],
                }
            slug_base = slugify(copy.get("title") or item["title"])
            slug = slug_base
            n = 2
            while any(x["slug"] == slug for x in out):
                slug = f"{slug_base}-{n}"
                n += 1
            out.append(
                {
                    "title": copy.get("title") or item["title"],
                    "slug": slug,
                    "url": item["url"],
                    "summary": copy.get("summary") or "",
                    "meta_description": copy.get("meta_description") or "",
                    "eligibility": copy.get("eligibility") or [],
                    "benefits": copy.get("benefits") or [],
                    "how_to_apply": copy.get("how_to_apply") or [],
                    "faqs": copy.get("faqs") or [],
                    "keywords": copy.get("keywords") or [],
                    "level": level,
                    "region": region,
                    "source": item.get("source") or "",
                    "published": item.get("published") or "",
                    "page": f"p/{slug}.html",
                }
            )
        return out

    scholarships = collect_safe(SCHOLARSHIP_FEEDS, "scholarship", max_s, SCHOLARSHIP_HTML)
    jobs = collect_safe(JOB_FEEDS, "job", max_j)

    # Ensure some Pakistan/Europe tagged rows exist for SEO sections even if feeds are global
    for j in jobs:
        if j["region"] == "Worldwide" and "remote" in (j.get("title") or "").lower():
            j["region"] = "Remote / Worldwide"

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "scholarships.json").write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "items": scholarships}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (DATA / "jobs.json").write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "items": jobs}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    write_list_and_details(
        "scholarship",
        scholarships,
        "Fully Funded MS & PhD Scholarships (Pakistan & India focused)",
        "Master’s and PhD scholarships with application guides. Built for students searching from Pakistan, India, and worldwide.",
        "fully funded ms scholarship, phd scholarship pakistan, scholarships for indian students, study abroad scholarship",
    )
    write_list_and_details(
        "job",
        jobs,
        "Jobs in Pakistan, Europe & Remote Tech Roles",
        "Software, data, and remote jobs with SEO-friendly descriptions. Filter Pakistan, Europe, or remote.",
        "jobs in pakistan, europe software jobs, remote developer jobs, data science jobs pakistan",
    )
    print(f"Scholarships={len(scholarships)} Jobs={len(jobs)}")


if __name__ == "__main__":
    main()
