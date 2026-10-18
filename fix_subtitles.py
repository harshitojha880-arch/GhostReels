# fix_subtitles.py
# Regenerates captions.ass with:
# - No flicker (each word extends to next word's start)
# - Yellow active word, white others
# - Lower placement (MarginV 95)

import os
import json

TIMINGS = "word_timings.json"
ASS_OUT = "captions.ass"

# Configuration
GROUP_SIZE = 5          # 4-6 words per caption block
MAX_CHARS = 30          # max chars per block
MARGIN_V = 95           # lower placement (was 155)
FONT_SIZE = 46


def ass_time(sec):
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(t):
    return str(t).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def main():
    with open(TIMINGS, encoding="utf-8") as f:
        words = json.load(f)

    if not words:
        raise Exception("No word timings")

    # Build groups
    groups = []
    cur = []
    cur_chars = 0

    for w in words:
        word = str(w.get("word", "")).strip()
        if not word:
            continue
        projected = cur_chars + len(word) + (1 if cur else 0)
        if cur and (len(cur) >= GROUP_SIZE or projected > MAX_CHARS):
            groups.append(cur)
            cur = []
            cur_chars = 0
        cur.append(w)
        cur_chars += len(word) + (1 if len(cur) > 1 else 0)

    if cur:
        groups.append(cur)

    print(f"[FIX] Groups: {len(groups)} | Words: {len(words)}")

    # Build ASS
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1280",
        "PlayResY: 720",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Base,Droid Sans,{FONT_SIZE},"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0.5,0,1,3.0,1.5,2,80,80,"
        f"{MARGIN_V},1",
        f"Style: Active,Droid Sans,{FONT_SIZE},"
        "&H0000D7FF,&H0000D7FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0.5,0,1,3.2,1.6,2,80,80,"
        f"{MARGIN_V},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text",
    ]

    lines = list(header)

    # Build event list: each word is highlighted from its start to the
    # next word's start (within the same group). Last word in group
    # extends to the FIRST word of the next group.
    for g_idx, group in enumerate(groups):
        if not group:
            continue

        # Determine next group's first word start (for last word's end)
        if g_idx + 1 < len(groups) and groups[g_idx + 1]:
            next_group_start = float(groups[g_idx + 1][0]["start"])
        else:
            # Last group — extend a bit beyond last word
            next_group_start = float(group[-1]["end"]) + 0.5

        for idx, active in enumerate(group):
            word_start = float(active["start"])

            # End = next word's start (in this group), or next group's start
            if idx + 1 < len(group):
                word_end = float(group[idx + 1]["start"])
            else:
                word_end = next_group_start

            # Safety: ensure positive duration
            if word_end <= word_start:
                word_end = word_start + 0.05

            before = [w["word"] for w in group[:idx]]
            after = [w["word"] for w in group[idx + 1:]]

            parts = []
            if before:
                parts.append(" ".join(esc(w) for w in before))
            parts.append(r"{\rActive}" + esc(active["word"]) + r"{\rBase}")
            if after:
                parts.append(" ".join(esc(w) for w in after))

            text = " ".join(parts)

            lines.append(
                "Dialogue: 0,"
                + ass_time(word_start) + ","
                + ass_time(word_end) + ","
                + "Base,,0,0," + str(MARGIN_V) + ",,"
                + text
            )

    with open(ASS_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[FIX] Saved: {ASS_OUT}")
    print(f"[FIX] Events: {sum(len(g) for g in groups)}")
    print(f"[FIX] No-flicker: each word extends to next word's start")
    print(f"[FIX] MarginV: {MARGIN_V} (lower placement)")


if __name__ == "__main__":
    main()
