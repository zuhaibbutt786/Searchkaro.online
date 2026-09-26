#!/usr/bin/env python3
"""
Fetch Google Trends RSS (PK, US, GB, IN, SA), expand each trend into a
long-form SEO news article via dedicated Groq keys NEW1 / NEW2, keep history.

Takes top NEWS_PER_GEO (default 6) trends from EVERY country.
Writes real news-style articles (not "why this search is trending" templates).

Env:
  NEW1, NEW2          — Groq API keys for news only
  NEWS_PER_GEO        — top N trends per country (default 6)
  NEWS_PER_RUN        — hard max new articles (default 30 = 6 x 5 countries)
  NEWS_MAX_KEEP       — max entries in data/news.json index (default 500)
  SITE_BASE_URL       — canonical site (default https://searchkaro.online)
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "news.json"
NEWS_DIR = ROOT / "news"
PAGES_DIR = NEWS_DIR / "p"

FEEDS = [
    ("PK", "https://trends.google.com/trending/rss?geo=PK"),
    ("IN", "https://trends.google.com/trending/rss?geo=IN"),
    ("US", "https://trends.google.com/trending/rss?geo=US"),
    ("GB", "https://trends.google.com/trending/rss?geo=GB"),
    ("SA", "https://trends.google.com/trending/rss?geo=SA"),
]

HT = "{https://trends.google.com/trending/rss}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODELS = [
    m.strip()
    for m in os.getenv(
        "NEWS_GROQ_MODELS",
        "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b,llama-3.1-8b-instant",
    ).split(",")
    if m.strip()
]


def news_api_keys() -> list[str]:
    keys = []
    for name in ("NEW1", "new1", "NEW2", "new2"):
        v = (os.getenv(name) or "").strip()
        if v and v not in keys:
            keys.append(v)
    shared = (os.getenv("GROQ_API_KEY") or "").strip()
    if shared and shared not in keys:
        keys.append(shared)
    return keys


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:90] or f"news-{int(time.time())}"


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def parse_feed(xml_text: str, geo: str) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  XML parse error {geo}: {e}")
        return items

    for item in root.findall("./channel/item"):
        title_el = item.find("title")
        topic = (title_el.text or "").strip() if title_el is not None else ""
        if len(topic) < 2:
            continue

        traffic_el = item.find(f"{HT}approx_traffic")
        traffic = (traffic_el.text or "").strip() if traffic_el is not None else ""

        pic_el = item.find(f"{HT}picture")
        picture = (pic_el.text or "").strip() if pic_el is not None else ""

        pub_el = item.find("pubDate")
        pub = (pub_el.text or "").strip() if pub_el is not None else ""

        news_links = []
        for ni in item.findall(f"{HT}news_item"):
            nt = ni.find(f"{HT}news_item_title")
            nu = ni.find(f"{HT}news_item_url")
            ns = ni.find(f"{HT}news_item_source")
            news_links.append(
                {
                    "title": (nt.text or "").strip() if nt is not None else "",
                    "url": (nu.text or "").strip() if nu is not None else "",
                    "source": (ns.text or "").strip() if ns is not None else "",
                }
            )

        items.append(
            {
                "topic": topic,
                "geo": geo,
                "traffic": traffic,
                "picture": picture,
                "pub_date": pub,
                "related": news_links[:5],
            }
        )
    return items


def fetch_all_trends() -> list[dict]:
    """Fetch all geos; take top NEWS_PER_GEO from each country."""
    by_geo: dict[str, list[dict]] = {}
    for geo, url in FEEDS:
        print(f"Feed {geo}: {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            print(f"  status={r.status_code} bytes={len(r.content)}")
            if r.status_code != 200:
                by_geo[geo] = []
                continue
            batch = parse_feed(r.text, geo)
            print(f"  items={len(batch)}")
            by_geo[geo] = batch
        except Exception as e:
            print(f"  error: {e}")
            by_geo[geo] = []
        time.sleep(0.6)

    per_geo = int(os.getenv("NEWS_PER_GEO", "6"))
    selected: list[dict] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}
    for geo, _url in FEEDS:
        taken = 0
        for it0 in by_geo.get(geo) or []:
            if taken >= per_geo:
                break
            it = dict(it0)
            key = it["topic"].lower().strip()
            if not key:
                continue
            if key in seen:
                continue
            # Prefer topics that have related publisher headlines (better news articles)
            seen.add(key)
            it["geos"] = [geo]
            selected.append(it)
            taken += 1
        counts[geo] = taken
        print(f"  selected {taken}/{per_geo} for {geo}")

    # Sort so items WITH related headlines are written first
    selected.sort(key=lambda x: 0 if x.get("related") else 1)
    print(f"Selected trends: {len(selected)} by geo={counts} (NEWS_PER_GEO={per_geo})")
    return selected


def _parse_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def groq_news_article(trend: dict, keys: list[str]) -> dict | None:
    related = trend.get("related") or []
    related_txt = "\n".join(
        f"- {r.get('title','')} ({r.get('source','')}) {r.get('url','')}"
        for r in related
        if r.get("title")
    )
    geos = ", ".join(trend.get("geos") or [trend.get("geo", "")])
    topic = trend.get("topic") or "trending topic"
    prompt = f"""You are a professional online news writer. Write a REAL news article in English about this trending topic.

TOPIC: {topic}
TRENDING IN: {geos}
SEARCH INTEREST LABEL: {trend.get('traffic') or 'elevated'}
RELATED HEADLINES FROM PUBLISHERS:
{related_txt or '(no related headlines — write careful general context only, do not invent events)'}

Write like a news website (BBC / Dawn / Al Jazeera style), NOT like a Google Trends explainer.

Return ONLY valid JSON (no markdown fences):
{{
  "title": "Natural news headline under 75 chars — NEVER use the phrase 'why this search is trending'",
  "meta_description": "150-160 character news summary including the topic once",
  "keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"],
  "excerpt": "Two sentences a reader would see under the headline on a news homepage",
  "sections": [
    {{"heading": "Latest developments", "body": "3-5 full paragraphs of news-style reporting based on the related headlines"}},
    {{"heading": "Why it matters", "body": "2-3 paragraphs on impact for readers in {geos}"}},
    {{"heading": "Background", "body": "2-3 paragraphs of context"}},
    {{"heading": "What happens next", "body": "1-2 paragraphs on expected follow-up"}},
    {{"heading": "Summary", "body": "Short bullet-style paragraphs of the main points"}}
  ]
}}

STRICT RULES:
1. Title must sound like a news headline. Forbidden: "why this search is trending", "trending today", "people are searching for".
2. Body total at least 520 English words.
3. Use related headlines as the factual backbone. Paraphrase; do not copy a headline as the title.
4. If the topic is Arabic, Urdu, Hindi or another language, write the ARTICLE IN ENGLISH but keep the original name once and explain what it means.
5. Do not invent quotes, death tolls, scores, or official statements not implied by the related headlines.
6. Neutral tone. Banned words: delve, tapestry, landscape, game-changer, leverage, cutting-edge, underscore.
7. JSON only."""

    last_err = None
    for key in keys:
        for model in MODELS:
            try:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a newsroom reporter for SearchKaro. "
                                "Write factual news articles in clear English. Output JSON only."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.45,
                    "max_tokens": 5000,
                }
                if model.startswith("openai/") or "gpt-oss" in model:
                    payload["response_format"] = {"type": "json_object"}

                resp = requests.post(
                    GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=90,
                )
                if resp.status_code != 200:
                    print(
                        f"  Groq {model} key...{key[-4:]} HTTP {resp.status_code}: {resp.text[:160]}"
                    )
                    last_err = resp.text[:160]
                    continue
                raw = resp.json()["choices"][0]["message"]["content"]
                data = _parse_json(raw)
                if not data or not data.get("title") or not data.get("sections"):
                    print(f"  invalid JSON from {model}")
                    last_err = "invalid json"
                    continue
                title_l = (data.get("title") or "").lower()
                if "why this search is trending" in title_l or title_l.endswith("trending today"):
                    print(f"  rejected template title from {model}: {data.get('title')}")
                    last_err = "template title"
                    continue
                body_words = 0
                for sec in data.get("sections") or []:
                    body_words += word_count(sec.get("body") or "")
                if body_words < 400:
                    print(f"  too short ({body_words} words) from {model}, retry")
                    last_err = "short"
                    continue
                data["_word_count"] = body_words
                print(f"  OK model={model} words={body_words} key...{key[-4:]}")
                return data
            except Exception as e:
                print(f"  error {model}: {e}")
                last_err = str(e)
    print(f"  All news Groq attempts failed: {last_err}")
    return None


def fallback_article(trend: dict) -> dict:
    """News-style fallback from related headlines — never the old Trends template."""
    topic = (trend.get("topic") or "Developing story").strip()
    geos = ", ".join(trend.get("geos") or [trend.get("geo", "")]) or "multiple regions"
    related = [r for r in (trend.get("related") or []) if r.get("title")]
    traffic = trend.get("traffic") or ""

    if related:
        title = related[0]["title"].strip()
        if len(title) > 75:
            title = title[:72].rsplit(" ", 1)[0] + "…"
    else:
        title = f"{topic}: what readers need to know"

    if related:
        bits = []
        for r in related[:5]:
            src = r.get("source") or "Reports"
            bits.append(f"{src} reported: {r.get('title')}.")
        headline_block = " ".join(bits)
    else:
        headline_block = (
            f'Public interest in "{topic}" has increased in {geos}, '
            f"according to Google Trends signals monitored by SearchKaro."
        )

    body1 = (
        f"{headline_block} "
        f'Search activity around "{topic}" is elevated in {geos}'
        f"{f' (interest label: {traffic})' if traffic else ''}. "
        f"Readers typically look up this query when a fresh report, official notice, "
        f"sports result, entertainment release, or local event is circulating on social media and news apps. "
        f"SearchKaro summarizes the publicly linked coverage so visitors can compare outlets instead of relying on a single share. "
        f"Details can change through the day as publishers update stories, so timestamps on source pages matter. "
        f"Where multiple outlets cover the same angle, the core facts usually converge within a few hours."
    )
    body2 = (
        f'For audiences in {geos}, "{topic}" matters because it affects how people plan their day, '
        f"follow a public debate, or check claims they saw in a forward. "
        f"Elevated search volume does not by itself prove a rumor; it only shows curiosity. "
        f"Cross-check at least two independent publishers before sharing sensitive claims. "
        f"Official government, league, or company pages should outrank anonymous screenshots when the topic involves policy, safety, or markets."
    )
    body3 = (
        f'Background on "{topic}" may include earlier coverage in the same region or a recurring seasonal story. '
        f"Sports, entertainment, weather, and politics often reappear on Trends charts when a match, premiere, storm, or vote approaches. "
        f"SearchKaro keeps an archive page for each topic after interest cools so past context remains readable."
    )
    body4 = (
        f'Next steps for readers: open the original publisher links related to "{topic}", '
        f"note the date and location of the reporting desk, and watch for corrections. "
        f"If the story is local to {geos}, local-language outlets may publish details faster than global English wires."
    )
    body5 = (
        f'"{topic}" is drawing search interest in {geos}. '
        f"Related publisher headlines provide the main narrative; Trends numbers are estimates. "
        f"Verify before sharing. SearchKaro also covers scholarships, jobs, free courses, and calculators from the main menu."
    )

    return {
        "title": title,
        "meta_description": (
            f"{topic}: coverage and context for readers in {geos}. "
            f"Summary of related reports and what to verify next."
        )[:160],
        "keywords": [topic, f"{topic} news", geos, "latest updates", "breaking context"],
        "excerpt": (
            f'Coverage linked to "{topic}" is circulating in {geos}. '
            f"Here is a concise news-style briefing based on related publisher headlines."
        ),
        "sections": [
            {"heading": "Latest developments", "body": body1},
            {"heading": "Why it matters", "body": body2},
            {"heading": "Background", "body": body3},
            {"heading": "What happens next", "body": body4},
            {"heading": "Summary", "body": body5},
        ],
        "_word_count": word_count(" ".join([body1, body2, body3, body4, body5])),
    }


def render_article(meta: dict, content: dict) -> str:
    title = html.escape(meta.get("title") or "News")
    desc = html.escape(meta.get("meta_description") or meta.get("excerpt") or "")
    keywords = html.escape(", ".join(meta.get("keywords") or []))
    excerpt = html.escape(meta.get("excerpt") or "")
    date = html.escape(meta.get("date") or "")
    date_pkt = html.escape(meta.get("date_pkt") or "")
    geos = html.escape(", ".join(meta.get("geos") or []))
    traffic = html.escape(meta.get("traffic") or "")
    picture = html.escape(meta.get("picture") or "")
    canonical = f"https://searchkaro.online/news/p/{meta.get('slug')}.html"

    parts = []
    for sec in content.get("sections") or []:
        parts.append(f"<h2>{html.escape(sec.get('heading') or '')}</h2>")
        for para in re.split(r"\n\n+", sec.get("body") or ""):
            if para.strip():
                parts.append(f"<p>{html.escape(para.strip())}</p>")

    related_html = ""
    rel = meta.get("related") or []
    if rel:
        lis = []
        for r in rel:
            if not r.get("title"):
                continue
            src = html.escape(r.get("source") or "Source")
            tt = html.escape(r.get("title") or "")
            lis.append(f"<li><strong>{src}:</strong> {tt}</li>")
        if lis:
            related_html = (
                "<h2>Related headlines (third-party)</h2><ul>"
                + "".join(lis)
                + '</ul><p class="note">Headlines are attributed for context. Verify on the publisher site.</p>'
            )

    img_block = (
        f'<div class="news-hero"><img src="{picture}" alt="" loading="lazy" referrerpolicy="no-referrer" /></div>'
        if picture
        else ""
    )

    schema = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": meta.get("title"),
        "description": meta.get("meta_description") or meta.get("excerpt"),
        "datePublished": meta.get("date"),
        "dateModified": meta.get("date"),
        "mainEntityOfPage": canonical,
        "author": {"@type": "Organization", "name": "SearchKaro"},
        "publisher": {
            "@type": "Organization",
            "name": "SearchKaro",
            "logo": {
                "@type": "ImageObject",
                "url": "https://searchkaro.online/assets/logo.svg",
            },
        },
    }
    if picture:
        schema["image"] = [picture]

    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-GG1Q4ZMG3J"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-GG1Q4ZMG3J');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} | SearchKaro News</title>
  <meta name="description" content="{desc}" />
  <meta name="keywords" content="{keywords}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{html.escape(canonical)}" />
  <meta property="og:type" content="article" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{desc}" />
  <meta property="og:url" content="{html.escape(canonical)}" />
  <meta property="og:site_name" content="SearchKaro" />
  <link rel="icon" href="https://searchkaro.online/assets/favicon.svg" type="image/svg+xml" />
  <link rel="stylesheet" href="../../assets/style.css" />
  <style>
    .article {{ max-width: 820px; margin: 0 auto; padding: 28px 0 56px; }}
    .article h1 {{ color: var(--brand); line-height: 1.25; }}
    .article .lead {{ font-size: 1.08rem; color: #374151; }}
    .article h2 {{ margin-top: 1.6rem; color: var(--brand); font-size: 1.2rem; }}
    .news-hero {{ border-radius: 14px; overflow: hidden; border: 1px solid var(--line); margin: 0 0 16px; }}
    .news-hero img {{ width: 100%; display: block; max-height: 360px; object-fit: cover; }}
    .meta-row {{ color: var(--muted); font-size: 0.92rem; margin-bottom: 12px; }}
    .note {{ color: var(--muted); font-size: 0.88rem; }}
  </style>
  <script type="application/ld+json">{html.escape(json.dumps(schema, ensure_ascii=False))}</script>
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../../index.html">Search<span>Karo</span></a>
      <nav>
        <a href="../../index.html">Home</a>
        <a href="../" class="active">News</a>
        <a href="../../calculators/">Calculators</a>
        <a href="../../courses/">Courses</a>
      </nav>
    </div>
  </header>
  <main class="container article">
    {img_block}
    <p class="meta-row">Published {date_pkt or date} · {geos or '—'}{f' · Traffic {traffic}' if traffic else ''}</p>
    <h1>{title}</h1>
    <p class="lead">{excerpt}</p>
    <div class="content">
{body}
{related_html}
    </div>
    <p><a href="../">← All news</a></p>
  </main>
  <footer class="site-footer"><div class="container"><p>SearchKaro news desk · Based on public Google Trends signals and related publisher headlines · Not affiliated with Google.</p></div></footer>
</body>
</html>
"""


def write_news_index(payload: dict) -> None:
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    items = payload.get("items") or []
    cards = []
    for it in items[:120]:
        title = html.escape(it.get("title") or "")
        excerpt = html.escape(it.get("excerpt") or "")
        date = html.escape(it.get("date_pkt") or it.get("date") or "")
        geos = html.escape(", ".join(it.get("geos") or []))
        href = html.escape(it.get("page") or f"p/{it.get('slug')}.html")
        pic = html.escape(it.get("picture") or "")
        thumb = (
            f'<div class="news-thumb"><img src="{pic}" alt="" loading="lazy" referrerpolicy="no-referrer" /></div>'
            if pic
            else ""
        )
        cards.append(
            f"""<article class="card list-card news-card">
  {thumb}
  <span class="tag">{geos or 'News'}</span>
  <h3><a href="{href}">{title}</a></h3>
  <p class="excerpt">{excerpt}</p>
  <p class="date">{date}</p>
</article>"""
        )

    updated = html.escape(payload.get("updated_at_pkt") or "")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-GG1Q4ZMG3J"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-GG1Q4ZMG3J');</script>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>News — Pakistan, India, US, UK, Saudi | SearchKaro</title>
  <meta name="description" content="Daily news briefings from trending topics in Pakistan, India, United States, United Kingdom, and Saudi Arabia." />
  <link rel="canonical" href="https://searchkaro.online/news/" />
  <link rel="icon" href="https://searchkaro.online/assets/favicon.svg" type="image/svg+xml" />
  <link rel="stylesheet" href="../assets/style.css" />
  <style>
    .news-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
    .news-thumb {{ border-radius: 12px; overflow: hidden; margin-bottom: 10px; border: 1px solid var(--line); }}
    .news-thumb img {{ width: 100%; height: 150px; object-fit: cover; display: block; }}
    .update-banner {{ background: #e8f1f3; border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; margin: 0 0 16px; font-weight: 600; color: var(--brand); }}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../index.html">Search<span>Karo</span></a>
      <nav>
        <a href="../index.html">Home</a>
        <a href="./" class="active">News</a>
        <a href="../calculators/">Calculators</a>
        <a href="../courses/">Courses</a>
        <a href="../blog/">Blog</a>
      </nav>
    </div>
  </header>
  <main class="container">
    <div class="page-head">
      <h1>News</h1>
      <p class="sub">News-style briefings from topics trending in Pakistan, India, US, UK, and Saudi Arabia. Older articles stay published.</p>
    </div>
    <div class="update-banner">Last updated: {updated} · {payload.get('count', 0)} articles · {payload.get('new_in_this_run', 0)} new this run</div>
    <div class="news-grid">
{''.join(cards) or '<p class="empty">News will appear after the daily workflow runs.</p>'}
    </div>
  </main>
  <footer class="site-footer"><div class="container"><p>Not affiliated with Google.</p></div></footer>
</body>
</html>
"""
    (NEWS_DIR / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {NEWS_DIR / 'index.html'}")


def main() -> None:
    keys = news_api_keys()
    if not keys:
        print("ERROR: set GitHub secrets NEW1 and/or NEW2 (Groq keys for news)")
    else:
        print(f"News Groq keys available: {len(keys)}")

    max_new = int(os.getenv("NEWS_PER_RUN", "30"))
    trends = fetch_all_trends()
    print(f"Unique trends collected: {len(trends)}")

    existing = {"items": []}
    if OUT_JSON.exists():
        try:
            existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            existing = {"items": []}

    by_slug = {i.get("slug"): i for i in (existing.get("items") or []) if i.get("slug")}
    existing_topics = {i.get("topic", "").lower() for i in by_slug.values()}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_pkt = datetime.now(ZoneInfo("Asia/Karachi")).strftime("%Y-%m-%d %I:%M %p PKT")

    created = 0
    for trend in trends:
        if created >= max_new:
            break
        topic_key = (trend.get("topic") or "").lower().strip()
        if not topic_key or topic_key in existing_topics:
            continue

        print(
            f"Article {created+1}/{max_new}: {trend.get('topic')} "
            f"({','.join(trend.get('geos') or [])}) related={len(trend.get('related') or [])}"
        )
        content = None
        if keys:
            content = groq_news_article(trend, keys)
        if content is None:
            content = fallback_article(trend)

        title = (content.get("title") or trend["topic"]).strip()
        slug = slugify(title)
        if slug in by_slug:
            slug = f"{slug}-{today.replace('-', '')}"

        meta = {
            "title": title,
            "slug": slug,
            "topic": trend.get("topic"),
            "date": today,
            "date_pkt": today_pkt,
            "excerpt": (content.get("excerpt") or "")[:240],
            "meta_description": (content.get("meta_description") or "")[:160],
            "keywords": list(content.get("keywords") or [])[:12],
            "geos": trend.get("geos") or [trend.get("geo")],
            "traffic": trend.get("traffic") or "",
            "picture": trend.get("picture") or "",
            "related": trend.get("related") or [],
            "word_count": content.get("_word_count") or 0,
            "page": f"p/{slug}.html",
        }

        PAGES_DIR.mkdir(parents=True, exist_ok=True)
        (PAGES_DIR / f"{slug}.html").write_text(
            render_article(meta, content), encoding="utf-8"
        )
        by_slug[slug] = meta
        existing_topics.add(topic_key)
        created += 1
        print(f"  wrote news/p/{slug}.html ({meta['word_count']} words) title={title[:60]}")
        time.sleep(0.8)

    items = list(by_slug.values())
    items.sort(key=lambda x: (x.get("date") or "", x.get("title") or ""), reverse=True)
    max_keep = int(os.getenv("NEWS_MAX_KEEP", "500"))
    if len(items) > max_keep:
        items = items[:max_keep]

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_at_pkt": today_pkt,
        "count": len(items),
        "new_in_this_run": created,
        "sources": [u for _, u in FEEDS],
        "items": items,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Catalog {len(items)} articles → {OUT_JSON} (new={created})")
    write_news_index(payload)


if __name__ == "__main__":
    main()
