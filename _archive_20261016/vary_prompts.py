# vary_prompts.py
# Post-process scenes.json to fix repetition and duplicates

import re
import json
import os
from collections import Counter


CAMERA_ROTATION = [
    "Cinematic wide establishing shot",
    "Intimate medium shot",
    "Tight close-up",
    "Over-the-shoulder frame",
    "Medium two-shot",
    "Extreme close-up",
    "Low-angle cinematic frame",
    "High-angle establishing frame",
    "Side-profile medium shot",
    "POV shot",
    "Tight insert shot",
    "Silhouetted wide frame",
    "Tracking-style medium frame",
    "Canted-angle dramatic frame",
    "Slow-burn close-up",
]

LIGHTING_ROTATION = [
    "lit by dim tungsten overhead",
    "under cool window daylight",
    "with blue-hour ambient glow",
    "under harsh fluorescent light",
    "rim-lit from behind",
    "in low-key shadow with a single practical lamp",
    "top-lit by a ceiling fixture",
    "washed in soft overcast daylight",
    "by warm desk-lamp glow",
    "silhouetted against a bright doorway",
    "under muted screen-light from a phone",
    "in high-contrast side lighting",
]


def _tokens(t):
    return re.findall(r"[a-z]+", t.lower())


def fix_duplicates(scenes):
    """Remove or merge duplicate scene texts."""
    seen = {}
    fixed = []
    for s in scenes:
        key = " ".join(_tokens(s["text"])[:8])
        if key in seen:
            # Merge into previous scene
            fixed[seen[key]]["text"] = (
                fixed[seen[key]]["text"] + " " + s["text"]
            ).strip()
            print(f"    [DEDUPE] Merged duplicate scene (id {s['id']}) into previous")
        else:
            seen[key] = len(fixed)
            fixed.append(s)
    return fixed


def fix_prompt_openers(scenes):
    """Replace ALL repetitive prompt openers (>=3 occurrences)."""
    openers = Counter()
    for s in scenes:
        first_6 = " ".join(s["prompt"].split()[:6]).lower()
        openers[first_6] += 1

    # Fix EVERY opener that appears 3+ times
    repeaters = [(op, c) for op, c in openers.most_common() if c >= 3]

    if not repeaters:
        print(f"    [OPENERS] No opener repeats 3+ times — OK")
        return scenes

    print(f"    [OPENERS] Found {len(repeaters)} repetitive openers to fix")

    camera_idx = 0
    total_fixed = 0

    for target_opener, target_count in repeaters:
        count_for_this = 0
        for s in scenes:
            first_6 = " ".join(s["prompt"].split()[:6]).lower()
            if first_6 == target_opener:
                new_cam = CAMERA_ROTATION[camera_idx % len(CAMERA_ROTATION)]
                camera_idx += 1
                rest = " ".join(s["prompt"].split()[5:])
                s["prompt"] = f"{new_cam}, {rest}"
                count_for_this += 1
        print(f"    [OPENERS] '{target_opener[:40]}...' x{target_count} -> varied")
        total_fixed += count_for_this

    print(f"    [OPENERS] Total fixed: {total_fixed} scenes")
    return scenes


def inject_lighting_variety(scenes):
    """Replace generic 'light' words with specific lighting descriptions."""
    total = len(scenes)
    light_count = sum(1 for s in scenes if " light" in s["prompt"].lower() 
                      or s["prompt"].lower().startswith("light"))
    light_ratio = light_count / max(1, total)

    if light_ratio < 0.55:
        print(f"    [LIGHTING] OK ({light_ratio:.0%} scenes mention 'light')")
        return scenes

    print(f"    [LIGHTING] 'light' in {light_ratio:.0%} scenes — aggressive replacement")

    fixed_count = 0
    light_idx = 0

    for i, s in enumerate(scenes):
        prompt = s["prompt"]

        # Skip if already has a specific lighting phrase
        if any(phrase in prompt.lower() for phrase in [
            "tungsten", "blue-hour", "rim-lit", "fluorescent",
            "low-key", "silhouetted", "overcast", "desk-lamp",
            "screen-light", "top-lit", "ceiling fixture", "candle",
            "neon", "headlights", "golden-hour", "ambient glow",
            "practical light", "harsh", "soft diffused", "backlit",
            "underlit", "high-contrast"
        ]):
            continue

        # Replace common generic patterns
        new_light = LIGHTING_ROTATION[light_idx % len(LIGHTING_ROTATION)]
        original = prompt

        for pattern in [
            "warm overhead light", "warm light", "soft window light",
            "soft light", "dim light", "cool light", "cool window light",
            "overhead light", "window light", "natural light",
            "ambient light", "faint light", "pale light", "bright light",
        ]:
            if pattern in prompt.lower():
                prompt = prompt.replace(pattern, new_light)
                prompt = prompt.replace(pattern.capitalize(), new_light)

        # If still has generic light, append specific one
        if prompt == original:
            prompt = prompt.rstrip(".") + f", {new_light}."
        else:
            light_idx += 1

        s["prompt"] = prompt
        fixed_count += 1

    print(f"    [LIGHTING] Fixed {fixed_count} scenes with specific lighting")
    return scenes


def report_variety(scenes):
    """Final variety report."""
    openers = Counter()
    for s in scenes:
        openers[" ".join(s["prompt"].split()[:5]).lower()] += 1

    print(f"\n[VARIETY] After fixes:")
    print(f"    Total scenes: {len(scenes)}")
    print(f"    Unique openers: {len(openers)}")
    print(f"    Most common opener: x{openers.most_common(1)[0][1]}")


if __name__ == "__main__":
    path = "scenes.json"
    if not os.path.exists(path):
        print(f"[X] {path} not found")
        raise SystemExit(1)

    with open(path, encoding="utf-8") as f:
        scenes = json.load(f)

    print(f"[VARY] Loaded {len(scenes)} scenes")

    print("[VARY] Step 1: Fixing duplicates...")
    scenes = fix_duplicates(scenes)

    print("[VARY] Step 2: Fixing repetitive openers...")
    scenes = fix_prompt_openers(scenes)

    print("[VARY] Step 3: Injecting lighting variety...")
    scenes = inject_lighting_variety(scenes)

    # Renumber
    for i, s in enumerate(scenes, start=1):
        s["id"] = i

    with open(path, "w", encoding="utf-8") as f:
        json.dump(scenes, f, indent=2, ensure_ascii=False)

    print(f"[OK] Saved cleaned scenes: {path}")
    report_variety(scenes)
