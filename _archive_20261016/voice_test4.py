# voice_test4.py — Andrew Multilingual voice at 4 loudness levels

import os
import asyncio
import subprocess
import edge_tts

BASE_DIR = os.getcwd()
TEST_TEXT = (
    "You check your phone before answering them. That is not love, that is training. "
    "You apologize for things you didn't do. That is what conditioning looks like. "
    "You feel crazy in arguments you didn't start. That is exactly the point."
)

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "-2%"
PITCH = "-1Hz"


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] {r.stderr[-300:]}")


async def _tts(text, out_path):
    communicate = edge_tts.Communicate(
        text, VOICE,
        rate=RATE, volume="+0%", pitch=PITCH,
        boundary="WordBoundary",
    )
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


# Base processing (no loudnorm, no volume)
BASE = (
    "highpass=f=80,"
    "lowpass=f=16000,"
    "equalizer=f=2500:t=q:w=1.5:g=0.8,"
    "equalizer=f=180:t=q:w=1.5:g=1.0,"
    "equalizer=f=7000:t=q:w=2.0:g=-2.0,"
    "afftdn=nr=5:nf=-42,"
    "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=250:makeup=1.0,"
    "aecho=0.85:0.9:20|40:0.05|0.025,"
)

# 4 loudness levels
VARIANTS = [
    ("V1_quiet",  BASE + "loudnorm=I=-22:TP=-3:LRA=10"),
    ("V2_soft",   BASE + "loudnorm=I=-19:TP=-2.5:LRA=10"),
    ("V3_normal", BASE + "loudnorm=I=-17:TP=-2:LRA=11"),
    ("V4_loud",   BASE + "loudnorm=I=-15:TP=-1.5:LRA=11"),
]


def process(raw, out, filters):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw}" -af "{filters}" '
        f'-ar 44100 -ac 2 -c:a libmp3lame -b:a 192k '
        f'"{out}"'
    )


def main():
    raw = os.path.join(BASE_DIR, "_raw_am.mp3")
    print("[1/2] Generating Andrew Multilingual TTS...")
    asyncio.run(_tts(TEST_TEXT, raw))
    print(f"      Raw: {os.path.getsize(raw) // 1024} KB\n")

    gallery = "/storage/emulated/0/DCIM/VoiceTests4"
    os.makedirs(gallery, exist_ok=True)

    print("[2/2] Processing 4 loudness variants...\n")
    for name, filters in VARIANTS:
        out = os.path.join(BASE_DIR, f"v4_{name}.mp3")
        try:
            process(raw, out, filters)
            size = os.path.getsize(out) // 1024
            _run(f'cp "{out}" "{gallery}/{name}.mp3"')
            print(f"  ✓ {name}: {size} KB")
        except Exception as e:
            print(f"  ✗ {name}: {e}")

    try:
        os.remove(raw)
    except Exception:
        pass

    print(f"\n[OK] Saved to: {gallery}")
    print("\nLoudness levels (lower number = quieter):")
    print("  V1_quiet   -22 LUFS")
    print("  V2_soft    -19 LUFS")
    print("  V3_normal  -17 LUFS")
    print("  V4_loud    -15 LUFS (previous default)")


if __name__ == "__main__":
    main()
