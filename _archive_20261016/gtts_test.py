# gtts_test.py — Test Google TTS voices with same processing

import os
import subprocess
from gtts import gTTS

BASE_DIR = os.getcwd()
TEST_TEXT = (
    "You check your phone before answering them. That is not love, that is training. "
    "You apologize for things you didn't do. That is what conditioning looks like. "
    "You feel crazy in arguments you didn't start. That is exactly the point."
)


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] {r.stderr[-300:]}")


# F1 processing chain (same as voice_engine)
F1_FILTERS = (
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


# Test variations — accents, slow, and TLD
VARIANTS = [
    ("US_default", "com", False, "en", False),
    ("US_slow", "com", True, "en", False),
    ("UK_default", "co.uk", False, "en", False),
    ("AU_default", "com.au", False, "en", False),
    ("CA_default", "ca", False, "en", False),
    ("US_tld_in", "co.in", False, "en", False),  # Indian English
]


def generate_gtts(text, out_path, tld, slow, lang):
    tts = gTTS(text=text, lang=lang, tld=tld, slow=slow)
    tts.save(out_path)


def process(raw, out, filters):
    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{raw}" -af "{filters}" '
        f'-ar 44100 -ac 2 -c:a libmp3lame -b:a 192k '
        f'"{out}"'
    )


def main():
    gallery = "/storage/emulated/0/DCIM/gTTSTests"
    os.makedirs(gallery, exist_ok=True)

    print(f"Testing {len(VARIANTS)} gTTS variants...\n")

    for name, tld, slow, lang, _ in VARIANTS:
        print(f"--- {name} (tld={tld}, slow={slow}) ---")
        raw = os.path.join(BASE_DIR, f"_raw_{name}.mp3")
        out = os.path.join(BASE_DIR, f"gtts_{name}.mp3")

        try:
            # Generate raw
            generate_gtts(TEST_TEXT, raw, tld, slow, lang)
            raw_size = os.path.getsize(raw)
            print(f"  Raw: {raw_size // 1024} KB")

            # Process with F1
            process(raw, out, F1_FILTERS)
            out_size = os.path.getsize(out)
            print(f"  Processed: {out_size // 1024} KB")

            # Copy to gallery
            _run(f'cp "{out}" "{gallery}/{name}.mp3"')
            print(f"  ✓ Saved to {gallery}/{name}.mp3")

        except Exception as e:
            print(f"  ✗ Failed: {e}")

        # Cleanup
        for f in [raw, out]:
            try:
                os.remove(f)
            except Exception:
                pass

    print(f"\n[OK] All variants saved to: {gallery}")
    print("\nVariants:")
    print("  US_default  — American English (Google Translate default)")
    print("  US_slow     — Slower American English")
    print("  UK_default  — British English")
    print("  AU_default  — Australian English")
    print("  CA_default  — Canadian English")
    print("  US_tld_in   — Indian English accent")


if __name__ == "__main__":
    main()
