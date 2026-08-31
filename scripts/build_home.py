#!/usr/bin/env python3
"""Rebuild index.html with recent articles, courses, scholarships, jobs + SEO/AEO."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def main() -> None:
    posts = load(ROOT / "data" / "posts.json", {"posts": []}).get("posts") or []
    courses = load(ROOT / "data" / "courses.json", {"courses": []}).get("courses") or []
    scholarships = load(ROOT / "data" / "scholarships.json", {"items": []}).get("items") or []
    jobs = load(ROOT / "data" / "jobs.json", {"items": []}).get("items") or []

    posts = sorted(posts, key=lambda p: p.get("date", ""), reverse=True)[:6]
    courses = courses[:6]
    scholarships = scholarships[:5]
    jobs = jobs[:5]

    post_cards = []
    for p in posts:
        post_cards.append(
            f"""<article class="card list-card">
  <span class="tag">Article</span>
  <h3><a href="blog/{html.escape(p.get('slug',''))}.html">{html.escape(p.get('title',''))}</a></h3>
  <p class="excerpt">{html.escape((p.get('excerpt') or '')[:160])}</p>
  <p class="date">{html.escape(p.get('date') or '')}</p>
</article>"""
        )

    course_cards = []
    for c in courses:
        img = html.escape(c.get("image") or "")
        title = html.escape(c.get("title") or "")
        page = html.escape(c.get("page") or f"p/{c.get('slug','')}.html")
        thumb = f'<div class="course-thumb"><span class="badge-free">100% OFF</span><img src="{img}" alt="" loading="lazy" referrerpolicy="no-referrer" /></div>' if img else ""
        course_cards.append(
            f"""<article class="course-card">
  {thumb}
  <div class="course-body">
    <h3>{title}</h3>
    <p class="course-meta">{html.escape(c.get('language') or 'English')}<span class="dot">·</span>{html.escape(c.get('category') or '')}</p>
    <a class="btn green block" href="courses/{page}">View coupon</a>
  </div>
</article>"""
        )

    sch_items = "".join(
        f'<li><a href="{html.escape(s.get("url") or "#")}" target="_blank" rel="noopener nofollow">{html.escape(s.get("title") or "")}</a></li>'
        for s in scholarships
    ) or "<li>Scholarship feed updates daily.</li>"

    job_items = "".join(
        f'<li><a href="{html.escape(j.get("url") or "#")}" target="_blank" rel="noopener nofollow">{html.escape(j.get("title") or "")}</a></li>'
        for j in jobs
    ) or "<li>Job feed updates daily.</li>"

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "LearnWithZuhaib",
        "url": "https://zuhaibbutt786.github.io/tech-blog-courses/",
        "description": "Free Udemy coupons, AI ML tutorials, Stack Overflow style answers, MS PhD scholarships, and remote tech jobs.",
        "potentialAction": {
            "@type": "SearchAction",
            "target": "https://zuhaibbutt786.github.io/tech-blog-courses/blog/",
            "query-input": "required name=search_term_string",
        },
    }

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LearnWithZuhaib — Free Udemy Courses, AI Blog, Scholarships & Tech Jobs</title>
  <meta name="description" content="Daily free Udemy course coupons, practical AI/ML coding articles, Stack Overflow style answers, MS & PhD scholarships, and remote developer jobs. Learn with Zuhaib." />
  <meta name="keywords" content="free udemy courses, udemy coupon, AI tutorial, machine learning blog, stack overflow answers, MS scholarship, PhD scholarship, remote developer jobs, MLOps, LLM, learn programming" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="https://zuhaibbutt786.github.io/tech-blog-courses/" />
  <meta property="og:title" content="LearnWithZuhaib — Free Courses, Tech Blog, Scholarships" />
  <meta property="og:description" content="Free Udemy coupons, AI coding guides, scholarships, and tech jobs updated daily." />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://zuhaibbutt786.github.io/tech-blog-courses/" />
  <link rel="stylesheet" href="assets/style.css" />
  <script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="index.html">Learn<span>With</span>Zuhaib</a>
      <nav>
        <a href="index.html" class="active">Home</a>
        <a href="blog/">Tech Blog</a>
        <a href="courses/">Free Courses</a>
        <a href="scholarships/">Scholarships</a>
        <a href="jobs/">Jobs</a>
        <a href="about.html">About</a>
      </nav>
    </div>
  </header>

  <section class="hero">
    <div class="container">
      <p class="eyebrow">Updated {updated} · Built for learners & job seekers</p>
      <h1>Free Udemy coupons, AI coding guides, scholarships & tech jobs</h1>
      <p class="lead">
        High-intent learning hub: 100% off Udemy courses, practical machine learning articles,
        answers to questions developers actually ask, plus MS/PhD scholarships and remote jobs.
      </p>
      <div class="hero-actions">
        <a class="btn green" href="courses/">New free course coupons</a>
        <a class="btn primary" href="blog/">Latest tech articles</a>
        <a class="btn secondary" href="scholarships/">MS & PhD scholarships</a>
      </div>
    </div>
  </section>

  <section class="container section">
    <div class="section-head">
      <h2>Most recent articles</h2>
      <a href="blog/">All articles →</a>
    </div>
    <div class="home-grid">
      {''.join(post_cards) or '<p class="empty">Articles publish daily.</p>'}
    </div>
  </section>

  <section class="container section">
    <div class="section-head">
      <h2>New free Udemy course coupons</h2>
      <a href="courses/">All coupons →</a>
    </div>
    <div class="course-grid">
      {''.join(course_cards) or '<p class="empty">Courses refresh every morning.</p>'}
    </div>
  </section>

  <section class="container section dual">
    <div class="card">
      <div class="section-head">
        <h2>MS & PhD scholarships</h2>
        <a href="scholarships/">View all →</a>
      </div>
      <ul class="link-list">{sch_items}</ul>
    </div>
    <div class="card">
      <div class="section-head">
        <h2>Tech & remote jobs</h2>
        <a href="jobs/">View all →</a>
      </div>
      <ul class="link-list">{job_items}</ul>
    </div>
  </section>

  <section class="container section faq-home">
    <h2>Common questions</h2>
    <details open><summary>Are the Udemy courses really free?</summary><p>Listings include coupon links. Always confirm the price shows <strong>$0</strong> on Udemy before checkout — coupons can expire.</p></details>
    <details><summary>What topics does the tech blog cover?</summary><p>AI, machine learning, LLMs, MLOps, coding fixes inspired by real developer questions, and production engineering tips.</p></details>
    <details><summary>Where do scholarships and jobs come from?</summary><p>Public RSS feeds from education and job boards. Always apply on the official source page.</p></details>
  </section>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div>
        <strong>LearnWithZuhaib</strong>
        <p class="muted">Practical tech learning, free courses, scholarships, and jobs.</p>
      </div>
      <div>
        <a href="about.html">About</a><br />
        <a href="contact.html">Contact</a><br />
        <a href="privacy.html">Privacy Policy</a>
      </div>
      <div>
        <a href="blog/">Tech Blog</a><br />
        <a href="courses/">Free Courses</a><br />
        <a href="scholarships/">Scholarships</a> · <a href="jobs/">Jobs</a>
      </div>
    </div>
    <div class="container"><p class="muted">© <span id="y"></span> LearnWithZuhaib · Not affiliated with Udemy or Stack Overflow.</p></div>
  </footer>
  <script>document.getElementById('y').textContent = new Date().getFullYear()</script>
</body>
</html>
"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print("Wrote index.html")


if __name__ == "__main__":
    main()
