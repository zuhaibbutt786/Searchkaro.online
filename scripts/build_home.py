#!/usr/bin/env python3
"""Rebuild index.html — SearchKaro hub for PK/IN + world traffic."""

from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = os.getenv("SITE_BASE_URL", "https://searchkaro.online").rstrip("/")


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
    scholarships = scholarships[:6]
    jobs = jobs[:6]

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
        thumb = (
            f'<div class="course-thumb"><span class="badge-free">100% OFF</span>'
            f'<img src="{img}" alt="" loading="lazy" referrerpolicy="no-referrer" /></div>'
            if img
            else ""
        )
        course_cards.append(
            f"""<article class="course-card">{thumb}<div class="course-body">
    <h3>{title}</h3>
    <p class="course-meta">{html.escape(c.get('language') or 'English')}<span class="dot">·</span>{html.escape(c.get('category') or '')}</p>
    <a class="btn green block" href="courses/{page}">View coupon</a></div></article>"""
        )

    sch_items = "".join(
        f'<li><a href="scholarships/{html.escape(s.get("page") or "")}">{html.escape(s.get("title") or "")}</a></li>'
        for s in scholarships
    ) or "<li>Scholarship pages update daily.</li>"

    job_items = "".join(
        f'<li><a href="jobs/{html.escape(j.get("page") or "")}">{html.escape(j.get("title") or "")}</a>'
        f' <span class="muted">({html.escape(j.get("region") or "")})</span></li>'
        for j in jobs
    ) or "<li>Job pages update daily.</li>"

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "SearchKaro",
        "url": f"{SITE}/",
        "description": "Fully funded MS PhD scholarships, jobs in Pakistan and Europe, HEC university rankings, free Udemy courses, and tech guides for students in Pakistan and India.",
    }

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SearchKaro — Scholarships, Jobs Pakistan & Europe, Universities, Free Courses</title>
  <meta name="description" content="Fully funded MS & PhD scholarships, jobs in Pakistan and Europe, HEC & world university rankings, free Udemy coupons, and tech articles for students in Pakistan, India, and worldwide." />
  <meta name="keywords" content="fully funded ms scholarship, phd scholarship pakistan, scholarships for indian students, jobs in pakistan, europe software jobs, hec ranking, best universities pakistan, free udemy courses, study abroad" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{SITE}/" />
  <meta property="og:title" content="SearchKaro — Scholarships, Jobs, Universities" />
  <meta property="og:description" content="MS/PhD scholarships, Pakistan & Europe jobs, university rankings, free courses." />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="{SITE}/" />
  <link rel="stylesheet" href="assets/style.css" />
  <script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="index.html">Search<span>Karo</span></a>
      <button class="nav-toggle" aria-label="Menu" onclick="document.body.classList.toggle('nav-open')">☰</button>
      <nav>
        <a href="index.html" class="active">Home</a>
        <a href="scholarships/">Scholarships</a>
        <a href="jobs/">Jobs</a>
        <a href="universities/">Universities</a>
        <a href="courses/">Courses</a>
        <a href="blog/">Blog</a>
      </nav>
    </div>
  </header>

  <section class="hero">
    <div class="container">
      <p class="eyebrow">Updated {updated} · Pakistan · India · Worldwide</p>
      <h1>Scholarships, jobs, university rankings & free courses</h1>
      <p class="lead">
        Search high-intent opportunities: fully funded <strong>MS & PhD scholarships</strong>,
        <strong>jobs in Pakistan & Europe</strong>, <strong>HEC and world university lists</strong>,
        and free Udemy coupons — written for mobile and desktop.
      </p>
      <div class="hero-actions">
        <a class="btn green" href="scholarships/">MS & PhD scholarships</a>
        <a class="btn primary" href="jobs/">Jobs Pakistan / Europe</a>
        <a class="btn secondary" href="universities/">University rankings</a>
        <a class="btn secondary" href="courses/">Free course coupons</a>
      </div>
    </div>
  </section>

  <section class="container section dual">
    <div class="card">
      <div class="section-head"><h2>Latest scholarships</h2><a href="scholarships/">All →</a></div>
      <ul class="link-list">{sch_items}</ul>
    </div>
    <div class="card">
      <div class="section-head"><h2>Latest jobs</h2><a href="jobs/">All →</a></div>
      <ul class="link-list">{job_items}</ul>
    </div>
  </section>

  <section class="container section">
    <div class="section-head"><h2>Universities</h2><a href="universities/">Explore →</a></div>
    <div class="home-grid">
      <a class="card mini" href="universities/pakistan.html"><h3>Pakistan HEC list</h3><p>NUST, UET, LUMS, QAU and more</p></a>
      <a class="card mini" href="universities/medical.html"><h3>Medical universities</h3><p>By country including PK & India</p></a>
      <a class="card mini" href="universities/engineering.html"><h3>Engineering universities</h3><p>IIT, NUST, MIT-style references</p></a>
      <a class="card mini" href="universities/law.html"><h3>Law universities</h3><p>Pakistan, India, UK, US</p></a>
    </div>
  </section>

  <section class="container section">
    <div class="section-head"><h2>New free Udemy coupons</h2><a href="courses/">All →</a></div>
    <div class="course-grid">{''.join(course_cards) or '<p class="empty">Courses refresh daily.</p>'}</div>
  </section>

  <section class="container section">
    <div class="section-head"><h2>Recent articles</h2><a href="blog/">All →</a></div>
    <div class="home-grid">{''.join(post_cards) or '<p class="empty">Articles publish daily.</p>'}</div>
  </section>

  <section class="container section faq-home">
    <h2>People also ask</h2>
    <details open><summary>Where can I find fully funded MS and PhD scholarships?</summary><p>Open our <a href="scholarships/">scholarships</a> section. Each listing has eligibility, steps, and a link to the official page.</p></details>
    <details><summary>How do I find jobs in Pakistan or Europe?</summary><p>Use the <a href="jobs/">jobs</a> page filters for Pakistan, Europe, or remote roles.</p></details>
    <details><summary>What is HEC ranking?</summary><p>HEC publishes category rankings for Pakistani universities. See our <a href="universities/pakistan.html">Pakistan universities</a> guide and verify on hec.gov.pk.</p></details>
  </section>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><strong>SearchKaro</strong><p class="muted">Scholarships, jobs, universities & free learning for Pakistan, India, and the world.</p></div>
      <div><a href="about.html">About</a><br /><a href="contact.html">Contact</a><br /><a href="privacy.html">Privacy</a></div>
      <div><a href="scholarships/">Scholarships</a><br /><a href="jobs/">Jobs</a><br /><a href="universities/">Universities</a></div>
    </div>
    <div class="container"><p class="muted">© <span id="y"></span> SearchKaro · Verify all deadlines on official sites.</p></div>
  </footer>
  <script>document.getElementById('y').textContent = new Date().getFullYear()</script>
</body>
</html>
"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print("Wrote index.html")


if __name__ == "__main__":
    main()
