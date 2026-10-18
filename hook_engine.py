# hook_engine.py v5
# Bulletproof hybrid hook generator.
# Error filter uses literal substrings (no regex ambiguity).

import os
import re
import time
import random
import requests


POLL_KEY = os.environ.get("POLLINATIONS_KEY", "")
POLL_KEYED_URL = "https://gen.pollinations.ai/v1/chat/completions"
POLL_ANON_URL = "https://text.pollinations.ai/openai"
LOCAL_URL = "http://127.0.0.1:8089/v1/chat/completions"


STYLE_EXAMPLES = """
Real viral hooks from dark psychology channels:

1. "You've been told you're overreacting for years. Here's what's actually happening."
2. "You check your phone before answering them. That's not love, that's training."
3. "You apologize for things you didn't do. Here is why you learned that."
4. "You feel crazy in arguments you didn't start. That is exactly the point."
5. "You explain yourself three times in one text. Someone trained you that this was necessary."
6. "The person hurting you knows exactly what they're doing. Here is how."
7. "You think you're protecting them. You are losing yourself."
8. "You stopped telling your friends the truth. You know why."
9. "You trust them more than you trust yourself. That was the plan."
10. "You catch yourself doubting your own memory. Someone is counting on that."
"""


HOOK_SYSTEM = f"""You write YouTube hooks for a dark psychology channel.

LANGUAGE: Write ONLY in standard American English.
NEVER use Hindi, Hinglish, Urdu, or any other language.
Every word must be English.

A hook is 1-2 spoken sentences, 12-24 words. It opens the video.

STYLE REFERENCE (match this exact tone):
{STYLE_EXAMPLES}

Every hook must:
- Start with "You" or "If you" in the first 3 words.
- Name ONE concrete, physical behavior the viewer can recognize in themselves.
- Use one of these words: lose, losing, before, never, stop, cost, quit, fail.
- End with an open question or an unresolved statement.

FORBIDDEN:
- Hindi/Hinglish words (hai, nahi, mein, aur, ko, ka, ke, se).
- Poetry words alone: deceit, descent, depths, shadows, surface, void.
- Starting with "Don't be fooled" or "Gaslighting's roots".
- Fewer than 12 words.
- Abstract claims without a concrete behavior.

Output exactly 5 hooks, one per line.
No numbering. No quotes. No explanation.
Each hook must approach the topic from a different angle."""


# ============================================================
# ERROR FILTER — literal substrings only (no regex ambiguity)
# ============================================================
ERROR_PHRASES = [
    "not enough credits",
    "please top up",
    "complete a quest",
    "contact whoever runs",
    "this api key",
    "rate limit exceeded",
    "quota exceeded",
    "insufficient funds",
    "insufficient credits",
    "unauthorized access",
    "as an ai language model",
    "as an ai,",
    "i cannot help with",
    "i cannot assist",
    "i am unable to",
    "i'm sorry, but i",
    "sorry, i cannot",
    "sorry, i can't",
]


HOOK_OPENERS = (
    "you ", "you're ", "you've ", "your ", "if you ",
    "we ", "most people ", "nobody ", "the person ",
    "the truth ", "the moment ", "the thing ",
)


def _is_error_text(text):
    """True only if text is clearly an API error or empty."""
    if not text:
        return True

    t = str(text).strip()
    if len(t) < 15:
        return True

    tl = t.lower()

    # Reject URLs
    if tl.startswith("http") or "://" in tl[:40]:
        return True

    # Whitelist: hook-style openers are never errors
    tl_stripped = tl.lstrip()
    for opener in HOOK_OPENERS:
        if tl_stripped.startswith(opener):
            return False

    # Check literal error phrases
    for phrase in ERROR_PHRASES:
        if phrase in tl:
            return True

    # Check for leading "error:" or "[error]"
    if tl_stripped.startswith("error:") or tl_stripped.startswith("[error]"):
        return True

    return False


# ============================================================
# PROVIDERS
# ============================================================
def _anonymous_pollinations(messages, max_tokens=600, temperature=0.9):
    payload = {
        "model": "openai",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": random.randint(1, 999999),
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, 4):
        try:
            print(f"    [ANON] attempt {attempt}/3")
            r = requests.post(POLL_ANON_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            if _is_error_text(content):
                raise Exception(f"error-ish: {content[:80]}")
            return content
        except Exception as e:
            print(f"    [ANON] failed: {e}")
            if attempt < 3:
                time.sleep(8 * attempt)
    raise Exception("anonymous pollinations failed")


def _keyed_pollinations(messages, max_tokens=600, temperature=0.9):
    if not POLL_KEY:
        raise Exception("no key")

    payload = {
        "model": "openai",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": random.randint(1, 999999),
    }
    headers = {
        "Authorization": f"Bearer {POLL_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, 3):
        try:
            print(f"    [POLL] attempt {attempt}/2")
            r = requests.post(POLL_KEYED_URL, headers=headers, json=payload, timeout=120)
            if r.status_code in (401, 402, 429):
                raise Exception(f"HTTP {r.status_code}")
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            if _is_error_text(content):
                raise Exception(f"error-ish: {content[:80]}")
            return content
        except Exception as e:
            print(f"    [POLL] failed: {e}")
            if attempt < 2:
                time.sleep(4)
    raise Exception("keyed pollinations failed")


def _local_gemma(messages, max_tokens=800, temperature=0.7):
    payload = {
        "model": "local",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(1, 3):
        try:
            print(f"    [GEMMA] attempt {attempt}/2")
            r = requests.post(LOCAL_URL, headers=headers, json=payload, timeout=300)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            if _is_error_text(content):
                raise Exception(f"error-ish: {content[:80]}")
            return content
        except Exception as e:
            print(f"    [GEMMA] failed: {e}")
            if attempt < 2:
                time.sleep(2)
    raise Exception("local gemma failed")


# ============================================================
# PARSER
# ============================================================
def _parse_hooks(raw):
    if _is_error_text(raw):
        return []

    hooks = []
    for line in raw.splitlines():
        line = line.strip()
        line = re.sub(r'^[\d]+[\.\)]\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)
        line = line.strip('"\'').strip()
        if not line:
            continue
        if _is_error_text(line):
            continue
        wc = len(line.split())
        if 10 <= wc <= 30:
            hooks.append(line)

    seen = set()
    unique = []
    for h in hooks:
        key = " ".join(h.lower().split()[:4])
        if key in seen:
            continue
        seen.add(key)
        unique.append(h)
    return unique


# ============================================================
# MAIN
# ============================================================
def _safe_parse_hooks(raw):
    """Never crash — returns [] on bad input."""
    if not raw:
        return []
    try:
        return _parse_hooks(raw)
    except Exception as e:
        print(f"    [parser] crashed: {e}")
        return []


def generate_hooks_hybrid(topic, score_fn, n_final=5):
    messages = [
        {"role": "system", "content": HOOK_SYSTEM},
        {"role": "user", "content": f"Topic: {topic}\n\nWrite 5 hooks now."},
    ]

    hooks = []

    try:
        print("[HOOK] Try 1: Anonymous Pollinations...")
        raw = _anonymous_pollinations(messages, max_tokens=600, temperature=0.9)
        hooks = _safe_parse_hooks(raw)
        print(f"[HOOK] Anonymous produced {len(hooks)} hooks")
    except Exception as e:
        print(f"[HOOK] Anonymous failed: {e}")

    if len(hooks) < 3 and POLL_KEY:
        try:
            print("[HOOK] Try 2: Keyed Pollinations...")
            raw = _keyed_pollinations(messages, max_tokens=600, temperature=0.9)
            new_hooks = _safe_parse_hooks(raw)
            print(f"[HOOK] Keyed produced {len(new_hooks)} hooks")
            hooks.extend(new_hooks)
        except Exception as e:
            print(f"[HOOK] Keyed failed: {e}")

    if len(hooks) < 3:
        try:
            print("[HOOK] Try 3: Local Gemma...")
            raw = _local_gemma(messages, max_tokens=800, temperature=0.7)
            new_hooks = _safe_parse_hooks(raw)
            print(f"[HOOK] Gemma produced {len(new_hooks)} hooks")
            hooks.extend(new_hooks)
        except Exception as e:
            print(f"[HOOK] Gemma failed: {e}")

    if not hooks:
        raise Exception("[HOOK] No valid hooks from any provider")

    scored = []
    for h in hooks:
        parts, verdict = score_fn(h)
        scored.append({"hook": h, "score": verdict, "parts": parts})

    scored.sort(key=lambda x: -x["score"])

    seen = set()
    final = []
    for s in scored:
        key = " ".join(s["hook"].lower().split()[:4])
        if key in seen:
            continue
        seen.add(key)
        final.append(s)
        if len(final) >= n_final:
            break

    return final


if __name__ == "__main__":
    print("hook_engine v5 loaded")
