# scene_builder.py
# Chunked LLM scene splitting + per-scene cinematic prompt generation
# STRICT: 25-45 words per scene

import os
import re
import json
import time
import random
import requests

POLLINATIONS_KEY = os.environ.get("POLLINATIONS_KEY", "")
API_URL = "https://gen.pollinations.ai/v1/chat/completions"


def _call_llm(system, user, max_tokens=8000, temperature=0.55, retries=3):
    if not POLLINATIONS_KEY:
        raise Exception("[X] POLLINATIONS_KEY not set. Run: source ~/.bashrc")

    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": random.randint(1, 999999),
    }
    headers = {
        "Authorization": f"Bearer {POLLINATIONS_KEY}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            print(f"    [NET] attempt {attempt}/{retries}")
            r = requests.post(API_URL, headers=headers, json=payload, timeout=300)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = e
            print(f"    [!] failed: {e}")
            if attempt < retries:
                time.sleep(4 * attempt)

    raise Exception(f"[X] LLM failed: {last_err}")


def _extract_json_array(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)

    start = text.find("[")
    if start < 0:
        raise Exception("No '[' found")

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1])

    # Recovery
    tail = text[start:]
    last_close = tail.rfind("}")
    if last_close > 0:
        try:
            return json.loads(tail[:last_close+1] + "]")
        except Exception:
            pass
    raise Exception("Unbalanced JSON")


def _split_script_into_chunks(script_text, chunk_words=500):
    sentences = re.split(r"(?<=[.!?])\s+", script_text.strip())
    chunks = []
    current = []
    current_words = 0

    for s in sentences:
        wc = len(s.split())
        if current_words + wc > chunk_words and current:
            chunks.append(" ".join(current).strip())
            current = []
            current_words = 0
        current.append(s)
        current_words += wc

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


SCENE_SYSTEM = """You are a cinematic scene director for a dark-psychology YouTube video.

TASK:
Split the given narration chunk into 10-14 visual scenes. Each scene MUST be
a substantial visual beat, not a fragment.

ABSOLUTE SPLITTING RULES (do not violate):
- Each scene MUST contain 25 to 45 words of narration.
- DO NOT create scenes with fewer than 22 words. Ever.
- DO NOT create scenes with more than 50 words.
- NEVER split mid-sentence. Only split at natural sentence boundaries.
- Each scene = 1 to 3 complete sentences forming ONE visual beat.
- Preserve EXACT narration wording. Do not paraphrase, rewrite, or reorder.
- Cover the ENTIRE chunk. Do not skip anything.

EXAMPLE OF CORRECT SCENE LENGTH (35 words):
"You're standing across a kitchen table while someone slides a phone toward you like evidence. Their thumb taps once, then twice, as if the screen is a witness. But the timestamp is almost right."

EXAMPLE OF FORBIDDEN (too short — 8 words):
"You're standing across a kitchen table."

VISUAL PROMPT RULES (for each scene):

OPENING VARIETY (CRITICAL):
- NEVER start more than 2 prompts in the entire output with the same words.
- Do NOT default to "Photorealistic cinematic film still" or
  "Photorealistic cinematic still". Vary the opening:
    * "Cinematic wide shot..."
    * "Intimate close-up..."
    * "Medium two-shot..."
    * "Over-the-shoulder frame..."
    * "Low-angle shot..."
    * "High-angle establishing frame..."
    * "Side-profile shot..."
    * "POV frame..."
    * "Tight insert shot..."
    * "Silhouetted wide frame..."
- Rotate through these openings across scenes.

CAMERA VARIETY (CRITICAL):
Across every 10 scenes, use AT LEAST 6 different shot types:
wide establishing, medium, close-up, extreme close-up, over-the-shoulder,
two-shot, POV, low-angle, high-angle, insert shot, silhouette shot,
side-profile, tracking-style frame.
Do NOT let one shot type dominate more than 25% of scenes.

LOCATION VARIETY (CRITICAL):
Do NOT keep all scenes indoors. Alternate between:
- interior (kitchen, bedroom, office, hallway, bathroom, living room)
- exterior (street, parking lot, café patio, car interior, park, doorway, stairwell)
- transitional (elevator, corridor, doorway threshold, staircase)
At least 25% of scenes must be in a distinctly different location from
the previous scene. Repeat locations only when narration explicitly
returns to the same place.

LIGHTING VARIETY (CRITICAL):
Do NOT default to "light" in every prompt. Rotate through:
- source of light: overhead, window, screen glow, lamp, neon, candle,
  headlights, phone screen, dim daylight, ambient dusk
- quality: hard, soft, warm, cool, golden-hour, blue-hour, tungsten,
  fluorescent, natural overcast
- mood: low-key, high-contrast, silhouetted, rim-lit, underlit, top-lit

SUBJECT / ACTION:
- Literal depiction of what this specific narration describes.
- If a person is mentioned, show them. If an action is described, show the action.
- If two+ people interact, show both in the same frame.
- Include: subject(s), action, environment, lighting, mood, camera angle.
- Photorealistic cinematic still, 16:9 composition, film quality.
- Dark psychological drama aesthetic: controlled shadows, cinematic depth,
  natural skin texture, believable physical environment.
- FORBIDDEN: text, captions, subtitles, logos, watermarks, diagrams, infographics,
  generic brain imagery, abstract concept art, stock-photo look, mood-board look.
- 55-85 words per visual prompt. Specific. Restrained. Cinematic.
- Do NOT repeat the same framing, same room, or same lighting setup
  as the previous scene.

OUTPUT FORMAT — strict JSON array, no markdown:
[
  {"text": "25-45 word narration chunk here", "prompt": "cinematic image prompt here"},
  ...
]

Return ONLY the JSON array."""


def _process_chunk(chunk_text, chunk_index, total_chunks):
    user = f"""Chunk {chunk_index}/{total_chunks} of the narration.
Expected output: 10-14 scenes. Each scene MUST be 25-45 words.

NARRATION CHUNK:
{chunk_text}

Produce the JSON array now."""

    raw = _call_llm(SCENE_SYSTEM, user, max_tokens=8000, temperature=0.55)
    data = _extract_json_array(raw)

    scenes = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not text or not prompt:
            continue
        scenes.append({"text": text, "prompt": prompt})

    # Post-process: merge scenes that are too short (<22 words)
    merged = []
    buffer_text = ""
    buffer_prompt = ""

    for s in scenes:
        wc = len(s["text"].split())
        if wc < 22 and buffer_text:
            buffer_text = buffer_text + " " + s["text"]
            # Keep the more detailed prompt
            if len(s["prompt"]) > len(buffer_prompt):
                buffer_prompt = s["prompt"]
            # If buffer now in range, flush
            if len(buffer_text.split()) >= 25:
                merged.append({"text": buffer_text.strip(), "prompt": buffer_prompt})
                buffer_text = ""
                buffer_prompt = ""
        else:
            if buffer_text:
                merged.append({"text": buffer_text.strip(), "prompt": buffer_prompt})
                buffer_text = ""
                buffer_prompt = ""
            if wc < 22:
                buffer_text = s["text"]
                buffer_prompt = s["prompt"]
            else:
                merged.append(s)

    if buffer_text:
        if merged:
            merged[-1]["text"] = merged[-1]["text"] + " " + buffer_text
        else:
            merged.append({"text": buffer_text, "prompt": buffer_prompt})

    return merged


def smart_split_scenes(script_text):
    chunks = _split_script_into_chunks(script_text, chunk_words=500)

    print(f"[SCENE] Script: {len(script_text.split())} words | "
          f"Chunks: {len(chunks)}")

    all_scenes = []
    for i, chunk in enumerate(chunks, start=1):
        print(f"[CHUNK {i}/{len(chunks)}] {len(chunk.split())} words")
        try:
            chunk_scenes = _process_chunk(chunk, i, len(chunks))
            print(f"    -> {len(chunk_scenes)} scenes")
            all_scenes.extend(chunk_scenes)
        except Exception as e:
            print(f"    [X] Chunk {i} primary failed: {e}")
            print(f"    [~] Retrying chunk {i} with smaller sub-chunks...")
            # Split chunk into 2 halves and retry each separately
            sentences = re.split(r"(?<=[.!?])\s+", chunk)
            mid = len(sentences) // 2
            halves = [
                " ".join(sentences[:mid]).strip(),
                " ".join(sentences[mid:]).strip(),
            ]
            for half_idx, half in enumerate(halves, 1):
                if not half.strip():
                    continue
                try:
                    sub_scenes = _process_chunk(half, f"{i}.{half_idx}", len(chunks))
                    print(f"        half {half_idx}: {len(sub_scenes)} scenes")
                    all_scenes.extend(sub_scenes)
                except Exception as e2:
                    print(f"        half {half_idx} failed too: {e2}")
                    # Final fallback: manual sentence grouping
                    sents = re.split(r"(?<=[.!?])\s+", half)
                    buf, buf_wc = [], 0
                    for s in sents:
                        buf.append(s)
                        buf_wc += len(s.split())
                        if buf_wc >= 30:
                            txt = " ".join(buf).strip()
                            all_scenes.append({
                                "text": txt,
                                "prompt": (
                                    "Photorealistic cinematic film still, dark psychological "
                                    "drama aesthetic, controlled dramatic lighting, realistic "
                                    "human subject and environment, 16:9 composition. "
                                    f"Scene depicts: {txt}"
                                ),
                            })
                            buf, buf_wc = [], 0
                    if buf:
                        txt = " ".join(buf).strip()
                        all_scenes.append({
                            "text": txt,
                            "prompt": (
                                "Photorealistic cinematic film still, dark psychological "
                                "drama aesthetic, controlled dramatic lighting, realistic "
                                "human subject and environment, 16:9 composition. "
                                f"Scene depicts: {txt}"
                            ),
                        })

    for i, s in enumerate(all_scenes, start=1):
        s["id"] = i

    original_words = set(w.lower() for w in re.findall(r"\w+", script_text))
    scene_words = set()
    for s in all_scenes:
        scene_words.update(w.lower() for w in re.findall(r"\w+", s["text"]))
    coverage = len(scene_words & original_words) / max(1, len(original_words)) * 100

    # Report scene length stats
    lengths = [len(s["text"].split()) for s in all_scenes]
    if lengths:
        avg = sum(lengths) / len(lengths)
        print(f"\n[SCENE] Total scenes: {len(all_scenes)}")
        print(f"[SCENE] Word coverage: {coverage:.1f}%")
        print(f"[SCENE] Scene length: min={min(lengths)} avg={avg:.1f} max={max(lengths)}")

    return all_scenes


def save_scenes(scenes, path="scenes.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved: {path}")
    return path


if __name__ == "__main__":
    with open("scripts.txt", "r", encoding="utf-8") as f:
        script = f.read().strip()

    scenes = smart_split_scenes(script)
    save_scenes(scenes)

    print("\n--- FIRST 3 SCENES ---")
    for s in scenes[:3]:
        print(f"\n[SCENE {s['id']}] ({len(s['text'].split())} words)")
        print(f"TEXT:   {s['text'][:200]}")
        print(f"PROMPT: {s['prompt'][:240]}...")

    print(f"\n--- LAST SCENE ---")
    s = scenes[-1]
    print(f"[SCENE {s['id']}] ({len(s['text'].split())} words)")
    print(f"TEXT:   {s['text'][:200]}")
    print(f"PROMPT: {s['prompt'][:240]}...")
