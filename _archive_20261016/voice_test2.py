# voice_test2.py — Test different Edge-TTS voices with minimal processing
# Key insight: less processing = more natural

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

# 6 different voices to try
VOICES = [
    ("EricNeural", "en-US-EricNeural", "-4%", "-2Hz"),
    ("AndrewNeural", "en-US-AndrewNeural", "-2%", "-1Hz"),
    ("AndrewMultilingual", "en-US-AndrewMultilingualNeural", "-2%", "-1Hz"),
    ("BrianNeural", "en-US-BrianNeural", "-3%", "-2Hz"),
    ("BrianMultilingual", "en-US-BrianMultilingualNeural", "-3%", "-2Hz"),
    ("GuyNeural", "en-US-GuyNeural", "-4%", "-3Hz"),
    ("ChristopherNeural", "en-US-ChristopherNeural", "-4%", "-3Hz"),
]


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] {r.stderr[-300:]}")


async def _tts(text, out_path, voice, rate, pitch):
    communicate = edge_tts.Communicate(
        text, voice,
        rate=rate, volume="+0%", pitch=pitch,
        boundary="WordBoundary",
    )
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


# Minimal processing — just cleanup, no compression
FILTERS_MINIMAL = (
    "highpass=f=80,"
    "lowpass=f=16000,"
    # Tiny presence (very subtle)
    "equalizer=f=2500:t=q:w=1.5:g=0.8,"
    # Very mild warmth
    "equalizer=f=180:t=q:w=1.5:g=1.0,"
    # Very light de-esser
    "equalizer=f=7000:t=q:w=2.0:g=-2.0,"
    # Very light NR
    "afftdn=nr=5:nf=-42,"
    # Very light compression
    "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=250:makeup=1.5,"
    # Natural room
    "aecho=0.85:0.9:20|40:0.05|0.025,"
    # Loudnorm
    "loudnorm=I=-16:TP=-2:LRA=12"
)


def process_variant(raw_audio, out_audio):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw_audio}" '
        f'-af "{FILTERS_MINIMAL}" '
        f'-ar 44100 -ac 2 '
        f'-codec:a libmp3lame -b:a 192k '
        f'"{out_audio}"'
    )


def main():
    print("Testing 7 voices with minimal processing...\n")

    gallery = "/storage/emulated/0/DCIM/VoiceTests2"
    os.makedirs(gallery, exist_ok=True)

    for name, voice_id, rate, pitch in VOICES:
        print(f"--- {name} ---")
        try:
            raw = os.path.join(BASE_DIR, f"_raw_{name}.mp3")
            out = os.path.join(BASE_DIR, f"v2_{name}.mp3")

            # Generate TTS
            asyncio.run(_tts(TEST_TEXT, raw, voice_id, rate, pitch))

            # Process
            process_variant(raw, out)

            # Copy to gallery
            _run(f'cp "{out}" "{gallery}/{name}.mp3"')
            print(f"  ✓ {name}: {os.path.getsize(out) // 1024} KB")

            # Cleanup
            try:
                os.remove(raw)
                os.remove(out)
            except Exception:
                pass

        except Exception as e:
            print(f"  ✗ {name}: {e}")

    print(f"\n[OK] All samples saved to: {gallery}")
    print("\nListen to each and tell me which one sounds most human:")
    for name, _, _, _ in VOICES:
        print(f"  • {name}")


if __name__ == "__main__":
    main()
