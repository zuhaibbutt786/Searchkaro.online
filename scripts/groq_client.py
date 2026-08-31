#!/usr/bin/env python3
"""Groq chat helper with ordered model fallbacks (2026 model IDs)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

# Current Groq production chat models (llama-3.1/3.3 free-tier decommissioned Aug 2026)
# See: https://console.groq.com/docs/deprecations
DEFAULT_MODELS = [
    "openai/gpt-oss-20b",       # fast default replacement for 8B instant
    "openai/gpt-oss-120b",      # stronger replacement for 70B
    "qwen/qwen3.6-27b",         # alternate strong model
    "groq/compound",            # system model if available
    "llama-3.3-70b-versatile",  # still works on some enterprise tiers
    "llama-3.1-8b-instant",
]

GROQ_MODELS = [
    m.strip()
    for m in os.getenv("GROQ_MODELS", ",".join(DEFAULT_MODELS)).split(",")
    if m.strip()
]

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

_discovered: list[str] | None = None


def _discover_models(api_key: str) -> list[str]:
    """If configured IDs all fail, try live /models list (chat-capable only)."""
    global _discovered
    if _discovered is not None:
        return _discovered
    try:
        resp = requests.get(
            GROQ_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        if resp.status_code != 200:
            _discovered = []
            return _discovered
        ids = []
        for m in resp.json().get("data") or []:
            mid = m.get("id") or ""
            # skip whisper / guard / audio
            low = mid.lower()
            if any(x in low for x in ("whisper", "guard", "tts", "orpheus")):
                continue
            ids.append(mid)
        # prefer known good prefixes first
        prefer = []
        rest = []
        for mid in ids:
            if mid.startswith(("openai/", "qwen/", "groq/", "llama")):
                prefer.append(mid)
            else:
                rest.append(mid)
        _discovered = prefer + rest
        print(f"Discovered {len(_discovered)} Groq models from API")
        return _discovered
    except Exception as e:
        print(f"Model discovery failed: {e}")
        _discovered = []
        return _discovered


def _parse_json_content(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
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


def groq_chat_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.6,
    max_tokens: int = 2000,
    timeout: int = 55,
) -> dict[str, Any] | None:
    """Call Groq; try each model until one returns a valid JSON object."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not set")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    models = list(GROQ_MODELS)
    last_err = None
    tried: set[str] = set()

    def attempt(model: str) -> dict[str, Any] | None:
        nonlocal last_err
        if model in tried:
            return None
        tried.add(model)
        try:
            resp = requests.post(
                GROQ_URL,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=timeout,
            )
            if resp.status_code != 200:
                print(f"Groq {model}: HTTP {resp.status_code} — {resp.text[:160]}")
                last_err = resp.text[:160]
                return None
            raw = resp.json()["choices"][0]["message"]["content"]
            data = _parse_json_content(raw)
            if data is None:
                print(f"Groq {model}: invalid JSON, trying next")
                last_err = "invalid json"
                return None
            print(f"Groq OK with model={model}")
            return data
        except Exception as e:
            print(f"Groq {model}: error {e}")
            last_err = str(e)
            return None

    for model in models:
        data = attempt(model)
        if data is not None:
            return data

    # Auto-discover live models if configured list failed
    for model in _discover_models(api_key):
        data = attempt(model)
        if data is not None:
            return data

    print(f"All Groq models failed. Last error: {last_err}")
    return None
