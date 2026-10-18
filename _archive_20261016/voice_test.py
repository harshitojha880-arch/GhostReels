# voice_test.py — Compare 3 voice processing variants
# Generates same text through 3 different filter chains

import os
import asyncio
import subprocess
import edge_tts

BASE_DIR = os.getcwd()
TEST_TEXT = (
    "You check your phone before answering them. That is not love, that is training. "
    "You apologize for things you didn't do. That is what conditioning looks like. "
    "You feel crazy in arguments you didn't start. That is exactly the point. "
    "You explain yourself three times in one text. Someone taught you that was necessary."
)

VOICE = "en-US-EricNeural"
RATE = "-4%"
PITCH = "-3Hz"


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


# ============================================================
# VARIANT A: Conservative
# Light de-esser, minimal reverb, cleaner
# ============================================================
FILTERS_A = (
    "highpass=f=85,"
    "lowpass=f=15000,"
    # Light de-esser (single notch)
    "equalizer=f=6500:t=q:w=2.0:g=-2.5,"
    # Mild presence
    "equalizer=f=3000:t=q:w=1.5:g=1.0,"
    # Warmth
    "equalizer=f=180:t=q:w=1.5:g=1.0,"
    # Gentle NR
    "afftdn=nr=6:nf=-40,"
    # Single gentle compressor
    "acompressor=threshold=-20dB:ratio=2.0:attack=20:release=200:makeup=1.5,"
    # Subtle room reverb
    "aecho=0.85:0.9:18|36:0.04|0.02,"
    # Loudnorm
    "loudnorm=I=-15:TP=-1.5:LRA=10"
)


# ============================================================
# VARIANT B: Balanced (recommended)
# Multi-band de-esser, natural room, warmth
# ============================================================
FILTERS_B = (
    "highpass=f=85,"
    "lowpass=f=15500,"
    # Multi-band de-esser
    "equalizer=f=6000:t=q:w=2.2:g=-3.0,"
    "equalizer=f=7500:t=q:w=2.0:g=-3.5,"
    "equalizer=f=9000:t=q:w=1.8:g=-2.0,"
    # Presence (reduced)
    "equalizer=f=2800:t=q:w=1.5:g=1.2,"
    # Warmth (increased)
    "equalizer=f=180:t=q:w=1.5:g=1.6,"
    "equalizer=f=350:t=q:w=1.8:g=0.8,"
    # Gentle NR
    "afftdn=nr=8:nf=-38,"
    # Dual-stage compression
    "acompressor=threshold=-22dB:ratio=2.2:attack=25:release=220:makeup=2,"
    # Natural room (more prominent)
    "aecho=0.8:0.88:22|44:0.06|0.03,"
    # Stereo width
    "extrastereo=m=1.03,"
    # Loudnorm (wider range)
    "loudnorm=I=-15:TP=-1.5:LRA=11"
)


# ============================================================
# VARIANT C: Warm/Human
# Strong de-esser, warm tone, cinematic room
# ============================================================
FILTERS_C = (
    "highpass=f=80,"
    "lowpass=f=15000,"
    # Strong de-esser
    "equalizer=f=5500:t=q:w=2.0:g=-2.5,"
    "equalizer=f=7000:t=q:w=2.5:g=-4.5,"
    "equalizer=f=8500:t=q:w=1.8:g=-3.0,"
    "equalizer=f=10000:t=q:w=1.5:g=-1.5,"
    # Cut nasal presence
    "equalizer=f=3200:t=q:w=1.2:g=-0.8,"
    # Body warmth (boosted)
    "equalizer=f=170:t=q:w=1.5:g=2.0,"
    "equalizer=f=350:t=q:w=1.8:g=1.2,"
    # Gentle NR
    "afftdn=nr=6:nf=-42,"
    # Very gentle compression
    "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=280:makeup=2.5,"
    # Cinematic room (longer tail)
    "aecho=0.75:0.85:28|55|82:0.07|0.04|0.02,"
    # Stereo width
    "extrastereo=m=1.05,"
    # Loudnorm (preserve dynamics)
    "loudnorm=I=-15:TP=-1.5:LRA=12"
)


def process_variant(raw_audio, out_audio, filters):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw_audio}" '
        f'-af "{filters}" '
        f'-ar 44100 -ac 2 '
        f'-codec:a libmp3lame -b:a 192k '
        f'"{out_audio}"'
    )


def main():
    raw = os.path.join(BASE_DIR, "_test_raw.mp3")

    print("[1/4] Generating raw TTS...")
    asyncio.run(_tts(TEST_TEXT, raw))
    print(f"      Raw audio: {os.path.getsize(raw) // 1024} KB")

    print("\n[2/4] Processing Variant A (conservative)...")
    out_a = os.path.join(BASE_DIR, "voice_test_A.mp3")
    process_variant(raw, out_a, FILTERS_A)
    print(f"      Saved: {out_a}")

    print("\n[3/4] Processing Variant B (balanced)...")
    out_b = os.path.join(BASE_DIR, "voice_test_B.mp3")
    process_variant(raw, out_b, FILTERS_B)
    print(f"      Saved: {out_b}")

    print("\n[4/4] Processing Variant C (warm/human)...")
    out_c = os.path.join(BASE_DIR, "voice_test_C.mp3")
    process_variant(raw, out_c, FILTERS_C)
    print(f"      Saved: {out_c}")

    # Cleanup raw
    try:
        os.remove(raw)
    except Exception:
        pass

    # Copy to gallery
    gallery = "/storage/emulated/0/DCIM/VoiceTests"
    try:
        os.makedirs(gallery, exist_ok=True)
        _run(f'cp "{out_a}" "{gallery}/A_conservative.mp3"')
        _run(f'cp "{out_b}" "{gallery}/B_balanced.mp3"')
        _run(f'cp "{out_c}" "{gallery}/C_warm.mp3"')
        print(f"\n[OK] Copied to: {gallery}")
    except Exception as e:
        print(f"[!] Gallery copy failed: {e}")

    print("\n" + "=" * 60)
    print(" VARIANT COMPARISON")
    print("=" * 60)
    print(" A — Conservative:")
    print("     Light de-esser, clean, mild warmth")
    print(" B — Balanced (recommended):")
    print("     Multi-band de-esser, natural room, warm")
    print(" C — Warm/Human:")
    print("     Strong de-esser, cinematic room, dynamic")
    print("=" * 60)


if __name__ == "__main__":
    main()
