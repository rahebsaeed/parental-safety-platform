from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from typing import Optional

import requests

from backend.app.classifiers.categories import Category
from backend.app.db.session import get_connection

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Free-tier models rotate/retire (a hardcoded ID 404s without warning, and
# shared pools 429 under load), so classify by walking this list: first
# HTTP-200 verdict wins. Keep entries instruction-tuned and terse.
FREE_MODELS: list[str] = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-31b-it:free",
    "liquid/lfm-2.5-2.6b:free",
]
FREE_MODEL = FREE_MODELS[0]

# Per-model cooldowns (monotonic timestamps): a model that 429s is skipped
# by subsequent calls until its cooldown expires instead of being retried
# first every time. In-memory only — a restart starts clean, which is the
# safe default (a cooldown may well have expired while down).
_MODEL_COOLDOWN_UNTIL: dict[str, float] = {}
COOLDOWN_RATE_LIMITED = 120.0
COOLDOWN_RETIRED = 86400.0
COOLDOWN_ERROR = 60.0
_MAX_COOLDOWN_WAIT = 30.0


def _cool_down(model: str, seconds: float) -> None:
    _MODEL_COOLDOWN_UNTIL[model] = time.monotonic() + seconds


def _pick_models() -> list[str]:
    """Models worth trying now, preferred order, cooling ones skipped.

    If everything is cooling, wait (bounded) for the earliest recovery
    instead of hammering pools that just said no.
    """
    now = time.monotonic()
    fresh = [m for m in FREE_MODELS if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) <= now]
    if fresh:
        return fresh
    wait = min(_MODEL_COOLDOWN_UNTIL[m] - now for m in FREE_MODELS)
    time.sleep(min(max(wait, 0.0), _MAX_COOLDOWN_WAIT))
    now = time.monotonic()
    recovered = [m for m in FREE_MODELS if _MODEL_COOLDOWN_UNTIL.get(m, 0.0) <= now]
    if recovered:
        return recovered
    # Still cooling after the bounded wait: grant one fresh attempt across
    # the board rather than failing outright (per-iteration guard below
    # would otherwise skip everything again).
    _MODEL_COOLDOWN_UNTIL.clear()
    return list(FREE_MODELS)


def get_model_status() -> list[dict]:
    """Health snapshot for the status endpoint (no network calls)."""
    now = time.monotonic()
    status = []
    for position, model in enumerate(FREE_MODELS):
        retry_in = _MODEL_COOLDOWN_UNTIL.get(model, 0.0) - now
        status.append({
            "model": model,
            "preferred": position == 0,
            "cooling": retry_in > 0,
            "retry_in": max(0, int(retry_in)),
        })
    return status

DEFAULT_CATEGORIES = [
    "UNSAFE",
    "GAMBLING",
    "SOCIAL_MEDIA",
    "STREAMING",
    "GAMING",
    "MESSAGING",
    "NEWS_INFORMATION",
    "PRODUCTIVITY_EDUCATION",
    "SEARCH_PORTAL",
    "INFRASTRUCTURE_SYSTEM",
    "UNKNOWN",
]

# Maps OpenRouter verdicts onto the rules-engine taxonomy so AI results can
# be persisted as first-class domain rules (and therefore drive alerts).
# Safety-critical mappings come first: anything sexually explicit, violent,
# or gambling-related lands in ADULT_CONTENT, the only category the alert
# engine treats as unsafe. UNKNOWN maps to None — never persisted, so the
# domain stays retryable instead of being cemented as uncategorized.
AI_CATEGORY_TO_RULE_CATEGORY: dict[str, Category | None] = {
    "UNSAFE": Category.ADULT_CONTENT,
    "GAMBLING": Category.ADULT_CONTENT,
    "SOCIAL_MEDIA": Category.SOCIAL_MEDIA,
    "STREAMING": Category.STREAMING_VIDEO,
    "GAMING": Category.GAMING,
    "MESSAGING": Category.SOCIAL_MEDIA,
    "NEWS_INFORMATION": Category.NEWS_MEDIA,
    "PRODUCTIVITY_EDUCATION": Category.PRODUCTIVITY,
    "SEARCH_PORTAL": Category.PRODUCTIVITY,
    "INFRASTRUCTURE_SYSTEM": Category.TECH_INFRASTRUCTURE,
    "UNKNOWN": None,
}


def map_ai_category(ai_category: str) -> Category | None:
    """Map an OpenRouter verdict to a rules-engine category (None = skip)."""
    return AI_CATEGORY_TO_RULE_CATEGORY.get((ai_category or "").strip().upper())

def get_openrouter_api_key() -> Optional[str]:
    """Retrieve the OpenRouter API key from settings."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key_name = 'openrouter_api_key'"
        ).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def save_openrouter_api_key(key: str) -> None:
    """Save the OpenRouter API key to settings."""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key_name, value) VALUES (?, ?)",
            ("openrouter_api_key", key),
        )
        conn.commit()
    finally:
        conn.close()


def test_openrouter_api_key(candidate: Optional[str] = None) -> dict:
    """Validate an OpenRouter API key via the /auth/key endpoint.

    If `candidate` is omitted, the saved key is tested. Never logs the key.
    """
    api_key = (candidate or "").strip() or get_openrouter_api_key()
    if not api_key:
        return {"ok": False, "error": "No API key provided or saved"}
    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json().get("data", {}) if response.content else {}
            return {
                "ok": True,
                "label": data.get("label"),
                "usage": data.get("usage"),
                "limit": data.get("limit"),
            }
        if response.status_code in (401, 403):
            return {"ok": False, "error": f"Key rejected by OpenRouter (HTTP {response.status_code})"}
        return {"ok": False, "error": f"OpenRouter returned HTTP {response.status_code}"}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"Could not reach OpenRouter: {e}"}


def classify_with_openrouter(domain: str) -> dict:
    """Classify a domain using OpenRouter's free LLM model.
    
    Returns a dict with category, confidence, and reasoning.
    """
    api_key = get_openrouter_api_key()
    if not api_key:
        return {"category": "UNKNOWN", "confidence": 0.0, "reason": "No OpenRouter API key configured"}
    
    prompt = f"""Classify this domain into ONE of the following categories:
{json.dumps(DEFAULT_CATEGORIES)}

Domain: {domain}

Categories:
- UNSAFE: Adult content, violence, harmful material
- GAMBLING: Gambling, casinos, betting
- SOCIAL_MEDIA: Social networks, messaging apps
- STREAMING: Video/music streaming services
- GAMING: Video games, gaming platforms
- MESSAGING: Communication, chat platforms
- NEWS_INFORMATION: News sites, information portals
- PRODUCTIVITY_EDUCATION: Education, productivity tools
- SEARCH_PORTAL: Search engines, web portals
- INFRASTRUCTURE_SYSTEM: System infrastructure, APIs, CDNs
- UNKNOWN: Cannot determine category

Respond with ONLY the category name and a brief one-line reason."""
    
    last_error: str | None = None
    for model in _pick_models():
        if _MODEL_COOLDOWN_UNTIL.get(model, 0.0) > time.monotonic():
            continue  # cooled down again while an earlier model was tried
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://192.168.1.20",
                    "X-Title": "Parental Safety Platform",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 64,
                    "temperature": 0.3,
                },
                timeout=15,
            )
            if response.status_code == 429:
                # Shared-pool rate limit: cool this model down and fail
                # over to the next one immediately (no blind sleep — the
                # next pool is independent).
                _cool_down(model, COOLDOWN_RATE_LIMITED)
                last_error = f"HTTP 429 from {model}"
                continue
            if response.status_code == 404:
                # Retired model ID: park it for the day, try the next.
                _cool_down(model, COOLDOWN_RETIRED)
                last_error = f"HTTP 404 from {model} (retired?)"
                continue
            response.raise_for_status()
            data = response.json()

            # 200s don't always carry a usable answer (provider quirks,
            # reasoning-only payloads) — treat those as a miss and try
            # the next model rather than failing the whole call.
            try:
                choices = data.get("choices") or []
                message = (choices[0].get("message") or {}) if choices else {}
                content = (message.get("content") or "").strip()
            except (AttributeError, IndexError, TypeError):
                content = ""
            if not content:
                _cool_down(model, COOLDOWN_ERROR)
                last_error = f"Empty answer from {model}: {str(data)[:150]}"
                continue
            lines = content.split("\n")

            # Parse the response - the category is the first token, but
            # models often append the reason on the same line
            # ("MESSAGING: it's a chat site") or decorate it ("**MESSAGING**").
            first = lines[0].strip() if lines and lines[0].strip() else ""
            head, sep, tail = first.partition(":")
            if not sep:
                # Models also separate with " – ", " — " or " - ".
                parts = re.split(r"\s+[–—-]\s+", first, maxsplit=1)
                head = parts[0]
                tail = parts[1] if len(parts) > 1 else ""
            candidate = re.sub(r"[^A-Z_]", "", head.strip().upper())
            if candidate in DEFAULT_CATEGORIES:
                category = candidate
                reason = tail.strip() or (lines[1].strip() if len(lines) > 1 else content)
            else:
                category = "UNKNOWN"
                reason = f"Could not parse category from: {content}"

            if category not in DEFAULT_CATEGORIES:
                category = "UNKNOWN"
                reason = f"Could not parse category from: {content}"

            return {
                "category": category,
                "confidence": 0.85,
                "reason": reason,
                "model": model,
            }
        except requests.exceptions.RequestException as e:
            # 5xx / network errors: cool briefly, try the next model.
            _cool_down(model, COOLDOWN_ERROR)
            last_error = str(e)
            continue
    return {"category": "UNKNOWN", "confidence": 0.0,
            "reason": f"OpenRouter API error: {last_error}"}


def save_classification(domain: str, category: str, confidence: float, model: str = FREE_MODEL) -> None:
    """Save an LLM classification result to the database."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO openrouter_results (domain, category, confidence, model)
               VALUES (?, ?, ?, ?)""",
            (domain, category, confidence, model),
        )
        conn.commit()
    finally:
        conn.close()


def get_cached_classification(domain: str) -> Optional[dict]:
    """Get a cached LLM classification for a domain."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT category, confidence, model FROM openrouter_results WHERE domain = ? ORDER BY created_at DESC LIMIT 1",
            (domain,),
        ).fetchone()
        if row:
            return {"category": row["category"], "confidence": row["confidence"], "model": row["model"]}
        return None
    finally:
        conn.close()


# Free shared pools throttle per-minute traffic; hammering them back to
# back turns one 429 into twenty. Pace uncached calls so a full batch
# spreads out instead of tripping every pool at once.
BATCH_PACE_SECONDS = 5.0


def classify_domains_batch(domains: list[str]) -> dict[str, dict]:
    """Classify multiple domains using OpenRouter."""
    results = {}
    paced = False
    for domain in domains:
        cached = get_cached_classification(domain)
        if cached:
            results[domain] = cached
        else:
            if paced:
                time.sleep(BATCH_PACE_SECONDS)
            result = classify_with_openrouter(domain)
            paced = True
            results[domain] = result
            if result["category"] != "UNKNOWN" or get_openrouter_api_key():
                save_classification(domain, result["category"], result["confidence"],
                                    result.get("model") or FREE_MODEL)
    return results
