#!/usr/bin/env python3
"""Turn high-view Stack Overflow questions into practical answer blog posts."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from groq_client import groq_chat_json

ROOT = Path(__file__).resolve().parent.parent
POSTS_JSON = ROOT / "data" / "posts.json"
BLOG_DIR = ROOT / "blog"
SO_SEEN = ROOT / "data" / "so_seen.json"

API = "https://api.stackexchange.com/2.3/questions"
SITE = "stackoverflow"
HEADERS = {"User-Agent": "LearnWithZuhaibBot/1.0 (educational blog)"}
MAX_POSTS = int(os.getenv("SO_POSTS_PER_RUN", "4"))


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:90] or f"so-{int(datetime.now().timestamp())}"


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def fetch_questions(sort: str, pagesize: int = 30) -> list[dict]:
    params = {
        "order": "desc",
        "sort": sort,
        "site": SITE,
        "pagesize": pagesize,
        "filter": "withbody",
    }
    r = requests.get(API, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    items = r.json().get("items") or []
    # rank by views locally
    items.sort(key=lambda x: x.get("view_count") or 0, reverse=True)
    return items[:10]


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def answer_with_groq(q: dict) -> dict | None:
    title = q.get("title") or "Programming question"
    body = strip_html(q.get("body") or "")[:2500]
    tags = ", ".join(q.get("tags") or [])
    prompt = f"""Write an original practical blog answer to this Stack Overflow-style question.
Do NOT copy the question or any answers verbatim. Paraphrase and teach.

Question title: {title}
Tags: {tags}
Question summary: {body[:1800]}

Return ONLY JSON:
{{
  "title": "SEO title under 70 chars, includes key tech term",
  "excerpt": "1-2 sentences with primary keyword",
  "sections": [
    {{"heading": "...", "body": "2-4 short paragraphs"}},
    {{"heading": "...", "body": "...", "code": "optional short code"}}
  ],
  "takeaway": "one line",
  "faq": [
    {{"q": "related question people ask", "a": "short answer"}},
    {{"q": "...", "a": "..."}}
  ]
}}
Rules: 4-6 sections, coding-focused, ban fluff words, JSON only."""
    data = groq_chat_json(
        system="Senior engineer writing SEO/AEO educational posts. JSON only. Original wording.",
        user=prompt,
        temperature=0.55,
        max_tokens=2800,
        timeout=70,
    )
    if not data or not data.get("title") or not data.get("sections"):
        return None
    return data


def fallback_answer(q: dict) -> dict:
    title = q.get("title") or "Common programming question"
    tags = ", ".join((q.get("tags") or [])[:4]) or "programming"
    return {
        "title": f"How to solve: {title[:55]}",
        "excerpt": f"A practical walkthrough for a common {tags} problem developers search for.",
        "sections": [
            {
                "heading": "What the problem usually means",
                "body": "Most reports like this come from a mismatch between expected types, versions, or configuration. Reproduce with a minimal example before changing production code.",
            },
            {
                "heading": "Checklist that fixes most cases",
                "body": "Confirm versions, isolate the failing unit, read the full stack trace, and compare a known-good sample. Avoid random package upgrades.",
            },
            {
                "heading": "Minimal debug snippet",
                "body": "Log inputs and environment once, then iterate.",
                "code": "import sys\nprint(sys.version)\n# print key variables and the exact error",
            },
        ],
        "takeaway": "Reproduce small, fix the root cause, then harden tests.",
        "faq": [
            {"q": "Why do similar errors appear after upgrades?", "a": "Breaking changes in libraries often change defaults or type signatures."},
            {"q": "Should I copy code from forums blindly?", "a": "No — adapt the pattern and test against your versions."},
        ],
    }


def render_html(meta: dict, content: dict, source_url: str) -> str:
    parts = []
    for sec in content.get("sections") or []:
        parts.append(f"<h2>{html.escape(sec.get('heading',''))}</h2>")
        for para in (sec.get("body") or "").split("\n\n"):
            if para.strip():
                parts.append(f"<p>{html.escape(para.strip())}</p>")
        code = (sec.get("code") or "").strip()
        if code:
            parts.append(f"<pre><code>{html.escape(code)}</code></pre>")
    if content.get("takeaway"):
        parts.append(f"<p><strong>Takeaway:</strong> {html.escape(content['takeaway'])}</p>")
    faq = content.get("faq") or []
    if faq:
        parts.append("<h2>People also ask</h2>")
        for item in faq[:5]:
            parts.append(f"<h3>{html.escape(item.get('q',''))}</h3>")
            parts.append(f"<p>{html.escape(item.get('a',''))}</p>")
    if source_url:
        parts.append(
            f'<p class="note">Inspired by a public discussion on '
            f'<a href="{html.escape(source_url)}" rel="noopener nofollow">Stack Overflow</a>. '
            f"This article is an original explanation for learners.</p>"
        )

    # FAQPage schema for AEO
    faq_schema = ""
    if faq:
        entities = []
        for item in faq[:5]:
            entities.append(
                {
                    "@type": "Question",
                    "name": item.get("q", ""),
                    "acceptedAnswer": {"@type": "Answer", "text": item.get("a", "")},
                }
            )
        faq_schema = (
            '<script type="application/ld+json">'
            + html.escape(
                json.dumps(
                    {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities},
                    ensure_ascii=False,
                ),
                quote=False,
            )
            + "</script>"
        )
        # fix: shouldn't html.escape JSON in script - use raw
        faq_schema = (
            '<script type="application/ld+json">'
            + json.dumps(
                {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": entities},
                ensure_ascii=False,
            )
            + "</script>"
        )

    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(meta['title'])} | LearnWithZuhaib</title>
  <meta name="description" content="{html.escape(meta.get('excerpt',''))}" />
  <meta name="keywords" content="programming help, stack overflow answers, coding tutorial, {html.escape(','.join(meta.get('tags') or []))}" />
  <link rel="canonical" href="https://zuhaibbutt786.github.io/tech-blog-courses/blog/{html.escape(meta['slug'])}.html" />
  <link rel="stylesheet" href="../assets/style.css" />
  {faq_schema}
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../index.html">Learn<span>With</span>Zuhaib</a>
      <nav>
        <a href="../index.html">Home</a>
        <a href="./" class="active">Tech Blog</a>
        <a href="../courses/">Free Courses</a>
        <a href="../scholarships/">Scholarships</a>
        <a href="../jobs/">Jobs</a>
      </nav>
    </div>
  </header>
  <main class="container article">
    <p class="date">{html.escape(meta.get('date',''))} · Q&A guide</p>
    <h1>{html.escape(meta['title'])}</h1>
    <p class="lead">{html.escape(meta.get('excerpt',''))}</p>
    <div class="content">
{body}
    </div>
    <p><a href="./">← All posts</a></p>
  </main>
</body>
</html>
"""


def main() -> None:
    seen = set(load_json(SO_SEEN, {"ids": []}).get("ids") or [])
    index = load_json(POSTS_JSON, {"posts": []})
    existing_slugs = {p.get("slug") for p in index.get("posts") or []}

    pool: list[dict] = []
    for sort in ("creation", "activity"):
        try:
            batch = fetch_questions(sort)
            print(f"SO {sort}: {len(batch)} top-by-views")
            pool.extend(batch)
        except Exception as e:
            print(f"SO fetch {sort} failed: {e}")

    # dedupe by question_id, prefer higher views
    by_id: dict[int, dict] = {}
    for q in pool:
        qid = q.get("question_id")
        if not qid:
            continue
        if qid not in by_id or (q.get("view_count") or 0) > (by_id[qid].get("view_count") or 0):
            by_id[qid] = q
    ranked = sorted(by_id.values(), key=lambda x: x.get("view_count") or 0, reverse=True)

    created = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    BLOG_DIR.mkdir(parents=True, exist_ok=True)

    for q in ranked:
        if created >= MAX_POSTS:
            break
        qid = q.get("question_id")
        if qid in seen:
            continue
        content = answer_with_groq(q) or fallback_answer(q)
        title = (content.get("title") or q.get("title") or "Programming guide").strip()
        slug = slugify(title)
        if slug in existing_slugs:
            slug = f"{slug}-{qid}"
        meta = {
            "title": title,
            "slug": slug,
            "date": today,
            "excerpt": (content.get("excerpt") or "")[:220],
            "source": "stackoverflow",
            "tags": q.get("tags") or [],
            "views": q.get("view_count") or 0,
        }
        path = BLOG_DIR / f"{slug}.html"
        path.write_text(
            render_html(meta, content, q.get("link") or ""),
            encoding="utf-8",
        )
        index.setdefault("posts", []).append(
            {
                "title": meta["title"],
                "slug": slug,
                "date": today,
                "excerpt": meta["excerpt"],
                "source": "stackoverflow",
            }
        )
        seen.add(qid)
        existing_slugs.add(slug)
        created += 1
        print(f"SO post: {slug} (views={meta['views']})")

    posts = sorted(index.get("posts") or [], key=lambda p: p.get("date", ""), reverse=True)[:300]
    POSTS_JSON.write_text(json.dumps({"posts": posts}, indent=2), encoding="utf-8")
    SO_SEEN.write_text(json.dumps({"ids": sorted(seen)[-2000:]}, indent=2), encoding="utf-8")
    print(f"Created {created} Stack Overflow answer posts")


if __name__ == "__main__":
    main()
