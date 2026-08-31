#!/usr/bin/env python3
"""Generate 2 AI/ML blog posts per day with Groq and write static HTML + index."""

from __future__ import annotations

import html
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
POSTS_JSON = ROOT / "data" / "posts.json"
BLOG_DIR = ROOT / "blog"
POSTS_PER_RUN = int(os.getenv("POSTS_PER_RUN", "2"))

TOPICS = [
    "KV cache and LLM latency",
    "LoRA fine-tuning practical tips",
    "RAG chunking that retrieves",
    "Quantization without quality collapse",
    "vLLM batching for throughput",
    "Evaluating LLM apps beyond accuracy",
    "Prompt versioning in production",
    "Vector search HNSW vs IVF",
    "Structured outputs and tool calling",
    "MLOps metrics that matter",
    "Computer vision deployment pitfalls",
    "Speech models Whisper decoding tips",
    "Feature stores for real-time ML",
    "Cost control for LLM APIs",
    "Reproducible CUDA training seeds",
]


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s[:80] or f"post-{int(datetime.now().timestamp())}"


def load_index() -> dict:
    if POSTS_JSON.exists():
        try:
            return json.loads(POSTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"posts": []}


def generate_with_groq(topic: str) -> dict | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    prompt = f"""Write a practical tech blog post for AI/ML engineers.

Topic: {topic}

Return ONLY JSON:
{{
  "title": "under 70 chars, specific",
  "excerpt": "1-2 sentences",
  "sections": [
    {{"heading": "...", "body": "2-4 short paragraphs, concrete"}},
    {{"heading": "...", "body": "...", "code": "optional python 3-8 lines"}}
  ],
  "takeaway": "one line"
}}

Rules:
- 4 to 6 sections
- coding-side insights, not fluff
- at least one section with real Python code
- ban: leverage, game-changer, delve, cutting-edge
- JSON only"""
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "Senior AI engineer blogger. JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
                "max_tokens": 2500,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            print("Groq error", resp.status_code, resp.text[:200])
            return None
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        return json.loads(raw)
    except Exception as e:
        print("generate failed", e)
        return None


def fallback_post(topic: str) -> dict:
    return {
        "title": f"Practical notes on {topic}",
        "excerpt": f"Engineering checklist and code patterns for {topic}.",
        "sections": [
            {
                "heading": "What to measure first",
                "body": "Log latency percentiles, token counts, and failure modes before changing models. Averages hide the pain users feel.",
            },
            {
                "heading": "Minimal code check",
                "body": "Start with a tiny reproducible script so every experiment is comparable.",
                "code": "import time\nt0 = time.time()\n# run inference\nprint('seconds', time.time() - t0)",
            },
            {
                "heading": "Ship checklist",
                "body": "Pin versions, add eval gates, and name an owner for the first week in production.",
            },
        ],
        "takeaway": "Measure, baseline, then optimize the bottleneck you can prove.",
    }


def render_html(meta: dict, content: dict) -> str:
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

    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(meta['title'])} | LearnWithZuhaib</title>
  <meta name="description" content="{html.escape(meta.get('excerpt',''))}" />
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../index.html">LearnWithZuhaib</a>
      <nav>
        <a href="../index.html">Home</a>
        <a href="./" class="active">Tech Blog</a>
        <a href="../courses/">Free Udemy Courses</a>
      </nav>
    </div>
  </header>
  <main class="container article">
    <p class="date">{html.escape(meta.get('date',''))}</p>
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
    index = load_index()
    existing_slugs = {p.get("slug") for p in index.get("posts") or []}
    existing_titles = {p.get("title", "").lower() for p in index.get("posts") or []}

    topics = random.sample(TOPICS, k=min(POSTS_PER_RUN + 3, len(TOPICS)))
    created = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for topic in topics:
        if created >= POSTS_PER_RUN:
            break
        content = generate_with_groq(topic) or fallback_post(topic)
        title = (content.get("title") or topic).strip()
        if title.lower() in existing_titles:
            continue
        slug = slugify(title)
        if slug in existing_slugs:
            slug = f"{slug}-{today.replace('-', '')}"
        meta = {
            "title": title,
            "slug": slug,
            "date": today,
            "excerpt": (content.get("excerpt") or "")[:220],
        }
        html_path = BLOG_DIR / f"{slug}.html"
        html_path.write_text(render_html(meta, content), encoding="utf-8")
        index.setdefault("posts", []).append(meta)
        existing_slugs.add(slug)
        existing_titles.add(title.lower())
        created += 1
        print(f"Wrote {html_path.name}")

    # keep newest 200 in index
    posts = sorted(index.get("posts") or [], key=lambda p: p.get("date", ""), reverse=True)[:200]
    POSTS_JSON.write_text(json.dumps({"posts": posts}, indent=2), encoding="utf-8")
    print(f"Created {created} posts")


if __name__ == "__main__":
    main()
