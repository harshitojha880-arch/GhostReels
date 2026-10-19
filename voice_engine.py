# voice_engine.py v3 — FINAL
# Voice: Andrew Multilingual | Pitch -5Hz | -24 LUFS | FINAL
# Optimized: -24 LUFS, natural, low sibilance

import os
import re
import json
import asyncio
import subprocess
import edge_tts


# ============================================================
# VOICE PROFILE — LOCKED
# ============================================================
# Load niche config
import json
_cfg_path = os.path.join(os.getcwd(), "niche_config.json")
if os.path.exists(_cfg_path):
    with open(_cfg_path, "r", encoding="utf-8") as _f:
        _cfg = json.load(_f)
        VOICE = _cfg.get("voice", "en-US-AndrewMultilingualNeural")
else:
    VOICE = "en-US-AndrewMultilingualNeural"
RATE = "-2%"
PITCH = "-5Hz"
VOLUME = "+0%"

BASE_DIR = os.getcwd()
RAW_AUDIO = os.path.join(BASE_DIR, "voice_raw.mp3")
MASTER_AUDIO = os.path.join(BASE_DIR, "voice_master.mp3")
TIMINGS_FILE = os.path.join(BASE_DIR, "word_timings.json")
SRT_FILE = os.path.join(BASE_DIR, "captions.srt")
ASS_FILE = os.path.join(BASE_DIR, "captions.ass")
SCRIPT_FILE = os.path.join(BASE_DIR, "scripts.txt")


# ============================================================
# FINAL STUDIO CHAIN — F1
# ============================================================
FINAL_FILTERS = (
    # Cleanup
    "highpass=f=80,"
    "lowpass=f=16000,"
    # Mild presence
    "equalizer=f=2500:t=q:w=1.5:g=0.8,"
    # Warmth
    "equalizer=f=180:t=q:w=1.5:g=1.0,"
    # De-esser
    "equalizer=f=7000:t=q:w=2.0:g=-2.0,"
    # Gentle NR
    "afftdn=nr=5:nf=-42,"
    # Very light compression
    "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=250:makeup=1.0,"
    # Natural room
    "aecho=0.85:0.9:20|40:0.05|0.025,"
    # Final volume + loudness
    "volume=0.85,"
    "loudnorm=I=-24:TP=-4:LRA=9"
)


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise Exception(f"[X] {r.stderr[-400:]}")
    return r.stdout.strip()


def _probe_duration(path):
    out = _run(
        f'ffprobe -v error -show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 "{path}"'
    )
    return float(out)


# ============================================================
# TTS with retry
# ============================================================
async def _tts_stream(script_text, raw_path, max_retries=4):
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"    [TTS] attempt {attempt}/{max_retries}")
            communicate = edge_tts.Communicate(
                script_text, VOICE,
                rate=RATE, volume=VOLUME, pitch=PITCH,
                boundary="WordBoundary",
            )
            words = []
            with open(raw_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        offset = chunk.get("offset", 0)
                        duration = chunk.get("duration", 0)
                        text = chunk.get("text", "").strip()
                        if text:
                            st = offset / 10_000_000.0
                            en = (offset + duration) / 10_000_000.0
                            words.append({
                                "word": text,
                                "start": round(st, 4),
                                "end": round(en, 4),
                            })

            if not words:
                raise Exception("no word boundaries")
            if not os.path.exists(raw_path) or os.path.getsize(raw_path) < 1000:
                raise Exception("empty audio")

            print(f"    [TTS] OK — {len(words)} words")
            return words

        except Exception as e:
            last_err = e
            print(f"    [TTS] attempt {attempt} failed: {e}")
            if os.path.exists(raw_path):
                try:
                    os.remove(raw_path)
                except Exception:
                    pass
            if attempt < max_retries:
                time.sleep(5 * attempt)
    raise Exception(f"[X] TTS failed: {last_err}")


import time


# ============================================================
# Subtitles
# ============================================================
def _srt_time(sec):
    sec = max(0.0, float(sec))
    h, m = int(sec // 3600), int((sec % 3600) // 60)
    r = sec % 60
    s, ms = int(r), int(round((r - int(r)) * 1000))
    if ms >= 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(sec):
    sec = max(0.0, float(sec))
    h, m = int(sec // 3600), int((sec % 3600) // 60)
    return f"{h}:{m:02d}:{sec % 60:05.2f}"


def _esc(t):
    return str(t).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _write_srt(words, path, group_size=6):
    groups = []
    for i in range(0, len(words), group_size):
        chunk = words[i:i + group_size]
        if chunk:
            groups.append((chunk[0]["start"], chunk[-1]["end"],
                           " ".join(w["word"] for w in chunk)))
    with open(path, "w", encoding="utf-8") as f:
        for idx, (st, en, text) in enumerate(groups, 1):
            f.write(f"{idx}\n{_srt_time(st)} --> {_srt_time(en)}\n{text}\n\n")


def _write_ass(words, path, group_size=5):
    groups, cur, cur_chars = [], [], 0
    for w in words:
        word = str(w.get("word", "")).strip()
        if not word:
            continue
        projected = cur_chars + len(word) + (1 if cur else 0)
        if cur and (len(cur) >= group_size or projected > 34):
            groups.append(cur)
            cur, cur_chars = [], 0
        cur.append(w)
        cur_chars += len(word) + (1 if len(cur) > 1 else 0)
    if cur:
        groups.append(cur)

    header = [
        "[Script Info]", "ScriptType: v4.00+",
        "PlayResX: 1280", "PlayResY: 720",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Base,Droid Sans,44,"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,"
        "1,0,0,0,100,100,0.4,0,1,3.0,1.5,2,80,80,95,1",
        "Style: Active,Droid Sans,44,"
        "&H0000D7FF,&H0000D7FF,&H00000000,&H90000000,"
        "1,0,0,0,100,100,0.4,0,1,3.2,1.6,2,80,80,95,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text",
    ]
    lines = list(header)

    for g_idx, group in enumerate(groups):
        if not group:
            continue
        if g_idx + 1 < len(groups) and groups[g_idx + 1]:
            next_group_start = float(groups[g_idx + 1][0]["start"])
        else:
            next_group_start = float(group[-1]["end"]) + 0.5

        for idx, active in enumerate(group):
            word_start = float(active["start"])
            if idx + 1 < len(group):
                word_end = float(group[idx + 1]["start"])
            else:
                word_end = next_group_start
            if word_end <= word_start:
                word_end = word_start + 0.05

            before = [w["word"] for w in group[:idx]]
            after = [w["word"] for w in group[idx + 1:]]
            parts = []
            if before:
                parts.append(" ".join(_esc(w) for w in before))
            parts.append(r"{\rActive}" + _esc(active["word"]) + r"{\rBase}")
            if after:
                parts.append(" ".join(_esc(w) for w in after))

            lines.append(
                "Dialogue: 0,"
                + _ass_time(word_start) + ","
                + _ass_time(word_end) + ","
                + "Base,,0,0,95,,"
                + " ".join(parts)
            )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ============================================================
# MAIN
# ============================================================
def generate_voice(script_text=None):
    if script_text is None:
        if not os.path.exists(SCRIPT_FILE):
            raise Exception("[X] scripts.txt not found")
        with open(SCRIPT_FILE, encoding="utf-8") as f:
            script_text = f.read().strip()
    if not script_text:
        raise Exception("[X] empty script")

    print("=" * 60)
    print(" FINAL VOICE ENGINE — Andrew Multilingual")
    print("=" * 60)
    print(f" Voice: {VOICE}")
    print(f" Rate:  {RATE} | Pitch: {PITCH}")
    print(f" Target: -24 LUFS (quiet cinematic)")
    print(f" Script: {len(script_text.split())} words")
    print("=" * 60)

    # 1. TTS
    print("\n[1/4] Generating Edge-TTS...")
    words = asyncio.run(asyncio.wait_for(_tts_stream(script_text, RAW_AUDIO), timeout=1800))
    print(f"      Words: {len(words)}")

    # 2. Studio processing (F1 chain)
    print("\n[2/4] Applying F1 studio chain...")
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{RAW_AUDIO}" '
        f'-af "{FINAL_FILTERS}" '
        f'-ar 44100 -ac 2 '
        f'-codec:a libmp3lame -b:a 192k '
        f'"{MASTER_AUDIO}"'
    )
    duration = _probe_duration(MASTER_AUDIO)
    print(f"      Duration: {duration:.2f}s ({duration/60:.1f} min)")

    # 3. Timings
    print("\n[3/4] Saving word timings...")
    with open(TIMINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, indent=2, ensure_ascii=False)

    # 4. Subtitles
    print("\n[4/4] Generating subtitles...")
    _write_srt(words, SRT_FILE)
    _write_ass(words, ASS_FILE)

    # Cleanup raw
    if os.path.exists(RAW_AUDIO):
        try:
            os.remove(RAW_AUDIO)
        except Exception:
            pass

    print("\n" + "=" * 60)
    print(f" COMPLETE — {MASTER_AUDIO}")
    print("=" * 60)

    return MASTER_AUDIO, duration, words


if __name__ == "__main__":
    generate_voice()
