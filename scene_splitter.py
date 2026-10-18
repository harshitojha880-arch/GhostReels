# scene_splitter.py v5 — Cloud-based story-aware scene splitting
# Groq → NVIDIA → Pollinations fallback

import os
import re
import json
import time
from cloud_llm import generate as cloud_generate


SCRIPT_FILE = "scripts.txt"
OUT_FILE = "scenes_text.json"
BATCH_SIZE_WORDS = 600   # words per LLM call


# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM = """You split narration into cinematic scenes for a YouTube video.

A scene is ONE visual moment — what the viewer sees in a single shot.

RULES:
- Each scene MUST be 10-20 words of narration.
- 10 words = 4 seconds on screen. 20 words = 8 seconds. This is critical.
- NEVER break a sentence in the middle.
- Group 1-2 short sentences together if they describe the same visual beat.
- Preserve the EXACT wording of the narration. Do not rewrite, paraphrase, or summarize.
- Skip nothing — cover every sentence.

FORBIDDEN PHRASES (remove them completely):
- "Let's begin", "Let's get started", "Today we'll", "In this video"
- "We'll be examining", "We'll look at", "We're going to"
- "That's a fundamental setup", "isn't it?" (rhetorical fillers)
- Tutorial/lecture language: "today", "we'll examine", "I'll show you"
- Meta-commentary about the video itself

LANGUAGE:
- Input is pure American English. Output must also be pure American English.
- No Hindi, Hinglish, or any other language.

OUTPUT FORMAT — numbered list, one scene per line:

1. You check your phone before answering them.
2. That is not love, that is training.
3. Three taps, then two seconds of nothing. You wait.

Output MUST include ALL scenes from the input. Do not summarize, skip, or shorten.

Return ONLY the numbered list. No commentary, no headers, no explanation."""


# ============================================================
# HELPERS
# ============================================================
def _is_english(s):
    if not s:
        return False
    if any('\u0900' <= c <= '\u097F' for c in s):
        return False
    words = set(w.strip(".,!?;:'\"()[]").lower() for w in s.split())
    hinglish = {"hai", "nahi", "mein", "aur", "ko", "ka", "ke", "se",
                "jo", "vo", "yeh", "kya", "bhi", "ho", "hoga", "tha",
                "thi", "par", "lekin", "kyun", "kaise", "ek", "bahut"}
    return len(words & hinglish) == 0


def _clean_line(line):
    """Strip numbering, bullets, quotes from a line."""
    line = line.strip()
    line = re.sub(r'^\*{0,2}\[?\s*(\d+)\s*[\.\)\]:\-]\s*\*{0,2}\s*', '', line)
    line = re.sub(r'^[-*•]\s*', '', line)
    line = line.strip('"\'`').strip()
    return line


def _chunk_script(text, max_words=250):
    """Split script into ~250-word chunks at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    chunks, cur, cur_wc = [], [], 0
    for s in sentences:
        wc = len(s.split())
        if cur_wc + wc > max_words and cur:
            chunks.append(" ".join(cur))
            cur, cur_wc = [], 0
        cur.append(s)
        cur_wc += wc
    if cur:
        chunks.append(" ".join(cur))
    return chunks


FORBIDDEN_STARTS = (
    "let's begin", "lets begin", "let's get started",
    "today we", "today we'll", "today i", "today's",
    "in this video", "in today's",
    "we'll be", "we will be", "we're going to",
    "i'll show", "i will show", "i'm going to",
    "that's a fundamental", "that is a fundamental",
    "here ", "sure", "of course", "certainly",
    "chunk", "output", "note:", "next:", "final:",
    "welcome", "hello", "hi everyone", "hey ",
)

FORBIDDEN_META = (
    "what's the next element", "what is the next",
    "next element", "as an ai", "as a language model",
    "i cannot", "i can't", "i'm unable",
    "note:", "output:", "scene:",
    "here is", "here's the",
)

FORBIDDEN_CONTAINS = (
    "we'll be examining", "we will be examining",
    "we'll be looking", "we will look at",
    "in this video", "in today's video",
    "isn't it?", "right?", "you know?",
    "let's dive", "let's jump", "let's begin",
    "we'll examine", "we'll explore", "we'll discuss",
)


def _normalize_apostrophes(t):
    return (t.replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u201c", '"').replace("\u201d", '"'))


def _is_forbidden(t):
    # Normalize curly apostrophes to straight
    low = _normalize_apostrophes(t.lower().strip())
    for p in FORBIDDEN_STARTS:
        if low.startswith(p):
            return True
    for p in FORBIDDEN_CONTAINS:
        if p in low:
            return True
    # Extra patterns for fragments
    if low.startswith("before you ") or low.startswith("or even "):
        # Would-be fragments
        return False
    return False


def _parse_numbered(raw):
    """Parse numbered list, filter garbage, enforce word count."""
    if not raw:
        return []
    scenes = []
    for line in raw.split("\n"):
        cleaned = _clean_line(line)
        if not cleaned:
            continue
        if not _is_english(cleaned):
            continue
        if _is_forbidden(cleaned):
            continue
        # Skip markdown headers
        if cleaned.startswith("#"):
            continue
        wc = len(cleaned.split())
        # Enforce 5-30 word band (10-20 ideal, but allow slight variance)
        if wc < 5 or wc > 30:
            continue
        scenes.append(cleaned)
    return scenes


# ============================================================
# SPLIT ONE CHUNK
# ============================================================
def _split_chunk(chunk, chunk_num, total_chunks, prev_scenes):
    """One LLM call to split a chunk into scenes."""
    # Build context: last 2 scenes from previous chunk
    context = ""
    if prev_scenes:
        context = "Previous chunk ended with:\n"
        for s in prev_scenes[-2:]:
            context += f"  - {s}\n"
        context += "\nContinue from there. Do NOT repeat these.\n\n"

    user = f"""{context}Split this narration into scenes.

NARRATION:
{chunk}

Output numbered list of scenes (10-20 words each)."""

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]

    for attempt in range(1, 6):  # 5 attempts
        try:
            print(f"    [{chunk_num}/{total_chunks}] LLM attempt {attempt}")
            raw = cloud_generate(messages, max_tokens=4000, temperature=0.4, task="split")
            scenes = _parse_numbered(raw)
            if scenes:
                return scenes
            raise Exception("parser returned 0 scenes")
        except Exception as e:
            err = str(e)
            print(f"    [{chunk_num}/{total_chunks}] failed: {err[:100]}")
            # Rate-limited or all failed → wait longer
            if "rate_limited" in err.lower() or "all providers" in err.lower():
                wait = 90 + (attempt - 1) * 30  # 90, 120, 150...
                print(f"    [{chunk_num}/{total_chunks}] — waiting {wait}s")
                time.sleep(wait)
            elif attempt < 5:
                time.sleep(5)

    return []


# ============================================================
# PYTHON FALLBACK
# ============================================================
def _python_fallback_split(chunk):
    """If LLM fails: split by sentence, pack to ~15 words."""
    sents = re.split(r'(?<=[.!?])\s+', chunk.strip())
    scenes = []
    buf, buf_wc = [], 0

    for s in sents:
        wc = len(s.split())
        # If sentence itself is over 22 words, split at commas
        if wc > 22:
            parts = re.split(r'(?<=[,;])\s+', s)
            if len(parts) > 1:
                for p in parts:
                    pwc = len(p.split())
                    if buf_wc + pwc > 20 and buf_wc >= 10:
                        scenes.append(" ".join(buf))
                        buf, buf_wc = [], 0
                    buf.append(p)
                    buf_wc += pwc
                continue

        if buf_wc + wc > 20 and buf_wc >= 10:
            scenes.append(" ".join(buf))
            buf, buf_wc = [], 0
        buf.append(s)
        buf_wc += wc

    if buf:
        scenes.append(" ".join(buf))

    return scenes


# ============================================================
# MAIN
# ============================================================
def build_scenes(script_text):
    # Clean script first
    script_text = script_text.strip()

    chunks = _chunk_script(script_text, max_words=BATCH_SIZE_WORDS)
    total_chunks = len(chunks)
    total_words = len(script_text.split())

    print(f"[SPLIT] Script: {total_words} words | Chunks: {total_chunks} (~{BATCH_SIZE_WORDS}w each)")

    all_scenes = []
    llm_ok = 0
    fallback_used = 0

    for i, chunk in enumerate(chunks, 1):
        wc = len(chunk.split())
        print(f"\n[CHUNK {i}/{total_chunks}] ({wc} words)")

        scenes = _split_chunk(chunk, i, total_chunks, all_scenes[-2:])

        if not scenes:
            print(f"    [FALLBACK] Python split")
            scenes = _python_fallback_split(chunk)
            fallback_used += 1
        else:
            llm_ok += 1

        print(f"    -> {len(scenes)} scenes")
        all_scenes.extend(scenes)

    # ---- Post-process: merge short, split long, dedupe, filter ----
    final = []

    # Step A: clean each scene
    cleaned = []
    for s in all_scenes:
        s = s.strip()
        if not s:
            continue
        if not _is_english(s):
            continue
        # Skip forbidden (normalizes apostrophes internally)
        if _is_forbidden(s):
            continue
        wc = len(s.split())
        if wc < 4:
            continue
        cleaned.append(s)

    # Step B: merge consecutive short scenes until each meets MIN_WORDS
    MIN_WORDS = 10  # hard minimum  # hard minimum
    MAX_WORDS = 22

    merged = []
    for s in cleaned:
        wc = len(s.split())

        # If short and previous exists, try to merge with previous
        if wc < MIN_WORDS and merged:
            prev = merged[-1]
            prev_wc = len(prev.split())
            combined = prev + " " + s
            combined_wc = len(combined.split())
            if combined_wc <= MAX_WORDS:
                merged[-1] = combined
                continue
            else:
                # Can't merge with prev — hold as pending
                merged.append(s)
                continue

        merged.append(s)

    # Step B2: forward pass — if previous is short, try merging with next
    final_pass = []
    i = 0
    while i < len(merged):
        s = merged[i]
        wc = len(s.split())

        if wc < MIN_WORDS and i + 1 < len(merged):
            next_s = merged[i + 1]
            combined = s + " " + next_s
            if len(combined.split()) <= MAX_WORDS:
                final_pass.append(combined)
                i += 2
                continue

        final_pass.append(s)
        i += 1

    # Step B3: last-resort — attach any remaining short fragment to previous
    fixed = []
    for s in final_pass:
        if len(s.split()) < 6 and fixed:
            # Too small — attach to previous
            combined = fixed[-1] + " " + s
            if len(combined.split()) <= MAX_WORDS + 5:
                fixed[-1] = combined
                continue
        fixed.append(s)

    # Step C: STRICT split long scenes (> 22 words)
    split_pass = []
    for s in final_pass:
        wc = len(s.split())
        if wc <= 22:
            split_pass.append(s)
            continue

        # Try splitting at sentence boundaries first
        parts = re.split(r'(?<=[.!?])\s+', s)
        if len(parts) > 1:
            buf, buf_wc = [], 0
            for p in parts:
                pwc = len(p.split())
                if buf_wc + pwc > 20 and buf_wc >= 10:
                    split_pass.append(" ".join(buf).strip())
                    buf, buf_wc = [], 0
                buf.append(p)
                buf_wc += pwc
            if buf:
                split_pass.append(" ".join(buf).strip())
            continue

        # No sentence boundary — split at commas/semicolons
        parts = re.split(r'(?<=[,;:])\s+', s)
        if len(parts) > 1:
            buf, buf_wc = [], 0
            for p in parts:
                pwc = len(p.split())
                if buf_wc + pwc > 20 and buf_wc >= 10:
                    split_pass.append(" ".join(buf).strip())
                    buf, buf_wc = [], 0
                buf.append(p)
                buf_wc += pwc
            if buf:
                split_pass.append(" ".join(buf).strip())
            continue

        # Last resort: split at word boundary mid-sentence
        words = s.split()
        mid = len(words) // 2
        split_pass.append(" ".join(words[:mid]).strip() + ",")
        split_pass.append(" ".join(words[mid:]).strip())

    # Step D: final cleanup — merge tiny, dedupe
    intermediate = []
    for s in split_pass:
        s = s.strip()
        if not s:
            continue
        wc = len(s.split())

        # If < 8 words, merge with previous
        if wc < 8 and intermediate:
            prev = intermediate[-1]
            combined = prev + " " + s
            if len(combined.split()) <= 24:
                intermediate[-1] = combined
                continue

        # If > 25 words still, hard truncate at sentence boundary
        if wc > 25:
            words = s.split()
            s = " ".join(words[:22]).rstrip(",;:") + "."

        intermediate.append(s)

    # Dedupe
    seen = set()
    for s in intermediate:
        if not s:
            continue
        if len(s.split()) < 5:
            continue
        key = " ".join(s.lower().split()[:6])
        if key in seen:
            continue
        seen.add(key)
        final.append(s)

    # ---- Verify coverage + auto-recover missing content ----
    script_sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())

    def _norm_words(t):
        return set(re.findall(r"[a-z']+", t.lower()))

    scene_word_set = set()
    for s in final:
        scene_word_set.update(_norm_words(s))

    # Find sentences whose words are mostly missing from scenes
    missing_sentences = []
    for sent in script_sentences:
        sent_words = _norm_words(sent)
        if len(sent_words) < 3:
            continue
        # If fewer than 50% of sentence's words appear in scenes → missing
        present = len(sent_words & scene_word_set)
        if present / len(sent_words) < 0.5:
            missing_sentences.append(sent.strip())

    if missing_sentences:
        print(f"\n[SPLIT] [RECOVER] {len(missing_sentences)} sentences missing — attempting LLM re-run")

        # Try to recover via LLM first (before falling back to raw insertion)
        recovered = []
        for sent in missing_sentences[:8]:  # max 8 recovery calls
            if _is_forbidden(sent) or not _is_english(sent):
                continue
            wc = len(sent.split())
            if wc < 5:
                continue

            # Try to split this sentence with LLM
            try:
                user_msg = f"Split into 1-3 scenes (10-20 words each). Output numbered list only:\n\n{sent}"
                raw = cloud_generate(
                    [{"role": "user", "content": user_msg}],
                    max_tokens=500,
                    temperature=0.3,
                    task="split",
                )
                sub_scenes = _parse_numbered(raw)
                if sub_scenes:
                    recovered.extend(sub_scenes)
                    print(f"    [RECOVER] Split: {sent[:50]}... -> {len(sub_scenes)} scenes")
                    continue
            except Exception as e:
                print(f"    [RECOVER] LLM failed: {str(e)[:60]}")

            # Fallback: add the sentence directly
            recovered.append(sent.strip())

        if recovered:
            print(f"[SPLIT] [RECOVER] Added {len(recovered)} scenes via LLM")
            final.extend(recovered)

        # OLD recover block continues with raw insertion for anything left

        # Add recovered sentences to final
        for sent in missing_sentences:
            # Skip forbidden/garbage
            if _is_forbidden(sent):
                continue
            if not _is_english(sent):
                continue
            wc = len(sent.split())
            if wc < 4:
                continue
            final.append(sent.strip())

        # Re-sort: preserve original script order approximately by
        # matching first occurrence in script
        def sort_key(scene_text):
            idx = script_text.lower().find(scene_text[:30].lower())
            return idx if idx >= 0 else 999999
        final.sort(key=sort_key)
        print(f"[SPLIT] [RECOVER] Final count: {len(final)}")

    # Recompute coverage
    script_words = _norm_words(script_text)
    scene_words = set()
    for s in final:
        scene_words.update(_norm_words(s))
    coverage = len(scene_words & script_words) / max(1, len(script_words)) * 100

    # ---- Stats ----
    lengths = [len(s.split()) for s in final]
    if not lengths:
        raise Exception("[X] No scenes produced")

    print(f"\n[SPLIT] === RESULTS ===")
    print(f"[SPLIT] Total scenes: {len(final)}")
    print(f"[SPLIT] Length: min={min(lengths)} avg={sum(lengths)/len(lengths):.1f} max={max(lengths)}")
    print(f"[SPLIT] Coverage: {coverage:.1f}%")
    print(f"[SPLIT] LLM chunks OK: {llm_ok}/{total_chunks}")
    print(f"[SPLIT] Fallback chunks: {fallback_used}/{total_chunks}")

    # Build output
    scenes_json = [
        {"id": i + 1, "text": s}
        for i, s in enumerate(final)
    ]

    return scenes_json


if __name__ == "__main__":
    if not os.path.exists(SCRIPT_FILE):
        raise SystemExit(f"[X] {SCRIPT_FILE} not found")

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        script = f.read().strip()

    t0 = time.time()
    scenes = build_scenes(script)
    dt = time.time() - t0

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Saved: {OUT_FILE} ({dt:.1f}s)")
    print("\n--- FIRST 8 SCENES ---")
    for s in scenes[:8]:
        print(f"[{s['id']}] ({len(s['text'].split())}w) {s['text'][:110]}")
    print("\n--- LAST 3 SCENES ---")
    for s in scenes[-3:]:
        print(f"[{s['id']}] ({len(s['text'].split())}w) {s['text'][:110]}")
