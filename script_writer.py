# script_writer.py v3 — Cloud-only, US English, quality-tuned
# No local LLM. Groq → NVIDIA → Pollinations anonymous.

import os
import re
import json
import time
import random
import requests
from cloud_llm import generate as cloud_generate


# ============================================================
# PATHS
# ============================================================
HOOKS_CANDIDATES = [
    os.path.expanduser("~/.config/opencode/skills/yt-script/hooks.json"),
    os.path.expanduser("~/youtube-agent-skill/skills/yt-script/hooks.json"),
]
VOICE_MD = os.path.expanduser("~/.claude/youtube/voice.md")


# ============================================================
# TOPICS
# ============================================================
# Load niche config
_cfg_path = os.path.join(os.getcwd(), "niche_config.json")
if os.path.exists(_cfg_path):
    with open(_cfg_path, "r", encoding="utf-8") as _f:
        _cfg = json.load(_f)
        DARK_PSYCH_TOPICS = _cfg.get("topics", ["Dark psychology"])
else:
    DARK_PSYCH_TOPICS = [
        "How manipulators use silence as a weapon",
        "Why intelligent people fall for gaslighting",
        "The dark side of being 'too understanding'",
    ]


# ============================================================
# LOADERS
# ============================================================
def load_hook_formulas():
    for path in HOOKS_CANDIDATES:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f).get("hooks", [])
            except Exception:
                pass
    return []


def _is_english_text(s):
    """Reject lines with Hindi/Hinglish/Devanagari."""
    if not s:
        return False
    if any('\u0900' <= c <= '\u097F' for c in s):
        return False
    words = set(w.strip(".,!?;:'\"()[]").lower() for w in s.split())
    hinglish = {"hai", "nahi", "mein", "aur", "ko", "ka", "ke", "se",
                "jo", "vo", "yeh", "kya", "bhi", "ho", "hoga", "tha",
                "thi", "par", "lekin", "kyun", "kaise", "ek", "bahut"}
    return len(words & hinglish) == 0


def load_voice_profile():
    """Return SHORT English-only voice summary. Never raw voice.md."""
    if not os.path.exists(VOICE_MD):
        return ""

    try:
        with open(VOICE_MD, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        return ""

    avoid = []
    use = []

    section = None
    for line in raw.split("\n"):
        stripped = line.strip()
        low = stripped.lower()

        if low.startswith("## words i never use"):
            section = "avoid"
            continue
        if low.startswith("## words i do use"):
            section = "use"
            continue
        if low.startswith("#"):
            section = None
            continue
        if not stripped:
            continue

        if stripped.startswith("-"):
            item = stripped.lstrip("-").strip().strip('"').strip("'")
            # Only keep pure English items
            if item and all(ord(c) < 128 for c in item) and _is_english_text(item):
                if section == "avoid":
                    avoid.append(item)
                elif section == "use":
                    use.append(item)

    parts = [
        "AUDIENCE: A smart English-speaking viewer interested in dark psychology "
        "and human behavior. They bore fast and lose interest in weak openings.",
    ]
    if avoid:
        parts.append("AVOID THESE WORDS: " + ", ".join(avoid[:12]))
    if use:
        parts.append("PREFERRED PHRASES: " + ", ".join(use[:8]))
    parts.append(
        "TONE: Direct, cinematic, second-person. Short sentences. No filler. "
        "No 'hey guys', no 'welcome back'. Start with a hook, end on a haunting note."
    )
    parts.append("LANGUAGE: Pure American English only. No Hindi. No Hinglish.")

    return "\n".join(parts)


# ============================================================
# HOOK SCORING
# ============================================================
FILLER = {"basically","actually","literally","just","really","very","so","kind",
          "sort","like","guys","hey","welcome","today","video","subscribe","channel"}
VAGUE = {"amazing","incredible","insane","crazy","huge","massive","game",
         "changer","secret","powerful","ultimate","best","revolutionary","unbelievable"}
CONCRETE = re.compile(r"\b(\d[\d,.]*\s?(%|k|m|x|s|m|h)?|\$\d|\d+\s?(second|minute|hour|day|week|month|year)s?)\b", re.I)
YOU = re.compile(r"\b(you|your|you're|youre|yourself)\b", re.I)
STAKE = re.compile(r"\b(lose|lost|losing|wasting|waste|quit|fail|broke|broken|cost|risk|before|stop|never|die|dying|dead)\b", re.I)
CURIOSITY = re.compile(r"\b(why|how|what|which|until|before|but|nobody|almost|except|reason|actually|because)\b", re.I)


def _words(t):
    return re.findall(r"[a-z0-9'%$.]+", t.lower())


def _specificity(t):
    w = _words(t)
    if not w: return 0
    nums = len(CONCRETE.findall(t))
    vague = sum(1 for x in w if x in VAGUE)
    filler = sum(1 for x in w if x in FILLER)
    s = 34 + nums * 22 - vague * 16 - filler * 5
    s += min(18, 6 * sum(1 for x in t.split()[1:] if x[:1].isupper()))
    return max(0, min(100, s))


def _address(t):
    n = len(YOU.findall(t))
    first = 30 if YOU.search(" ".join(t.split()[:6])) else 0
    return max(0, min(100, 26 + n * 20 + first))


def _stakes(t):
    n = len(STAKE.findall(t))
    return max(0, min(100, 22 + n * 26 + (14 if CONCRETE.search(t) else 0)))


def _curiosity(t):
    n = len(CURIOSITY.findall(t))
    q = 18 if t.strip().endswith("?") else 0
    closed = -18 if re.search(r"\b(because|so that|which means)\b", t, re.I) else 0
    return max(0, min(100, 24 + n * 17 + q + closed))


def _brevity(t):
    n = len(_words(t))
    if n == 0: return 0
    if 9 <= n <= 24: return 100
    if n < 9: return max(30, 100 - (9 - n) * 11)
    return max(10, 100 - (n - 24) * 7)


def score_hook(text):
    parts = {
        "SPECIFICITY": _specificity(text),
        "ADDRESS": _address(text),
        "STAKES": _stakes(text),
        "CURIOSITY": _curiosity(text),
        "BREVITY": _brevity(text),
    }
    vals = list(parts.values())
    verdict = round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals))
    return parts, verdict


# ============================================================
# HOOKS — generation via cloud
# ============================================================
HOOK_SYSTEM = """You write YouTube hooks for a dark psychology channel.

LANGUAGE: Pure American English only. Never Hindi, Hinglish, or other languages.

A hook is 1-2 spoken sentences, 14-22 words.

Every hook must:
- Start with "You" or "If you" in the first 3 words.
- Name ONE specific behavior the viewer can recognize in themselves.
- Use at least one stake word: lose, losing, before, never, stop, cost, quit, fail.
- End with an open question OR an unresolved statement.

STYLE EXAMPLES:
- "You've been told you're overreacting for years. Here is what is actually happening."
- "You check your phone before answering them. That is not love, that is training."
- "You apologize for things you didn't do. That is what conditioning looks like."
- "You feel crazy in arguments you didn't start. That is exactly the point."
- "You explain yourself three times in one text. Someone taught you that was necessary."

FORBIDDEN:
- Poetry words alone: deceit, descent, depths, shadows, surface.
- Abstract claims without a specific behavior.
- Fewer than 12 words.
- Hindi/Hinglish words.

Output exactly 5 hooks. One per line. No numbering. No quotes. No explanation.
Each hook must approach the topic from a different angle."""


def _parse_hooks(raw):
    if not raw:
        return []
    hooks = []
    for line in raw.split("\n"):
        line = line.strip()
        line = re.sub(r'^\d+[\.\)]\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)
        line = line.strip('"\'`').strip()
        if not line:
            continue
        if not _is_english_text(line):
            continue
        wc = len(line.split())
        if 10 <= wc <= 30:
            hooks.append(line)

    seen = set()
    out = []
    for h in hooks:
        key = " ".join(h.lower().split()[:4])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def generate_hooks(topic, formulas):
    """Cloud-only hooks with score ranking."""
    messages = [
        {"role": "system", "content": HOOK_SYSTEM},
        {"role": "user", "content": f"Topic: {topic}\n\nWrite 5 hooks now."},
    ]

    fallback = [
        "You've been told you're overreacting for years. Here is what is actually happening.",
        "You check your phone before answering them. That is not love, that is training.",
        "You apologize for things you didn't do. That is what conditioning looks like.",
        "You feel crazy in arguments you didn't start. That is exactly the point.",
        "You explain yourself three times in one text. Someone taught you that was necessary.",
    ]

    try:
        print("[HOOK] Cloud generation...")
        raw = cloud_generate(messages, max_tokens=600, temperature=0.9, task="script")
        hooks = _parse_hooks(raw)
        print(f"[HOOK] {len(hooks)} hooks from cloud")
    except Exception as e:
        print(f"[HOOK] Cloud failed: {e}")
        hooks = []

    if len(hooks) < 3:
        print("[HOOK] Using fallback")
        hooks.extend(fallback)

    # Score and rank
    scored = [(h, score_hook(h)[1]) for h in hooks]
    scored.sort(key=lambda x: -x[1])

    seen = set()
    final = []
    for h, s in scored:
        key = " ".join(h.lower().split()[:4])
        if key in seen:
            continue
        seen.add(key)
        final.append((h, s))
        if len(final) >= 5:
            break

    print("\n[HOOK] Ranked:")
    for i, (h, s) in enumerate(final, 1):
        band = "STRONG" if s >= 72 else "WORKABLE" if s >= 55 else "WEAK"
        print(f"  {i}. [{s} {band}] {h[:90]}")

    return [h for h, _ in final]


# ============================================================
# SCRIPT BODY — chunked cloud generation
# ============================================================
SCRIPT_SYSTEM = """You are the narrator of an American dark-psychology YouTube video.

LANGUAGE (ABSOLUTE):
- Write ONLY in standard American English.
- Never write Hindi, Hinglish, Urdu, Devanagari, or any non-English words.
- Every sentence must be pure English.

NARRATION RULES:
- Second person only: "you", "your", "yourself".
- Never first person: no "I", "me", "my", "we", "us", "our".
- Never third-person commentary ("People do X", "They feel Y").
- Do NOT describe rooms, atmosphere, weather, or scene-setting.
- Do NOT write like a novel. This is spoken narration.

VOICE PATTERN:
Every paragraph follows this shape:
  1. "You [specific behavior the viewer will recognize]."
  2. Short sentence naming what that behavior means.
  3. Consequence, mechanism, or origin — still about you.

EXAMPLES:
"You start every sentence with 'I think.' As if your opinion needs a permit. That habit was installed."
"You apologize to strangers for existing. That is what training looks like."
"Watch what you do when someone criticizes you. Do you defend, or do you explain? Explaining is the trained response."
"You replay conversations after they end. Looking for the mistake. There is no mistake. That is the point."

FORBIDDEN:
- Room descriptions, atmosphere, weather.
- First person (I, me, my, we).
- General statements about "people" or "they".
- Fabricated statistics, studies, quotes.
- "Welcome back", "let's begin", "in this video", subscribe pitches.
- Any Hindi/Hinglish words.
- Repeating sentences from the previous section.

CONTINUATION RULES:
- Continue the argument with a NEW observation each paragraph.
- End mid-thought so the next section can continue naturally."""


def _clean_chunk(text):
    """Aggressive cleanup of LLM output."""
    if not text:
        return ""

    text = text.strip()

    # Strip markers
    text = re.sub(r"---BEGIN HOOK---\s*", "", text)
    text = re.sub(r"---END HOOK---\s*", "", text)
    text = re.sub(r"^BEGIN HOOK[:\s]*", "", text, flags=re.M)
    text = re.sub(r"^END HOOK[:\s]*", "", text, flags=re.M)

    # Markdown fences
    text = re.sub(r"^```(?:text|markdown|json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    # Meta prefixes (repeated)
    for _ in range(3):
        text = re.sub(r"^\s*(?:VOICE|NARRATOR|SCRIPT|NARRATION|CHUNK|SECTION|PART)\s*[:\-]\s*\([^)]*\)\s*\n?", "", text, flags=re.I)
        text = re.sub(r"^\s*(?:VOICE|NARRATOR|SCRIPT|NARRATION|CHUNK|SECTION|PART)\s*[:\-]\s*\n?", "", text, flags=re.I)

    # Inline stage directions
    text = re.sub(r"\([^)]{0,80}(?:pause|beat|slow|whisper|echo|breath|softly|quietly|voice|narrator)[^)]{0,60}\)", "", text, flags=re.I)
    text = re.sub(r"\*[^*]{1,100}\*", "", text)
    text = re.sub(r"\[[^\]]{1,100}\]", "", text)

    # "Here's the..." prefixes
    text = re.sub(r"^(here['']?s?\s+the\s+(?:script|narration|continuation|next|rest)[^\n]*\n)", "", text, flags=re.I)
    text = re.sub(r"^(sure|certainly|of course)[,.]?\s*", "", text, flags=re.I)

    # Wrapping quotes
    text = re.sub(r'^\s*["\u201c\u201d\'`]\s*', "", text, flags=re.M)

    # Trailing meta
    text = re.sub(r"\n+(let me know|hope this|is this|would you|feel free)[^\n]*$", "", text, flags=re.I)

    # Line-by-line English filter
    clean_lines = []
    skip_markers = (
        "## who i am", "## how i", "## words i", "## what i", "## my format",
        "voice:", "voice profile", "here is the voice", "style guide",
        "instructions:", "curiosity-driven", "bores fast",
        "let's begin", "lets begin", "expert nahi", "internet mysteries",
    )

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            clean_lines.append(line)
            continue

        low = stripped.lower()

        # Skip markdown headers
        if stripped.startswith("#"):
            continue

        # Skip leakage markers
        if any(m in low for m in skip_markers):
            continue

        # Skip non-English
        if not _is_english_text(stripped):
            continue

        clean_lines.append(line)

    text = "\n".join(clean_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def _chunk_prompt(topic, chunk_num, total_chunks, target_words,
                  prev_tail, voice_summary, hook_line):
    """Build the user prompt for one chunk."""
    if chunk_num == 1:
        context = (
            f"YOUR FIRST SENTENCE MUST BE EXACTLY THIS (word-for-word):\n"
            f"{hook_line}\n\n"
            f"Then continue the narration in second person.\n"
            f"Do NOT describe rooms or settings."
        )
    else:
        context = (
            f"Continue the narration from where the previous section ended.\n\n"
            f"PREVIOUS SECTION ENDING (do NOT repeat any of this):\n"
            f"{prev_tail[-700:]}\n\n"
            f"REQUIREMENTS:\n"
            f"- Stay in second person. Only 'you', 'your'.\n"
            f"- Start with a NEW behavior observation.\n"
            f"- Move the argument forward: new example, deeper mechanism, or escalation.\n"
            f"- No scene-setting, no 'I', no 'people do X'.\n"
        )

    user = f"""Topic: {topic}
Chunk {chunk_num} of {total_chunks}
Target: {target_words} words.

VOICE GUIDANCE:
{voice_summary[:400] if voice_summary else "(neutral documentary narrator)"}

{context}

Write at least {target_words} words of pure narration now."""

    return user


def _generate_chunk(topic, chunk_num, total_chunks, target_words,
                    prev_tail, voice_summary, hook_line):
    """One chunk via cloud, 2 retries, length validated."""
    user = _chunk_prompt(topic, chunk_num, total_chunks, target_words,
                        prev_tail, voice_summary, hook_line)
    messages = [
        {"role": "system", "content": SCRIPT_SYSTEM},
        {"role": "user", "content": user},
    ]

    last_err = None
    for attempt in range(1, 3):
        try:
            print(f"    [chunk {chunk_num}] attempt {attempt}/2")
            raw = cloud_generate(messages, max_tokens=2200, temperature=0.75, task="script")
            text = _clean_chunk(raw)

            if not text or len(text.split()) < 50:
                raise Exception(f"too short: {len(text.split())} words")

            print(f"    [chunk {chunk_num}] {len(text.split())} words")
            return text
        except Exception as e:
            last_err = e
            print(f"    [chunk {chunk_num}] attempt {attempt} failed: {e}")
            if attempt < 2:
                time.sleep(3)

    raise Exception(f"chunk {chunk_num} failed: {last_err}")


def generate_full_script(topic, winning_hook, voice_profile, target_words=3500):
    """Generate full script in chunks via cloud."""
    print(f"[SCRIPT] Target: {target_words} words via cloud")

    chunk_size = 700
    total_chunks = max(4, round(target_words / chunk_size))
    print(f"[SCRIPT] {total_chunks} chunks x ~{chunk_size} words\n")

    chunks = []
    total_so_far = 0

    for i in range(1, total_chunks + 1):
        if total_so_far >= target_words * 0.95:
            print(f"[SCRIPT] Reached {total_so_far} words — done")
            break

        print(f"[SCRIPT] --- Chunk {i}/{total_chunks} ---")
        prev_tail = chunks[-1] if chunks else ""

        try:
            chunk = _generate_chunk(
                topic=topic,
                chunk_num=i,
                total_chunks=total_chunks,
                target_words=chunk_size,
                prev_tail=prev_tail,
                voice_summary=voice_profile,
                hook_line=winning_hook,
            )
            if chunk:
                chunks.append(chunk)
                total_so_far += len(chunk.split())
                print(f"[SCRIPT] Total so far: {total_so_far} words")
        except Exception as e:
            print(f"[SCRIPT] chunk {i} failed: {e}")
            if not chunks:
                raise
            break

    if not chunks:
        raise Exception("[SCRIPT] No chunks generated")

    script = "\n\n".join(chunks)
    wc = len(script.split())

    # Verify hook in first 20 words
    first_20 = " ".join(script.split()[:20]).lower()
    hook_head = " ".join(winning_hook.split()[:4]).lower()
    if hook_head not in first_20:
        print("[SCRIPT] Prepending hook")
        script = winning_hook.strip() + "\n\n" + script
        wc = len(script.split())

    # Final Hindi check
    if any('\u0900' <= c <= '\u097F' for c in script):
        script = "\n".join(
            line for line in script.split("\n")
            if not any('\u0900' <= c <= '\u097F' for c in line)
        )
        wc = len(script.split())

    print(f"\n[SCRIPT] Final: {wc} words (~{wc // 150} min)")
    return script


# ============================================================
# MAIN ENTRY
# ============================================================
def generate_dark_psychology_script(topic=None):
    if topic is None:
        topic = random.choice(DARK_PSYCH_TOPICS)

    print(f"\n{'='*60}")
    print(f"[*] TOPIC: {topic}")
    print(f"{'='*60}")

    formulas = load_hook_formulas()
    print(f"[i] Hook formulas: {len(formulas)}")

    voice_profile = load_voice_profile()

    # Stage 1: Hooks
    print(f"\n[STAGE 1] Hooks...")
    hooks = generate_hooks(topic, formulas)
    if not hooks:
        raise Exception("[X] No hooks produced")

    scored = [(h, score_hook(h)[1]) for h in hooks]
    scored.sort(key=lambda x: -x[1])
    winning = scored[0][0]
    top2 = [h for h, _ in scored[:2]]

    print(f"\n[WINNER] {winning}")
    print(f"[RUNNER-UP] {top2[1] if len(top2) > 1 else 'N/A'}")

    # Stage 2: Full script
    print(f"\n[STAGE 2] Full script...")
    script = generate_full_script(topic, winning, voice_profile, target_words=3500)

    return script, topic, winning, top2


def save_script(script_text):
    path = os.path.join(os.getcwd(), "scripts.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(script_text)
    print(f"[OK] Saved: {path}")
    return path


if __name__ == "__main__":
    script, topic, winning, top2 = generate_dark_psychology_script()
    save_script(script)
    print("\n--- PREVIEW (first 900 chars) ---")
    print(script[:900])
