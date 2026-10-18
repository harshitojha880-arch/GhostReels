# repetition_check.py
# Detects repetition in scripts and scene prompts

import re
import json
from collections import Counter


STOPWORDS = set("""
a an the and or but if so then of to in on at for from with by is are was were
be been being has have had do does did will would could should may might must
this that these those it its as not no nor you your yours yourself i me my mine
he she they them their we us our ours what which who whom when where why how
""".split())


def _tokens(text):
    return [
        w.lower()
        for w in re.findall(r"[a-zA-Z']+", text)
        if w.lower() not in STOPWORDS and len(w) > 3
    ]


def check_script(script_text, top_n=15):
    """Return most repeated non-stopword terms in the script."""
    tokens = _tokens(script_text)
    counter = Counter(tokens)
    print(f"\n[REP] Script length: {len(tokens)} content words")
    print(f"[REP] Top {top_n} repeated words:")
    for word, count in counter.most_common(top_n):
        ratio = count / max(1, len(tokens)) * 100
        flag = " <<<" if ratio > 1.5 else ""
        print(f"    {word:<20} x{count:<4} ({ratio:.2f}%){flag}")

    # Repeated bigrams (2-word phrases)
    words = re.findall(r"[a-zA-Z']+", script_text.lower())
    bigrams = Counter(
        f"{words[i]} {words[i+1]}"
        for i in range(len(words) - 1)
        if words[i] not in STOPWORDS and words[i+1] not in STOPWORDS
    )
    repeated_phrases = [(b, c) for b, c in bigrams.most_common(10) if c >= 3]
    if repeated_phrases:
        print(f"\n[REP] Repeated 2-word phrases (3+ times):")
        for phrase, count in repeated_phrases:
            print(f"    '{phrase}' x{count}")

    return counter, repeated_phrases


def check_scenes(scenes_json_path="scenes.json"):
    """Check repetition across scene image prompts."""
    with open(scenes_json_path, encoding="utf-8") as f:
        scenes = json.load(f)

    print(f"\n[REP] Analyzing {len(scenes)} scene prompts")

    prompts = [s["prompt"].lower() for s in scenes]

    # Repeated opening phrases
    openers = Counter()
    for p in prompts:
        first_words = " ".join(p.split()[:4])
        openers[first_words] += 1

    print(f"[REP] Most common prompt openings:")
    for op, count in openers.most_common(8):
        flag = " <<<" if count >= 3 else ""
        print(f"    '{op}' x{count}{flag}")

    # Repeated camera/shot phrases
    camera_phrases = [
        "medium shot", "close-up", "wide shot", "over-the-shoulder",
        "extreme close", "two-shot", "full shot", "establishing shot",
        "photorealistic cinematic still", "photorealistic still",
    ]
    camera_counts = Counter()
    for p in prompts:
        for cam in camera_phrases:
            if cam in p:
                camera_counts[cam] += 1

    print(f"\n[REP] Camera phrase usage across {len(scenes)} scenes:")
    for cam, count in camera_counts.most_common():
        ratio = count / len(scenes) * 100
        flag = " <<<" if ratio > 40 else ""
        print(f"    {cam:<35} {count:>3} ({ratio:.0f}%){flag}")

    # Duplicate text chunks
    texts = [s["text"].lower().strip() for s in scenes]
    dupes = [t for t, c in Counter(texts).items() if c > 1]
    if dupes:
        print(f"\n[REP] WARNING: {len(dupes)} duplicate scene texts")
    else:
        print(f"\n[REP] No duplicate scene texts [OK]")

    return openers, camera_counts


def check_scene_visual_diversity(scenes_json_path="scenes.json"):
    """Check if scenes have varied visual descriptions."""
    with open(scenes_json_path, encoding="utf-8") as f:
        scenes = json.load(f)

    # Extract keyword categories
    keywords = {
        "person": ["man", "woman", "person", "figure", "subject", "adult", "face", "hand"],
        "interior": ["room", "kitchen", "office", "apartment", "bedroom", "hallway"],
        "exterior": ["street", "city", "outdoor", "park", "car", "building"],
        "props": ["phone", "table", "chair", "door", "window", "notebook", "glass"],
        "lighting": ["dim", "warm", "cool", "shadow", "light", "dark", "bright"],
    }

    print(f"\n[REP] Visual diversity across {len(scenes)} scenes:")
    for cat, words in keywords.items():
        counts = Counter()
        for s in scenes:
            p = s["prompt"].lower()
            for w in words:
                if w in p:
                    counts[w] += 1

        if counts:
            top = counts.most_common(3)
            print(f"    {cat:<10}: " + ", ".join(f"{w}({c})" for w, c in top))


if __name__ == "__main__":
    import os

    if os.path.exists("scripts.txt"):
        print("=" * 60)
        print("SCRIPT REPETITION ANALYSIS")
        print("=" * 60)
        with open("scripts.txt", encoding="utf-8") as f:
            script = f.read()
        check_script(script)

    if os.path.exists("scenes.json"):
        print("\n" + "=" * 60)
        print("SCENE PROMPT REPETITION ANALYSIS")
        print("=" * 60)
        check_scenes()
        check_scene_visual_diversity()
