# voice_test6.py — Pitch tuning for Andrew Multilingual
# Same F1 processing, different pitch values

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


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] {r.stderr[-300:]}")


async def _tts(text, out_path, pitch):
    communicate = edge_tts.Communicate(
        text, VOICE,
        rate=RATE, volume="+0%", pitch=pitch,
        boundary="WordBoundary",
    )
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


# F1 processing (locked)
F1 = (
    "highpass=f=80,"
    "lowpass=f=16000,"
    "equalizer=f=2500:t=q:w=1.5:g=0.8,"
    "equalizer=f=180:t=q:w=1.5:g=1.0,"
    "equalizer=f=7000:t=q:w=2.0:g=-2.0,"
    "afftdn=nr=5:nf=-42,"
    "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=250:makeup=1.0,"
    "aecho=0.85:0.9:20|40:0.05|0.025,"
    "volume=0.85,"
    "loudnorm=I=-24:TP=-4:LRA=9"
)

# Pitch variations
PITCHES = [
    ("P1_minus1", "-1Hz"),      # current
    ("P2_minus3", "-3Hz"),
    ("P3_minus5", "-5Hz"),
    ("P4_minus7", "-7Hz"),
    ("P5_minus10", "-10Hz"),
    ("P6_plus2", "+2Hz"),       # slightly higher
]


def process(raw, out):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw}" -af "{F1}" '
        f'-ar 44100 -ac 2 -c:a libmp3lame -b:a 192k '
        f'"{out}"'
    )


def main():
    gallery = "/storage/emulated/0/DCIM/VoiceTests6"
    os.makedirs(gallery, exist_ok=True)

    print(f"Testing {len(PITCHES)} pitch variations...\n")

    for name, pitch in PITCHES:
        print(f"--- {name} (pitch={pitch}) ---")
        raw = os.path.join(BASE_DIR, f"_raw_{name}.mp3")
        out = os.path.join(BASE_DIR, f"v6_{name}.mp3")

        try:
            asyncio.run(_tts(TEST_TEXT, raw, pitch))
            process(raw, out)
            size = os.path.getsize(out) // 1024
            _run(f'cp "{out}" "{gallery}/{name}.mp3"')
            print(f"  ✓ {size} KB")
        except Exception as e:
            print(f"  ✗ Failed: {e}")

        for f in [raw, out]:
            try:
                os.remove(f)
            except Exception:
                pass

    print(f"\n[OK] All saved to: {gallery}")
    print("\nPitch variations:")
    print("  P1_minus1  — current (-1Hz)")
    print("  P2_minus3  — slightly lower (-3Hz)")
    print("  P3_minus5  — noticeably lower (-5Hz)")
    print("  P4_minus7  — much lower (-7Hz)")
    print("  P5_minus10 — very deep (-10Hz)")
    print("  P6_plus2   — slightly higher (+2Hz)")


if __name__ == "__main__":
    main()
