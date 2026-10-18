# voice_test5.py — Final tune: quieter than V1

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

# Final 3 candidates — all quieter than V1
VARIANTS = [
    ("F1", BASE + "volume=0.85,loudnorm=I=-24:TP=-4:LRA=9"),
    ("F2", BASE + "volume=0.9,loudnorm=I=-25:TP=-4:LRA=9"),
    ("F3", BASE + "volume=0.8,loudnorm=I=-23:TP=-3.5:LRA=9"),
]


def process(raw, out, filters):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw}" -af "{filters}" '
        f'-ar 44100 -ac 2 -c:a libmp3lame -b:a 192k '
        f'"{out}"'
    )


def main():
    raw = os.path.join(BASE_DIR, "_raw_f.mp3")
    print("Generating Andrew Multilingual TTS...")
    asyncio.run(_tts(TEST_TEXT, raw))

    gallery = "/storage/emulated/0/DCIM/VoiceTests5"
    os.makedirs(gallery, exist_ok=True)

    for name, filters in VARIANTS:
        out = os.path.join(BASE_DIR, f"v5_{name}.mp3")
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

    print(f"\n[OK] Saved: {gallery}")
    print("F1 = -24 LUFS + volume 0.85")
    print("F2 = -25 LUFS + volume 0.90")
    print("F3 = -23 LUFS + volume 0.80")


if __name__ == "__main__":
    main()
