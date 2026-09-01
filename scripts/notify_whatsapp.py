#!/usr/bin/env python3
"""
Post newly listed free courses to WhatsApp (Channel / group / chat).

Providers:
1) baileys  — POST to your Baileys bridge (whatsapp-baileys/)  ★ recommended with https://baileys.wiki/
2) whapi    — Whapi.cloud channel API
3) meta     — Meta Cloud API (phone chat, not Channel)
4) webhook  — generic JSON {"text": "..."}

Secrets:
  SITE_BASE_URL              https://searchkaro.online
  WHATSAPP_PROVIDER          baileys | whapi | meta | webhook | auto
  BAILEYS_WEBHOOK_URL        https://your-host:8787/send
  BAILEYS_API_SECRET         Bearer token matching bridge API_SECRET
  WHAPI_TOKEN / WHAPI_CHANNEL_ID
  WHATSAPP_TOKEN / WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_TO
  WHATSAPP_WEBHOOK_URL
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
    return (os.getenv("SITE_BASE_URL") or "https://searchkaro.online").rstrip("/")


def build_message(new_courses: list[dict], total: int) -> str:
    base = site_base()
    list_url = f"{base}/courses/"
    lines = [
        "🎓 *New free Udemy courses — SearchKaro*",
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
            "Open on the site → *Enroll on Udemy*.",
            "#FreeUdemy #SearchKaro",
        ]
    )
    return "\n".join(lines).strip()


def send_baileys(text: str) -> bool:
    url = (os.getenv("BAILEYS_WEBHOOK_URL") or os.getenv("WHATSAPP_WEBHOOK_URL") or "").strip()
    secret = (os.getenv("BAILEYS_API_SECRET") or os.getenv("API_SECRET") or "").strip()
    if not url:
        print("Baileys: missing BAILEYS_WEBHOOK_URL")
        return False
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    payload = {"text": text}
    jid = (os.getenv("BAILEYS_TARGET_JID") or os.getenv("TARGET_JID") or "").strip()
    if jid:
        payload["jid"] = jid
    resp = requests.post(url, headers=headers, json=payload, timeout=45)
    print(f"Baileys status={resp.status_code} body={resp.text[:300]}")
    return resp.status_code in (200, 201)


def send_whapi(text: str) -> bool:
    token = os.getenv("WHAPI_TOKEN") or os.getenv("WHATSAPP_TOKEN")
    channel = os.getenv("WHAPI_CHANNEL_ID") or os.getenv("WHATSAPP_CHANNEL_ID")
    if not token or not channel:
        print("Whapi: missing WHAPI_TOKEN or WHAPI_CHANNEL_ID")
        return False
    url = os.getenv("WHAPI_API_URL", "https://gate.whapi.cloud/messages/text")
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
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
    # If this is the Baileys URL, prefer authorized baileys sender
    if "/send" in hook and os.getenv("BAILEYS_API_SECRET"):
        return send_baileys(text)
    resp = requests.post(hook, json={"text": text, "source": "searchkaro"}, timeout=30)
    print(f"Webhook status={resp.status_code}")
    return resp.status_code in (200, 201, 204)


def main() -> None:
    force = os.getenv("FORCE_WHATSAPP", "").strip().lower() in ("1", "true", "yes")
    data = load_json(COURSES_JSON, {"courses": []})
    courses = data.get("courses") or []
    if not courses:
        print("No courses — skip WhatsApp")
        sys.exit(0)

    seen = set(load_json(SEEN_JSON, {"slugs": []}).get("slugs") or [])
    current_slugs = [c.get("slug") for c in courses if c.get("slug")]
    new_courses = [c for c in courses if c.get("slug") and c["slug"] not in seen]

    if force and not new_courses:
        new_courses = courses[:8]
        print("FORCE_WHATSAPP: sample of current courses")

    if not new_courses:
        print("No new courses — skip WhatsApp")
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

    if provider in ("auto", "baileys") and os.getenv("BAILEYS_WEBHOOK_URL"):
        ok = send_baileys(text) or ok
    if provider in ("auto", "whapi") and (
        os.getenv("WHAPI_TOKEN") or os.getenv("WHAPI_CHANNEL_ID")
    ):
        ok = send_whapi(text) or ok
    if provider in ("auto", "meta") and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
        ok = send_meta(text) or ok
    if provider in ("auto", "webhook") and os.getenv("WHATSAPP_WEBHOOK_URL"):
        ok = send_webhook(text) or ok

    if not ok and provider == "auto":
        if os.getenv("BAILEYS_WEBHOOK_URL"):
            ok = send_baileys(text)
        if not ok and os.getenv("WHAPI_CHANNEL_ID"):
            ok = send_whapi(text)
        if not ok and os.getenv("WHATSAPP_PHONE_NUMBER_ID"):
            ok = send_meta(text)
        if not ok and os.getenv("WHATSAPP_WEBHOOK_URL"):
            ok = send_webhook(text)

    if not ok:
        print(
            "WhatsApp not sent. For Baileys set:\n"
            "  BAILEYS_WEBHOOK_URL + BAILEYS_API_SECRET\n"
            "  Run whatsapp-baileys/ on a VPS (see README)\n"
            "Or Whapi: WHAPI_TOKEN + WHAPI_CHANNEL_ID"
        )
        sys.exit(0)

    seen.update(current_slugs)
    SEEN_JSON.parent.mkdir(parents=True, exist_ok=True)
    SEEN_JSON.write_text(
        json.dumps({"slugs": sorted(seen)[-500:]}, indent=2), encoding="utf-8"
    )
    print(f"WhatsApp OK — posted {len(new_courses)} new courses")


if __name__ == "__main__":
    main()
