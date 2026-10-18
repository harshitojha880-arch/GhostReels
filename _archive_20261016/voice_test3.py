# voice_test3.py — Lower loudness test
# Andrew voice + 4 different loudness levels

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

VOICE = "en-US-AndrewNeural"
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


# Base processing — minimal
BASE_FILTERS = (
    "highpass=f=80,"
    "lowpass=f=16000,"
    "equalizer=f=2500:t=q:w=1.5:g=0.8,"
    "equalizer=f=180:t=q:w=1.5:g=1.0,"
    "equalizer=f=7000:t=q:w=2.0:g=-2.0,"
    "afftdn=nr=5:nf=-42,"
    "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=250:makeup=1.5,"
    "aecho=0.85:0.9:20|40:0.05|0.025,"
)

# 4 loudness levels
VARIANTS = [
    ("V1_soft",  BASE_FILTERS + "volume=0.6,loudnorm=I=-20:TP=-3:LRA=10"),
    ("V2_medium", BASE_FILTERS + "volume=0.75,loudnorm=I=-18:TP=-2.5:LRA=10"),
    ("V3_normal", BASE_FILTERS + "volume=0.85,loudnorm=I=-17:TP=-2:LRA=11"),
    ("V4_quiet",  BASE_FILTERS + "volume=0.5,loudnorm=I=-22:TP=-3.5:LRA=9"),
]


def process_variant(raw, out, filters):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw}" '
        f'-af "{filters}" '
        f'-ar 44100 -ac 2 '
        f'-codec:a libmp3lame -b:a 192k '
        f'"{out}"'
    )


def get_lufs(path):
    """Read integrated loudness."""
    r = subprocess.run(
        f'ffmpeg -hide_banner -i "{path}" -af "loudnorm=print_format=summary" -f null - 2>&1',
        shell=True, capture_output=True, text=True
    )
    for line in r.stderr.split("\n"):
        if "Input Integrated" in line or "Output Integrated" in line:
            return line.strip()
    return "?"


def main():
    raw = os.path.join(BASE_DIR, "_raw_andrew.mp3")
    print("[1/2] Generating Andrew TTS...")
    asyncio.run(_tts(TEST_TEXT, raw))
    print(f"      Raw: {os.path.getsize(raw) // 1024} KB")

    gallery = "/storage/emulated/0/DCIM/VoiceTests3"
    os.makedirs(gallery, exist_ok=True)

    print("\n[2/2] Processing 4 loudness variants...\n")

    for name, filters in VARIANTS:
        print(f"--- {name} ---")
        out = os.path.join(BASE_DIR, f"v3_{name}.mp3")
        try:
            process_variant(raw, out, filters)
            size = os.path.getsize(out) // 1024
            _run(f'cp "{out}" "{gallery}/{name}.mp3"')
            print(f"  ✓ {size} KB | {name}")
        except Exception as e:
            print(f"  ✗ Failed: {e}")

    try:
        os.remove(raw)
    except Exception:
        pass

    print(f"\n[OK] Saved to: {gallery}")
    print("\nLoudness levels:")
    print("  V1_soft   — volume 0.6,  target -20 LUFS")
    print("  V2_medium — volume 0.75, target -18 LUFS")
    print("  V3_normal — volume 0.85, target -17 LUFS")
    print("  V4_quiet  — volume 0.5,  target -22 LUFS")
    print("\nStandard YouTube narration: -16 to -18 LUFS")
    print("Audiobook / ambient: -18 to -20 LUFS")


if __name__ == "__main__":
    main()
