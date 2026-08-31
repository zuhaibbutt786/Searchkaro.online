#!/usr/bin/env python3
"""
Post newly listed free courses to a WhatsApp Channel (or chat).

Supports:
1) Whapi.cloud  — best for WhatsApp Channels (newsletter IDs like 1203...@newsletter)
2) Meta Cloud API — send to a phone number (not a Channel)
3) Generic webhook — POST JSON {"text": "..."} to any automation URL

Secrets / env:
  SITE_BASE_URL              e.g. https://zuhaibbutt786.github.io/tech-blog-courses
  WHATSAPP_PROVIDER          whapi | meta | webhook  (default: auto)
  WHAPI_TOKEN                Whapi API token
  WHAPI_CHANNEL_ID           e.g. 120363171744447809@newsletter
  WHATSAPP_TOKEN             Meta Cloud API access token
  WHATSAPP_PHONE_NUMBER_ID   Meta phone number id
  WHATSAPP_TO                E.164 digits only, e.g. 923001234567
  WHATSAPP_WEBHOOK_URL       optional generic webhook
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
COURSES_JSON = ROOT / "data" / "courses.json"
SEEN_JSON = ROOT / "data" / "courses_seen.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def site_base() -> str:
    return os.getenv(
        "SITE_BASE_URL",
        "https://zuhaibbutt786.github.io/tech-blog-courses",
    ).rstrip("/")


def build_message(new_courses: list[dict], total: int) -> str:
    base = site_base()
    list_url = f"{base}/courses/"
    lines = [
        "🎓 *New free Udemy courses today*",
        "",
    ]
    for c in new_courses[:12]:
        title = (c.get("title") or "Course").strip()
        slug = c.get("slug") or ""
        page = c.get("page") or (f"p/{slug}.html" if slug else "")
        detail = f"{base}/courses/{page}" if page else list_url
        cat = c.get("category") or ""
        lines.append(f"• *{title}*" + (f" ({cat})" if cat else ""))
        lines.append(f"  {detail}")
        lines.append("")

    if len(new_courses) > 12:
        lines.append(f"…and {len(new_courses) - 12} more.")
        lines.append("")

    lines.extend(
        [
            f"📋 Full list ({total} courses):",
            list_url,
            "",
            "Open a course on the site → then *Enroll on Udemy*.",
            "#FreeUdemy #LearnWithZuhaib",
        ]
    )
    return "\n".join(lines).strip()


def send_whapi(text: str) -> bool:
    token = os.getenv("WHAPI_TOKEN") or os.getenv("WHATSAPP_TOKEN")
    channel = os.getenv("WHAPI_CHANNEL_ID") or os.getenv("WHATSAPP_CHANNEL_ID")
    if not token or not channel:
        print("Whapi: missing WHAPI_TOKEN or WHAPI_CHANNEL_ID")
        return False
    url = os.getenv("WHAPI_API_URL", "https://gate.whapi.cloud/messages/text")
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"to": channel, "body": text},
        timeout=30,
    )
    print(f"Whapi status={resp.status_code} body={resp.text[:300]}")
    return resp.status_code in (200, 201)


def send_meta(text: str) -> bool:
    token = os.getenv("WHATSAPP_TOKEN")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    to = os.getenv("WHATSAPP_TO", "").lstrip("+")
    if not token or not phone_id or not to:
        print("Meta: missing WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_TO")
        return False
    url = f"https://graph.facebook.com/v20.0/{phone_id}/messages"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": True, "body": text},
        },
        timeout=30,
    )
    print(f"Meta status={resp.status_code} body={resp.text[:300]}")
    return resp.status_code in (200, 201)


def send_webhook(text: str) -> bool:
    hook = os.getenv("WHATSAPP_WEBHOOK_URL")
    if not hook:
        return False
    resp = requests.post(hook, json={"text": text, "source": "tech-blog-courses"}, timeout=30)
    print(f"Webhook status={resp.status_code}")
    return resp.status_code in (200, 201, 204)


def main() -> None:
    force = os.getenv("FORCE_WHATSAPP", "").strip().lower() in ("1", "true", "yes")
    data = load_json(COURSES_JSON, {"courses": []})
    courses = data.get("courses") or []
    if not courses:
        print("No courses in data/courses.json — skip WhatsApp")
        sys.exit(0)

    seen = set(load_json(SEEN_JSON, {"slugs": []}).get("slugs") or [])
    current_slugs = [c.get("slug") for c in courses if c.get("slug")]

    new_courses = [c for c in courses if c.get("slug") and c["slug"] not in seen]
    if force and not new_courses:
        new_courses = courses[:8]
        print("FORCE_WHATSAPP: posting sample of current courses")

    if not new_courses:
        print("No new courses since last run — skip WhatsApp post")
        # still refresh seen set to current
        SEEN_JSON.write_text(
            json.dumps({"slugs": current_slugs[-500:]}, indent=2), encoding="utf-8"
        )
        sys.exit(0)

    text = build_message(new_courses, total=len(courses))
    print("--- WhatsApp message ---")
    print(text)
    print("------------------------")

    provider = (os.getenv("WHATSAPP_PROVIDER") or "auto").strip().lower()
    ok = False

    if provider in ("auto", "whapi") and (
        os.getenv("WHAPI_TOKEN") or os.getenv("WHAPI_CHANNEL_ID")
    ):
        ok = send_whapi(text) or ok
    if provider in ("auto", "meta") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
        ok = send_meta(text) or ok
    if provider in ("auto", "webhook") and os.getenv("WHATSAPP_WEBHOOK_URL"):
        ok = send_webhook(text) or ok

    if not ok and provider == "auto":
        # try all once more by capability
        if os.getenv("WHAPI_CHANNEL_ID"):
            ok = send_whapi(text)
        if not ok and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
            ok = send_meta(text)
        if not ok and os.getenv("WHATSAPP_WEBHOOK_URL"):
            ok = send_webhook(text)

    if not ok:
        print(
            "WhatsApp not sent. Add secrets:\n"
            "  Channel (recommended): WHAPI_TOKEN + WHAPI_CHANNEL_ID\n"
            "  or Meta chat: WHATSAPP_TOKEN + WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_TO\n"
            "  or WHATSAPP_WEBHOOK_URL"
        )
        sys.exit(0)  # do not fail the whole workflow

    # mark seen
    seen.update(current_slugs)
    SEEN_JSON.parent.mkdir(parents=True, exist_ok=True)
    SEEN_JSON.write_text(
        json.dumps({"slugs": sorted(seen)[-500:]}, indent=2), encoding="utf-8"
    )
    print(f"WhatsApp OK — posted {len(new_courses)} new courses")


if __name__ == "__main__":
    main()
