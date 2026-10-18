# prompt_builder.py v4 — LLM-based, scene-specific prompts
# Local Qwen first (short task) → Groq → Gemini → NVIDIA

import os
import re
import json
import time
from cloud_llm import generate as cloud_generate, generate_with_retry


SCENES_FILE = "scenes_text.json"
OUT_FILE = "scenes.json"
BATCH_SIZE = 12


SYSTEM_PROMPT = """You write cinematic image prompts for a dark-psychology YouTube video.

For each scene, write ONE image prompt that LITERALLY shows what the scene says.
Output format: "<id>. <prompt>"

RULES:
- Show the SPECIFIC action, person, object, or environment from the narration.
- If the narration says "you check your phone", show a hand holding a phone.
- If it says "they pass without eye contact", show two people — one passing, one still.
- If it says "your jaw tightens", show a face with a tightened jaw.
- Convert "you" to "a person" or "a man/woman".
- Include: subject + action + environment + lighting + camera angle.
- Photorealistic cinematic still, 16:9, shallow depth of field, film quality.
- Dark psychological drama aesthetic, controlled shadows.
- 50-70 words per prompt.
- Vary camera angle across scenes (wide/medium/close/over-shoulder/POV/low-angle).
- No text, captions, logos, watermarks, diagrams, brain imagery, abstract art.

EXAMPLE:
1. Medium shot of a woman at a dim kitchen counter at night, phone face-down beside her, hands still, cold blue window light, tension in shoulders, photorealistic, 16:9.
2. Close-up of a man's face at a dinner table, jaw tightened, eyes avoiding contact, warm tungsten overhead, muted colors, cinematic depth.

OUTPUT: only numbered lines, one per scene. No commentary, no headers."""


def _llm_prompts(batch_text, verbose=True):
    """One LLM call for a batch of scenes."""
    user = f"""Write ONE image prompt for each scene below.

SCENES:
{batch_text}

Numbered list now:"""

    try:
        return generate_with_retry(
            [{"role": "system", "content": SYSTEM_PROMPT},
             {"role": "user", "content": user}],
            max_tokens=2500,
            temperature=0.6,
            task="prompts",
            max_attempts=5,
            verbose=verbose,
        )
    except Exception as e:
        print(f"    [PROMPT] LLM failed: {str(e)[:100]}")
        return ""


def _parse_numbered(text, expected_ids):
    """Parse numbered list. Return {id: prompt}."""
    result = {}
    if not text:
        return result

    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r'^\*{0,2}\[?\s*(\d+)\s*[\.\)\]:\-]\s*\*{0,2}\s*(.+)$', line)
        if not m:
            continue
        try:
            sid = int(m.group(1))
        except Exception:
            continue
        if sid not in expected_ids:
            continue
        prompt = m.group(2).strip().strip("*").strip('"\'').strip()
        if not prompt:
            continue
        # Word count sanity
        wc = len(prompt.split())
        if wc < 15 or wc > 120:
            continue
        result[sid] = prompt

    return result


def _fallback_prompt(scene):
    """Simple fallback if LLM completely fails on a scene."""
    txt = scene["text"]
    txt = re.sub(r"\byou're\b", "a person is", txt, flags=re.I)
    txt = re.sub(r"\byou are\b", "a person is", txt, flags=re.I)
    txt = re.sub(r"\byour\b", "their", txt, flags=re.I)
    txt = re.sub(r"\byou\b", "a person", txt, flags=re.I)
    txt = re.sub(r"\s+", " ", txt).strip()
    if len(txt) > 180:
        txt = txt[:180].rsplit(" ", 1)[0] + "."
    return (
        f"Photorealistic cinematic film still depicting: {txt} "
        f"Dark psychological drama aesthetic, controlled shadows, "
        f"shallow depth of field, 16:9 composition."
    )


def build_prompts(scenes):
    total = len(scenes)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    print(f"[PROMPT] Scenes: {total} | Batches: {total_batches} (batch {BATCH_SIZE})")
    print(f"[PROMPT] Starting...\n")

    t0 = time.time()
    llm_used = 0
    fallback_used = 0

    for b in range(total_batches):
        start = b * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = scenes[start:end]
        batch_num = b + 1

        # Build input for LLM
        lines = []
        for s in batch:
            txt = s["text"]
            if len(txt) > 300:
                txt = txt[:300].rsplit(" ", 1)[0] + "..."
            lines.append(f'{s["id"]}. "{txt}"')
        batch_text = "\n".join(lines)

        print(f"[BATCH {batch_num}/{total_batches}] scenes {start+1}-{end}")

        expected_ids = set(s["id"] for s in batch)
        raw = _llm_prompts(batch_text)
        parsed = _parse_numbered(raw, expected_ids)

        print(f"    [batch {batch_num}] got {len(parsed)}/{len(batch)} prompts")

        for s in batch:
            if s["id"] in parsed:
                p = parsed[s["id"]]
                if "16:9" not in p.lower() and "photorealistic" not in p.lower():
                    p += " 16:9 cinematic, film quality."
                s["prompt"] = p
                llm_used += 1
            else:
                s["prompt"] = _fallback_prompt(s)
                fallback_used += 1

        # Save incrementally so dashboard sees progress
        try:
            with open(OUT_FILE, "w", encoding="utf-8") as f:
                json.dump(scenes, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        elapsed = time.time() - t0
        done = end
        rate = done / max(elapsed, 0.1)
        eta = (total - done) / rate if rate > 0 else 0
        print(f"[PROMPT] {done}/{total} | {rate*60:.1f}/min | ETA {int(eta)}s\n")

    return scenes, llm_used, fallback_used


if __name__ == "__main__":
    if not os.path.exists(SCENES_FILE):
        raise SystemExit(f"[X] {SCENES_FILE} not found. Run scene_splitter.py first.")

    with open(SCENES_FILE, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    scenes, llm_used, fb_used = build_prompts(scenes)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Saved: {OUT_FILE}")
    print(f"[OK] LLM: {llm_used} | Fallback: {fb_used}")

    print("\n--- FIRST 3 SCENES ---")
    for s in scenes[:3]:
        print(f"\n[{s['id']}] ({len(s['text'].split())}w)")
        print(f"TEXT:   {s['text'][:120]}")
        print(f"PROMPT: {s['prompt'][:220]}...")

    print("\n--- MIDDLE SCENE ---")
    s = scenes[len(scenes) // 2]
    print(f"[{s['id']}] ({len(s['text'].split())}w)")
    print(f"TEXT:   {s['text'][:120]}")
    print(f"PROMPT: {s['prompt'][:220]}...")
