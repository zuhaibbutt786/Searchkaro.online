#!/usr/bin/env python3
"""Groq chat helper with ordered model fallbacks."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

# Try in order when a model is down, rate-limited, or decommissioned
GROQ_MODELS = [
    m.strip()
    for m in os.getenv(
        "GROQ_MODELS",
        ",".join(
            [
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "gemma2-9b-it",
                "mixtral-8x7b-32768",
            ]
        ),
    ).split(",")
    if m.strip()
]

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


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
        # last resort: extract first {...} block
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
    """Call Groq; try each model until one returns valid JSON object."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not set")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_err = None
    for model in GROQ_MODELS:
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
                print(f"Groq {model}: HTTP {resp.status_code} — {resp.text[:180]}")
                last_err = resp.text[:180]
                # rate limit / overloaded → try next model
                continue

            raw = resp.json()["choices"][0]["message"]["content"]
            data = _parse_json_content(raw)
            if data is None:
                print(f"Groq {model}: invalid JSON, trying next model")
                last_err = "invalid json"
                continue

            print(f"Groq OK with model={model}")
            return data
        except Exception as e:
            print(f"Groq {model}: error {e}")
            last_err = str(e)
            continue

    print(f"All Groq models failed. Last error: {last_err}")
    return None
