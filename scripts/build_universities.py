#!/usr/bin/env python3
"""Build universities section: Pakistan HEC-style lists, field pages, country samples."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "universities"
DATA = ROOT / "data" / "universities.json"
SITE = "https://searchkaro.online"

# Curated reference lists for SEO structure (not live scraped paywalled rankings).
# Labels are commonly cited public institutions; users should verify latest HEC/THE pages.

PAKISTAN_HEC_GENERAL = [
    {"name": "National University of Sciences & Technology (NUST)", "city": "Islamabad", "hec_note": "Top general / engineering focused"},
    {"name": "Quaid-i-Azam University (QAU)", "city": "Islamabad", "hec_note": "Strong research & natural sciences"},
    {"name": "University of the Punjab", "city": "Lahore", "hec_note": "Large comprehensive university"},
    {"name": "University of Karachi", "city": "Karachi", "hec_note": "Major public university"},
    {"name": "COMSATS University Islamabad", "city": "Islamabad", "hec_note": "IT & engineering strength"},
    {"name": "University of Engineering & Technology (UET) Lahore", "city": "Lahore", "hec_note": "Premier engineering"},
    {"name": "Lahore University of Management Sciences (LUMS)", "city": "Lahore", "hec_note": "Business, CS, social sciences"},
    {"name": "Aga Khan University", "city": "Karachi", "hec_note": "Medical & health sciences"},
    {"name": "Pakistan Institute of Engineering and Applied Sciences (PIEAS)", "city": "Islamabad", "hec_note": "Engineering & applied sciences"},
    {"name": "Institute of Business Administration (IBA)", "city": "Karachi", "hec_note": "Business & CS"},
    {"name": "University of Agriculture Faisalabad", "city": "Faisalabad", "hec_note": "Agriculture & allied"},
    {"name": "Bahria University", "city": "Islamabad", "hec_note": "Multi-campus public sector"},
]

BY_FIELD = {
    "medical": {
        "title": "Top Medical Universities",
        "keywords": "best medical universities, mbbs ranking, medical colleges pakistan india",
        "countries": {
            "Pakistan": ["Aga Khan University", "King Edward Medical University", "Dow University of Health Sciences", "Rawalpindi Medical University"],
            "India": ["AIIMS New Delhi", "Christian Medical College Vellore", "AFMC Pune", "JIPMER Puducherry"],
            "United Kingdom": ["University of Oxford (Medical Sciences)", "University of Cambridge", "UCL", "Imperial College London"],
            "United States": ["Harvard University", "Johns Hopkins University", "Stanford University", "University of California San Francisco"],
            "Germany": ["Charité – Universitätsmedizin Berlin", "Heidelberg University", "LMU Munich"],
        },
    },
    "engineering": {
        "title": "Top Engineering Universities",
        "keywords": "best engineering universities, NUST ranking, IIT ranking, engineering abroad",
        "countries": {
            "Pakistan": ["NUST", "UET Lahore", "PIEAS", "GIK Institute"],
            "India": ["IIT Bombay", "IIT Delhi", "IIT Madras", "IIT Kanpur"],
            "United States": ["MIT", "Stanford University", "UC Berkeley", "Caltech"],
            "United Kingdom": ["Imperial College London", "University of Cambridge", "University of Oxford", "University of Manchester"],
            "Germany": ["TU Munich", "RWTH Aachen", "University of Stuttgart"],
        },
    },
    "arts": {
        "title": "Top Arts & Humanities Universities",
        "keywords": "arts universities ranking, fine arts colleges, humanities ranking",
        "countries": {
            "Pakistan": ["National College of Arts", "University of the Punjab", "Beaconhouse National University"],
            "India": ["JNU", "University of Delhi", "Jamia Millia Islamia"],
            "United Kingdom": ["University of Oxford", "University of Cambridge", "UCL", "University of Edinburgh"],
            "United States": ["Harvard University", "Yale University", "Columbia University"],
        },
    },
    "law": {
        "title": "Top Law Universities",
        "keywords": "best law universities, LLB ranking, law schools pakistan india",
        "countries": {
            "Pakistan": ["LUMS Shaikh Ahmad Hassan School of Law", "University of Punjab Law College", "International Islamic University"],
            "India": ["NLSIU Bangalore", "NALSAR Hyderabad", "NLU Delhi"],
            "United Kingdom": ["University of Oxford", "University of Cambridge", "LSE", "UCL"],
            "United States": ["Yale Law School", "Harvard Law School", "Stanford Law School"],
        },
    },
    "allied-sciences": {
        "title": "Allied Health & Applied Sciences Universities",
        "keywords": "allied health sciences universities, nursing physiotherapy ranking, applied sciences",
        "countries": {
            "Pakistan": ["University of Health Sciences Lahore", "Dow University", "SHIFA Tameer-e-Millat University"],
            "India": ["Manipal Academy of Higher Education", "SRM Institute", "Amity University"],
            "United Kingdom": ["King's College London", "University of Manchester", "University of Southampton"],
            "Australia": ["University of Sydney", "Monash University", "University of Melbourne"],
        },
    },
}

TIMES_REF = [
    {"name": "University of Oxford", "country": "UK", "note": "Frequently top in THE World Rankings"},
    {"name": "Stanford University", "country": "USA", "note": "Top global research university"},
    {"name": "MIT", "country": "USA", "note": "Engineering & technology leader"},
    {"name": "Harvard University", "country": "USA", "note": "Global brand & research output"},
    {"name": "University of Cambridge", "country": "UK", "note": "Historic research excellence"},
    {"name": "Imperial College London", "country": "UK", "note": "Science & engineering focus"},
    {"name": "ETH Zurich", "country": "Switzerland", "note": "Europe STEM leader"},
    {"name": "National University of Singapore", "country": "Singapore", "note": "Asia top tier"},
    {"name": "Tsinghua University", "country": "China", "note": "Engineering strength"},
    {"name": "University of Tokyo", "country": "Japan", "note": "Leading Japanese research university"},
]


def page_shell(title: str, desc: str, keywords: str, body: str, active="universities") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} | SearchKaro</title>
  <meta name="description" content="{html.escape(desc)[:160]}" />
  <meta name="keywords" content="{html.escape(keywords)}" />
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <header class="site-header">
    <div class="container nav">
      <a class="logo" href="../index.html">Search<span>Karo</span></a>
      <button class="nav-toggle" aria-label="Menu" onclick="document.body.classList.toggle('nav-open')">☰</button>
      <nav>
        <a href="../index.html">Home</a>
        <a href="../scholarships/">Scholarships</a>
        <a href="../jobs/">Jobs</a>
        <a href="./" class="active">Universities</a>
        <a href="../courses/">Courses</a>
        <a href="../blog/">Blog</a>
      </nav>
    </div>
  </header>
  {body}
  <footer class="site-footer"><div class="container"><p>Reference lists for guidance only. Confirm latest HEC and Times Higher Education rankings on official sites.</p></div></footer>
</body>
</html>
"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "pakistan_hec": PAKISTAN_HEC_GENERAL,
        "times_ref": TIMES_REF,
        "by_field": BY_FIELD,
    }
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Index
    field_links = "".join(
        f'<a class="card mini" href="{slug}.html"><h3>{html.escape(data["title"])}</h3><p>By country lists</p></a>'
        for slug, data in BY_FIELD.items()
    )
    hec_rows = "".join(
        f"<tr><td>{html.escape(u['name'])}</td><td>{html.escape(u['city'])}</td><td>{html.escape(u['hec_note'])}</td></tr>"
        for u in PAKISTAN_HEC_GENERAL
    )
    times_rows = "".join(
        f"<tr><td>{html.escape(u['name'])}</td><td>{html.escape(u['country'])}</td><td>{html.escape(u['note'])}</td></tr>"
        for u in TIMES_REF
    )
    index_body = f"""
  <section class="page-head container">
    <h1>University Rankings & Field Guides</h1>
    <p class="sub">Pakistan HEC-oriented university lists, global Times-style references, and medical, engineering, arts, law, and allied sciences universities by country — built for students in Pakistan and India.</p>
  </section>
  <main class="container section">
    <div class="home-grid">{field_links}</div>
    <h2>Pakistan universities (HEC-oriented reference)</h2>
    <div class="table-wrap"><table class="data-table">
      <thead><tr><th>University</th><th>City</th><th>Focus</th></tr></thead>
      <tbody>{hec_rows}</tbody>
    </table></div>
    <p class="note"><a href="pakistan.html">Full Pakistan universities page →</a></p>
    <h2>Times Higher Education style global references</h2>
    <div class="table-wrap"><table class="data-table">
      <thead><tr><th>University</th><th>Country</th><th>Note</th></tr></thead>
      <tbody>{times_rows}</tbody>
    </table></div>
    <p class="note">Always verify the latest year on <a href="https://www.timeshighereducation.com/world-university-rankings" rel="noopener nofollow" target="_blank">Times Higher Education</a> and <a href="https://www.hec.gov.pk/" rel="noopener nofollow" target="_blank">HEC Pakistan</a>.</p>
  </main>
"""
    (OUT / "index.html").write_text(
        page_shell(
            "University Rankings Pakistan HEC & World",
            "HEC Pakistan university lists, Times world ranking references, medical engineering law arts universities by country.",
            "hec ranking pakistan, times higher education ranking, best universities pakistan, medical universities, engineering universities",
            index_body,
        ),
        encoding="utf-8",
    )

    # Pakistan page
    pk_body = f"""
  <section class="page-head container">
    <h1>Best Universities in Pakistan (HEC-oriented)</h1>
    <p class="sub">Popular public and private universities students search for under HEC recognition, engineering, medical, and general categories.</p>
  </section>
  <main class="container section">
    <div class="table-wrap"><table class="data-table">
      <thead><tr><th>University</th><th>City</th><th>Notes</th></tr></thead>
      <tbody>{hec_rows}</tbody>
    </table></div>
    <div class="card" style="margin-top:16px">
      <h2>How to use HEC rankings</h2>
      <p>HEC publishes category rankings (general, engineering & technology, medicine, business, agriculture). Use the official HEC portal for the latest year before admissions or equivalency decisions.</p>
    </div>
    <p><a href="./">← All university guides</a></p>
  </main>
"""
    (OUT / "pakistan.html").write_text(
        page_shell(
            "Best Universities in Pakistan HEC Ranking",
            "List of top universities in Pakistan with HEC-oriented notes for students and parents.",
            "hec ranking, best universities in pakistan, NUST ranking, UET Lahore, LUMS",
            pk_body,
        ),
        encoding="utf-8",
    )

    # Field pages
    for slug, data in BY_FIELD.items():
        blocks = []
        for country, unis in data["countries"].items():
            lis = "".join(f"<li>{html.escape(u)}</li>" for u in unis)
            blocks.append(f"<div class=\"card\"><h2>{html.escape(country)}</h2><ul>{lis}</ul></div>")
        body = f"""
  <section class="page-head container">
    <h1>{html.escape(data['title'])} by Country</h1>
    <p class="sub">Curated lists for students comparing {html.escape(slug.replace('-', ' '))} programs in Pakistan, India, Europe, and more.</p>
  </section>
  <main class="container home-grid" style="padding-bottom:40px">{''.join(blocks)}</main>
"""
        (OUT / f"{slug}.html").write_text(
            page_shell(data["title"] + " by Country", data["title"] + " ranked style lists by country.", data["keywords"], body),
            encoding="utf-8",
        )

    print(f"Universities pages written → {OUT}")


if __name__ == "__main__":
    main()
