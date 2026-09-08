#!/usr/bin/env python3
"""
Post free courses / jobs / scholarships to WhatsApp Channel (Whapi / Baileys / Meta).

Course messages follow the popular category digest style:
  *_8 Sep | 35 💻 Development Free Udemy Coupons — SearchKaro_*
  numbered list + SearchKaro detail links

Env:
  NOTIFY_MODE=courses|jobs|scholarships|all   (default: courses)
  SITE_BASE_URL=https://searchkaro.online
  WHATSAPP_PROVIDER=whapi|baileys|meta|webhook|auto
  WHAPI_TOKEN, WHAPI_CHANNEL_ID
  FORCE_WHATSAPP=1  (post even if nothing new)
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
COURSES_JSON = ROOT / "data" / "courses.json"
SEEN_JSON = ROOT / "data" / "courses_seen.json"
JOBS_JSON = ROOT / "data" / "jobs.json"
SCHOLARSHIPS_JSON = ROOT / "data" / "scholarships.json"
JOBS_SEEN = ROOT / "data" / "jobs_seen.json"
SCHOL_SEEN = ROOT / "data" / "scholarships_seen.json"

# WhatsApp practical limit per message
MAX_CHARS = 3500
MAX_ITEMS_PER_MSG = 35

CAT_EMOJI = {
    "development": "💻",
    "design": "🎨",
    "it & software": "🖥️",
    "it and software": "🖥️",
    "marketing": "📣",
    "business": "💼",
    "finance & accounting": "💰",
    "finance and accounting": "💰",
    "personal development": "🚀",
    "office productivity": "📊",
    "health & fitness": "🏋️",
    "photography & video": "📷",
    "music": "🎵",
    "lifestyle": "✨",
    "teaching & academics": "📚",
}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def site_base() -> str:
    return (os.getenv("SITE_BASE_URL") or "https://searchkaro.online").rstrip("/")


def today_label() -> str:
    now = datetime.now(ZoneInfo("Asia/Karachi"))
    return now.strftime("%-d %b")  # e.g. 8 Sep


def cat_emoji(category: str) -> str:
    return CAT_EMOJI.get((category or "").strip().lower(), "🎓")


def normalize_category(raw: str) -> str:
    c = (raw or "").strip()
    if not c or c.lower() in {"category", "other", "n/a", "none"}:
        return "General"
    # strip leftover "English |"
    c = c.split("|")[-1].strip()
    return c[:60] or "General"


def course_detail_url(c: dict) -> str:
    base = site_base()
    page = c.get("page") or ""
    slug = c.get("slug") or ""
    if page:
        return f"{base}/courses/{page.lstrip('/')}"
    if slug:
        return f"{base}/courses/p/{slug}.html"
    return f"{base}/courses/"


def build_category_messages(courses: list[dict]) -> list[str]:
    """One or more WhatsApp messages per category (e-next style)."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in courses:
        by_cat[normalize_category(c.get("category") or "")].append(c)

    # Prefer larger / known categories first
    order = sorted(by_cat.keys(), key=lambda k: (-len(by_cat[k]), k.lower()))
    messages: list[str] = []
    day = today_label()
    list_url = f"{site_base()}/courses/"

    for cat in order:
        items = by_cat[cat]
        # chunk
        for start in range(0, len(items), MAX_ITEMS_PER_MSG):
            chunk = items[start : start + MAX_ITEMS_PER_MSG]
            n = len(chunk)
            emoji = cat_emoji(cat)
            header = f"*_{day} | {n} {emoji} {cat} Free Udemy Coupons — SearchKaro_*"
            lines = [
                header,
                "━━━━━━━━━━━━━━━━━━━━━",
                list_url,
                "━━━━━━━━━━━━━━━━━━━━━",
            ]
            for i, c in enumerate(chunk, 1):
                title = (c.get("title") or "Course").strip()
                lines.append(f"*#{i:02d}* _{title}_")
                lines.append(course_detail_url(c))
                lines.append("")
            lines.extend(
                [
                    "━━━━━━━━━━━━━━━━━━━━━",
                    "_Enroll on the course page → Udemy. Share with friends._ ✨",
                    "#FreeUdemy #SearchKaro",
                ]
            )
            msg = "\n".join(lines).strip()
            # if still too long, hard-split further
            if len(msg) <= MAX_CHARS:
                messages.append(msg)
            else:
                # smaller chunks
                mid = max(5, len(chunk) // 2)
                for sub_start in range(0, len(chunk), mid):
                    sub = chunk[sub_start : sub_start + mid]
                    lines = [
                        f"*_{day} | {len(sub)} {emoji} {cat} Free Udemy Coupons — SearchKaro_*",
                        "━━━━━━━━━━━━━━━━━━━━━",
                        list_url,
                        "━━━━━━━━━━━━━━━━━━━━━",
                    ]
                    for i, c in enumerate(sub, 1):
                        lines.append(f"*#{i:02d}* _{(c.get('title') or 'Course').strip()}_")
                        lines.append(course_detail_url(c))
                        lines.append("")
                    lines.extend(
                        [
                            "━━━━━━━━━━━━━━━━━━━━━",
                            "_Enroll on the course page → Udemy._ ✨",
                            "#FreeUdemy #SearchKaro",
                        ]
                    )
                    messages.append("\n".join(lines).strip())
    return messages


def build_list_message(kind: str, items: list[dict], list_path: str) -> str:
    day = today_label()
    base = site_base()
    title_map = {
        "jobs": ("💼", "Jobs — Pakistan · Europe · Remote"),
        "scholarships": ("🎓", "MS & PhD Scholarships"),
    }
    emoji, label = title_map.get(kind, ("📌", kind.title()))
    lines = [
        f"*_{day} | {len(items)} {emoji} {label} — SearchKaro_*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{base}/{list_path.strip('/')}/",
        "━━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, it in enumerate(items[:25], 1):
        t = (it.get("title") or "Listing").strip()
        page = it.get("page") or ""
        if page:
            url = f"{base}/{list_path.strip('/')}/{page.lstrip('/')}"
        elif it.get("slug"):
            url = f"{base}/{list_path.strip('/')}/p/{it['slug']}.html"
        else:
            url = f"{base}/{list_path.strip('/')}/"
        region = it.get("region") or it.get("country") or ""
        extra = f" ({region})" if region else ""
        lines.append(f"*#{i:02d}* _{t}_{extra}")
        lines.append(url)
        lines.append("")
    if len(items) > 25:
        lines.append(f"…and {len(items) - 25} more on the site.")
        lines.append("")
    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━━━━",
            "_Always verify deadlines on official pages._",
            "#SearchKaro",
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
    if "/send" in hook and os.getenv("BAILEYS_API_SECRET"):
        return send_baileys(text)
    resp = requests.post(hook, json={"text": text, "source": "searchkaro"}, timeout=30)
    print(f"Webhook status={resp.status_code}")
    return resp.status_code in (200, 201, 204)


def dispatch(text: str) -> bool:
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
    return ok


def notify_courses() -> bool:
    force = os.getenv("FORCE_WHATSAPP", "").strip().lower() in ("1", "true", "yes")
    data = load_json(COURSES_JSON, {"courses": []})
    courses = data.get("courses") or []
    if not courses:
        print("No courses — skip")
        return True

    seen = set(load_json(SEEN_JSON, {"slugs": []}).get("slugs") or [])
    current_slugs = [c.get("slug") for c in courses if c.get("slug")]
    new_courses = [c for c in courses if c.get("slug") and c["slug"] not in seen]

    if force and not new_courses:
        new_courses = courses[:]
        print("FORCE_WHATSAPP: posting all current courses by category")

    if not new_courses:
        print("No new courses — skip WhatsApp")
        save_json(SEEN_JSON, {"slugs": current_slugs[-800:]})
        return True

    messages = build_category_messages(new_courses)
    print(f"Prepared {len(messages)} WhatsApp message(s) for {len(new_courses)} courses")
    any_ok = False
    for i, text in enumerate(messages, 1):
        print(f"--- WhatsApp message {i}/{len(messages)} ({len(text)} chars) ---")
        print(text[:500] + ("…" if len(text) > 500 else ""))
        if dispatch(text):
            any_ok = True
        else:
            print(f"Failed to send message {i}")

    if not any_ok:
        print(
            "WhatsApp not sent. Set WHAPI_TOKEN + WHAPI_CHANNEL_ID "
            "(or Baileys / Meta secrets)."
        )
        return False

    seen.update(current_slugs)
    save_json(SEEN_JSON, {"slugs": sorted(seen)[-800:]})
    print(f"WhatsApp OK — course digests posted ({len(new_courses)} courses)")
    return True


def _new_items(path: Path, seen_path: Path, key_field: str = "slug") -> tuple[list[dict], list[str]]:
    data = load_json(path, {})
    items = data.get("items") or data.get("jobs") or data.get("scholarships") or []
    if not items and isinstance(data, list):
        items = data
    seen = set(load_json(seen_path, {"ids": []}).get("ids") or [])
    new = []
    all_ids = []
    for it in items:
        kid = it.get(key_field) or it.get("page") or it.get("title") or ""
        if not kid:
            continue
        all_ids.append(str(kid))
        if str(kid) not in seen:
            new.append(it)
    return new, all_ids


def notify_jobs() -> bool:
    force = os.getenv("FORCE_WHATSAPP", "").strip().lower() in ("1", "true", "yes")
    new_items, all_ids = _new_items(JOBS_JSON, JOBS_SEEN)
    if force and not new_items:
        data = load_json(JOBS_JSON, {"items": []})
        new_items = (data.get("items") or [])[:15]
    if not new_items:
        print("No new jobs — skip WhatsApp")
        save_json(JOBS_SEEN, {"ids": all_ids[-500:]})
        return True
    text = build_list_message("jobs", new_items, "jobs")
    print("--- Jobs WhatsApp ---")
    print(text[:600])
    ok = dispatch(text)
    if ok:
        seen = set(load_json(JOBS_SEEN, {"ids": []}).get("ids") or [])
        seen.update(all_ids)
        save_json(JOBS_SEEN, {"ids": sorted(seen)[-500:]})
        print(f"WhatsApp OK — {len(new_items)} jobs")
    return ok


def notify_scholarships() -> bool:
    force = os.getenv("FORCE_WHATSAPP", "").strip().lower() in ("1", "true", "yes")
    new_items, all_ids = _new_items(SCHOLARSHIPS_JSON, SCHOL_SEEN)
    if force and not new_items:
        data = load_json(SCHOLARSHIPS_JSON, {"items": []})
        new_items = (data.get("items") or [])[:15]
    if not new_items:
        print("No new scholarships — skip WhatsApp")
        save_json(SCHOL_SEEN, {"ids": all_ids[-500:]})
        return True
    text = build_list_message("scholarships", new_items, "scholarships")
    print("--- Scholarships WhatsApp ---")
    print(text[:600])
    ok = dispatch(text)
    if ok:
        seen = set(load_json(SCHOL_SEEN, {"ids": []}).get("ids") or [])
        seen.update(all_ids)
        save_json(SCHOL_SEEN, {"ids": sorted(seen)[-500:]})
        print(f"WhatsApp OK — {len(new_items)} scholarships")
    return ok


def main() -> None:
    mode = (os.getenv("NOTIFY_MODE") or "courses").strip().lower()
    ok = True
    if mode in ("courses", "all"):
        ok = notify_courses() and ok
    if mode in ("jobs", "all"):
        ok = notify_jobs() and ok
    if mode in ("scholarships", "all"):
        ok = notify_scholarships() and ok
    if mode not in ("courses", "jobs", "scholarships", "all"):
        print(f"Unknown NOTIFY_MODE={mode}")
        sys.exit(1)
    # Never fail the whole workflow solely on WhatsApp
    sys.exit(0)


if __name__ == "__main__":
    main()
