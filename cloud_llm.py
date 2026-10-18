# cloud_llm.py — Verified models only (from live API lists)

import os
import time
import random
import threading
import requests
from pathlib import Path
from collections import deque


# ============================================================
# LOAD SECRETS
# ============================================================
for sp in [
    Path.home() / "content-os" / ".contentos" / "secrets.env",
    Path.home() / ".claude_llm_keys",
]:
    if sp.exists():
        try:
            for line in sp.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass


# ============================================================
# RATE LIMITER
# ============================================================
class RateLimiter:
    def __init__(self, rpm):
        self.rpm = rpm
        self.window = deque()
        self.lock = threading.Lock()

    def wait(self):
        min_gap = 60.0 / self.rpm
        with self.lock:
            now = time.time()
            while self.window and now - self.window[0] > 60:
                self.window.popleft()
            if len(self.window) >= self.rpm:
                sleep_for = 60 - (now - self.window[0]) + 0.1
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.time()
                while self.window and now - self.window[0] > 60:
                    self.window.popleft()
            if self.window:
                gap = now - self.window[-1]
                if gap < min_gap:
                    time.sleep(min_gap - gap)
            self.window.append(time.time())


# ============================================================
# PROVIDERS — VERIFIED FROM LIVE API
# ============================================================
GROQ_MODELS = [
    "qwen/qwen3.8-27b",          # 8,000 TPM, non-reasoning → full output
    "openai/gpt-oss-20b",        # reasoning fallback
    "openai/gpt-oss-120b",       # reasoning last resort
]

GROQ_REASONING = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
}

GEMINI_MODELS = [
    "gemini-3.5-flash-lite",   # 1,000+ RPD, fast, best for volume
]


NVIDIA_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b",
    "deepseek-ai/deepseek-v4.1-flash",
    "meta/llama-3.2-11b-vision-instruct",
    "google/gemma-3-12b-it",
]

PROVIDERS = [
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "models": GROQ_MODELS,
        "reasoning_models": GROQ_REASONING,
        "rpm": 2,        # 30s gap enforced via min-gap
        "timeout": 20,
    },
    {
        "name": "nvidia",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "models": NVIDIA_MODELS,
        "reasoning_models": set(),
        "rpm": 38,
        "timeout": 120,
    },
    {
        "name": "gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/models",
        "key_env": "GEMINI_API_KEY",
        "models": GEMINI_MODELS,
        "reasoning_models": set(),
        "rpm": 10,
        "timeout": 120,
        "format": "gemini",
    },
]


# ============================================================
# TASK-BASED ROUTING
# ============================================================
# Model preference per task — non-reasoning models produce fuller output
TASK_MODEL_PREFERENCE = {
    "split":   ["qwen/qwen3.8-27b"],
    "prompts": ["qwen/qwen3.8-27b"],
    "script":  ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"],
    "seo":     ["qwen/qwen3.8-27b"],
}


TASK_ROUTING = {
    "script":   ["groq", "gemini", "nvidia"],
    "split":    ["groq", "gemini", "nvidia"],
    "prompts":  ["groq", "gemini", "nvidia", "local"],
    "default":  ["groq", "gemini", "nvidia"],
}


# ============================================================
# GLOBAL RATE HEALTH — shared state across all calls
# ============================================================
GLOBAL_BLACKLIST = {}       # {provider: unblock_timestamp}
GLOBAL_RPM_WINDOW = {}       # {provider: deque of timestamps}
GLOBAL_LOCK = threading.Lock()


# ============================================================
# LOCAL PROVIDER — Qwen2.5-0.5B on port 8089
# ============================================================
LOCAL_PROVIDER = {
    "name": "local",
    "url": "http://127.0.0.1:8089/v1/chat/completions",
    "key_env": None,
    "models": ["qwen-local"],
    "reasoning_models": set(),
    "rpm": 60,
    "timeout": 180,
}


_RUNTIME = {}

# Try local model first
try:
    import requests as _r
    _resp = _r.get("http://127.0.0.1:8089/health", timeout=2)
    if _resp.status_code == 200:
        _RUNTIME["local"] = {
            "provider": LOCAL_PROVIDER,
            "key": "local",
            "limiter": RateLimiter(60),
            "dead_models": set(),
            "blocked_until": 0,
            "consec_fails": 0,
            "last_call": 0,
            "model_idx": 0,
        }
        print("[cloud_llm] Local Qwen2.5-0.5B detected on :8089")
except Exception:
    print("[cloud_llm] Local model not running — cloud only")

for p in PROVIDERS:
    key = os.environ.get(p["key_env"], "") if p["key_env"] else "anonymous"
    if not key:
        continue
    _RUNTIME[p["name"]] = {
        "provider": p,
        "key": key,
        "limiter": RateLimiter(p["rpm"]),
        "dead_models": set(),
        "blocked_until": 0,
        "last_call": 0,
        "consec_fails": 0,
        "model_idx": 0,
    }

# Global min-gap (seconds) — protects against TPM limits
PROVIDER_MIN_GAP = {
    "local": 0.5,    # essentially no limit
    "groq": 18.0,    # 15s gap → 4 calls/min → rotation keeps TPM safe
    "nvidia": 4.0,   # 38 RPM safe
    "gemini": 8.0,   # 10 RPM safe gap (no TPM cap)
    "pollinations_anon": 15.0,
}


MIN_TOKENS = 800   # reasoning models need headroom


def _call_gemini(rt, messages, max_tokens, temperature):
    """Gemini-specific API format handler."""
    p = rt["provider"]
    live = [m for m in p["models"] if m not in rt["dead_models"]]
    if not live:
        raise Exception("all_models_dead")

    model = live[rt.get("model_idx", 0) % len(live)]
    rt["model_idx"] = (rt.get("model_idx", 0) + 1) % max(1, len(live) * 2)

    # Convert OpenAI-style messages → Gemini format
    system_text = ""
    contents = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_text += content + "\n"
        else:
            role_g = "user" if role == "user" else "model"
            contents.append({"role": role_g, "parts": [{"text": content}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max(max_tokens, 800),
        },
    }
    if system_text.strip():
        payload["systemInstruction"] = {"parts": [{"text": system_text.strip()}]}

    # Rate limit
    gap = PROVIDER_MIN_GAP.get(p["name"], 1.0)
    elapsed = time.time() - rt.get("last_call", 0)
    if elapsed < gap:
        time.sleep(gap - elapsed)
    rt["limiter"].wait()
    rt["last_call"] = time.time()

    url = f"{p['url']}/{model}:generateContent?key={rt['key']}"
    r = requests.post(url, json=payload, timeout=p["timeout"])

    if r.status_code == 404:
        rt["dead_models"].add(model)
        raise Exception(f"model_gone:{model}")
    if r.status_code == 429:
        raise Exception("rate_limited")
    if r.status_code >= 500:
        raise Exception(f"server_error:{r.status_code}")
    r.raise_for_status()

    try:
        data = r.json()
    except Exception:
        raise Exception(f"bad_json:{r.text[:100]}")

    candidates = data.get("candidates", [])
    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise Exception(f"no_candidates:{str(feedback)[:100]}")

    parts = candidates[0].get("content", {}).get("parts", [])
    content = ""
    for part in parts:
        content += part.get("text", "")
    content = content.strip()

    if not content:
        finish = candidates[0].get("finishReason", "?")
        raise Exception(f"empty_content:finish={finish}")

    return content, model


def _call_provider(rt, messages, max_tokens, temperature, task="default"):
    p = rt["provider"]
    all_models = p["models"]
    live = [m for m in all_models if m not in rt["dead_models"]]
    if not live:
        raise Exception("all_models_dead")

    # Prefer task-specific models if available
    preferred = TASK_MODEL_PREFERENCE.get(task, [])
    candidates = [m for m in preferred if m in live]
    if not candidates:
        # Never use reasoning models for split/prompts
        if task in ("split", "prompts"):
            candidates = [m for m in live if m not in p.get("reasoning_models", set())]
        if not candidates:
            candidates = live

    # Deterministic round-robin
    model = candidates[rt.get("model_idx", 0) % len(candidates)]
    rt["model_idx"] = (rt.get("model_idx", 0) + 1) % max(1, len(candidates) * 2)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max(max_tokens, MIN_TOKENS),
    }

    if model in p["reasoning_models"]:
        payload["reasoning_effort"] = "low"
        payload["include_reasoning"] = False

    headers = {"Content-Type": "application/json"}
    if rt["key"] != "anonymous":
        headers["Authorization"] = f"Bearer {rt['key']}"

    # Global min-gap between calls for this provider
    gap = PROVIDER_MIN_GAP.get(p["name"], 1.0)
    elapsed = time.time() - rt.get("last_call", 0)
    if elapsed < gap:
        time.sleep(gap - elapsed)

    rt["limiter"].wait()
    rt["last_call"] = time.time()
    r = requests.post(p["url"], headers=headers, json=payload, timeout=p["timeout"])

    # ---- ERRORS ----
    if r.status_code in (404, 410):
        rt["dead_models"].add(model)
        raise Exception(f"model_gone:{model}")

    if r.status_code == 429:
        raise Exception("rate_limited")

    if r.status_code >= 500:
        raise Exception(f"server_error:{r.status_code}")

    r.raise_for_status()

    try:
        data = r.json()
    except Exception:
        raise Exception(f"bad_json:{r.text[:100]}")

    if not isinstance(data, dict):
        raise Exception("bad_response_type")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise Exception(f"no_choices:{str(data)[:120]}")

    msg = choices[0].get("message") or {}
    content = (msg.get("content") or "").strip()
    finish = choices[0].get("finish_reason", "?")

    # ---- TRUNCATION CHECK ----
    if not content:
        if finish == "length":
            raise Exception("truncated_length")
        raise Exception(f"empty_content:finish={finish}")

    # If truncated AND output is small, retry with different model
    if finish == "length" and len(content.split()) < 100:
        raise Exception(f"truncated_small:{len(content.split())}w")

    return content, model


def _provider_health(name):
    """Check if provider is currently rate-limited or blocked."""
    now = time.time()
    with GLOBAL_LOCK:
        unblock = GLOBAL_BLACKLIST.get(name, 0)
        if unblock > now:
            return False, unblock - now
    rt = _RUNTIME.get(name)
    if rt and rt["blocked_until"] > now:
        return False, rt["blocked_until"] - now
    return True, 0


def _mark_rate_limited(name, seconds=60):
    with GLOBAL_LOCK:
        GLOBAL_BLACKLIST[name] = time.time() + seconds


def generate(messages, max_tokens=2000, temperature=0.7, verbose=True,
             task="default"):
    """
    Smart fallback: skip rate-limited providers, use next available.
    Never blocks pipeline.
    """
    if not _RUNTIME:
        raise Exception("No providers configured")

    max_tokens = max(max_tokens, MIN_TOKENS)
    errors = []

    order = TASK_ROUTING.get(task, TASK_ROUTING["default"])

    if verbose:
        print(f"    [route:{task}] order={order}")

    for name in order:
        rt = _RUNTIME.get(name)
        if not rt:
            continue

        # Skip if globally rate-limited
        healthy, wait = _provider_health(name)
        if not healthy:
            if verbose:
                print(f"    [{name}] rate-limited ({wait:.0f}s) — skip")
            continue

        for attempt in range(1, 3):
            try:
                if verbose:
                    print(f"    [{name}] attempt {attempt}/2")

                if rt["provider"].get("format") == "gemini":
                    content, model = _call_gemini(rt, messages, max_tokens, temperature)
                else:
                    content, model = _call_provider(rt, messages, max_tokens, temperature, task=task)

                if verbose:
                    m_short = model.split("/")[-1] if "/" in model else model
                    print(f"    [{name}/{m_short}] OK — {len(content.split())} words")
                return content

            except Exception as e:
                err = str(e)
                errors.append(f"{name}: {err}")
                rt["consec_fails"] = rt.get("consec_fails", 0) + 1

                # ---- RATE LIMIT ----
                if "rate_limited" in err:
                    _mark_rate_limited(name, 90)
                    if verbose:
                        print(f"    [{name}] RATE LIMITED — 60s global block")
                    break

                # ---- MODEL GONE ----
                if "model_gone" in err:
                    if verbose:
                        print(f"    [{name}] dead model: {err.split(':')[1] if ':' in err else err}")
                    continue

                # ---- TRUNCATION ----
                if "truncated" in err:
                    if verbose:
                        print(f"    [{name}] truncated — bumping tokens")
                    max_tokens = min(max_tokens + 2000, 6000)
                    continue

                # ---- SERVER ERROR ----
                if "server_error" in err or "timeout" in err.lower():
                    _mark_rate_limited(name, 45)
                    if verbose:
                        print(f"    [{name}] server/timeout — 30s block")
                    break

                if verbose:
                    print(f"    [{name}] attempt {attempt}: {err[:80]}")

                if attempt < 2:
                    time.sleep(1)

    # ============================================================
    # ALL PROVIDERS FAILED — wait for soonest available and retry
    # ============================================================
    if verbose:
        print(f"    [WAIT] All providers unavailable — checking soonest...")

    soonest_wait = None
    for name in order:
        healthy, wait = _provider_health(name)
        if not healthy and wait > 0:
            if soonest_wait is None or wait < soonest_wait:
                soonest_wait = wait

    if soonest_wait is not None and soonest_wait < 120:
        wait_time = min(soonest_wait + 2, 120)
        if verbose:
            print(f"    [WAIT] Sleeping {wait_time:.0f}s for soonest provider...")
        time.sleep(wait_time)

        # Retry once with all providers
        if verbose:
            print(f"    [RETRY] Retrying after wait...")
        for name in order:
            rt = _RUNTIME.get(name)
            if not rt:
                continue
            healthy, _ = _provider_health(name)
            if not healthy:
                continue
            try:
                if verbose:
                    print(f"    [{name}] retry attempt")
                if rt["provider"].get("format") == "gemini":
                    content, model = _call_gemini(rt, messages, max_tokens, temperature)
                else:
                    content, model = _call_provider(rt, messages, max_tokens, temperature, task=task)
                if verbose:
                    print(f"    [{name}] OK after wait — {len(content.split())} words")
                return content
            except Exception as e:
                errors.append(f"retry-{name}: {e}")
                continue

    raise Exception(f"All providers failed: {errors[-3:]}")


def generate_with_retry(messages, max_tokens=2000, temperature=0.7,
                        task="default", max_attempts=5, verbose=True):
    """
    Production retry wrapper. Handles rate limits, timeouts, all failures.
    """
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            if verbose and attempt > 1:
                print(f"    [RETRY {attempt}/{max_attempts}]")
            return generate(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                task=task,
                verbose=verbose,
            )
        except Exception as e:
            last_err = e
            err_str = str(e).lower()

            # Wait time based on failure type
            if "rate_limited" in err_str or "all providers" in err_str:
                wait = 60 + (attempt - 1) * 30
            elif "timeout" in err_str:
                wait = 20 * attempt
            elif "server_error" in err_str:
                wait = 30 * attempt
            else:
                wait = 10 * attempt

            if attempt < max_attempts:
                if verbose:
                    print(f"    [FAIL] attempt {attempt}: {str(e)[:80]}")
                    print(f"    [WAIT] {wait}s before retry...")
                time.sleep(wait)

    raise Exception(f"Failed after {max_attempts} attempts: {last_err}")


def reset_health():
    """Reset health state. Useful for long-running processes."""
    global GLOBAL_BLACKLIST, GLOBAL_RPM_WINDOW
    with GLOBAL_LOCK:
        GLOBAL_BLACKLIST.clear()
        GLOBAL_RPM_WINDOW.clear()


def status():
    out = {}
    now = time.time()
    for name, rt in _RUNTIME.items():
        out[name] = {
            "key_set": bool(rt["key"] and rt["key"] != "anonymous"),
            "total_models": len(rt["provider"]["models"]),
            "dead_models": list(rt["dead_models"]),
            "rpm": rt["provider"]["rpm"],
            "in_window": len(rt["limiter"].window),
            "blocked_for": max(0, rt["blocked_until"] - now),
        }
    return out


if __name__ == "__main__":
    import json
    print("=== Status ===")
    print(json.dumps(status(), indent=2))

    print("\n=== Test: short ===")
    try:
        out = generate([{"role": "user", "content": "Say OK in one word"}], max_tokens=100)
        print(f"Response: {out}")
    except Exception as e:
        print(f"FAILED: {e}")

    print("\n=== Test: normal ===")
    try:
        out = generate(
            [{"role": "user", "content": "Write one sentence about silence in a relationship."}],
            max_tokens=200,
        )
        print(f"Response: {out[:200]}")
    except Exception as e:
        print(f"FAILED: {e}")
