# agnes_engine.py v3 — RAM-first, crash-proof, resumable.
# After every image: explicit del + gc.collect() + optional KV clear.

import os
import re
import sys
import time
import json
import gc
import random
import subprocess
import urllib.request
import urllib.parse
import urllib.error

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install --quiet requests")
    import requests


AGNES_API_KEY = os.environ.get("AGNES_API_KEY", "")
AGNES_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.1-flash"

POLL_FALLBACK = "https://image.pollinations.ai/prompt/"

BASE_DIR = os.getcwd()
LOCAL_SERVER = "http://127.0.0.1:8089"

DARK_CINEMATIC_SUFFIX = (
    "Cinematic dark psychological drama aesthetic, controlled shadows, "
    "moody atmospheric lighting, muted desaturated color palette, "
    "deep blacks with careful highlights, film grain texture, "
    "shallow depth of field, 16:9 widescreen composition, "
    "photorealistic film still quality, no text, no watermarks, no logos."
)


def _ensure_key():
    if not AGNES_API_KEY:
        raise Exception("[X] AGNES_API_KEY not set")


def _free_ram(stage=""):
    """Aggressively free Python-side RAM."""
    gc.collect()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass

    # Read free RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable"):
                    kb = int(line.split()[1])
                    mb = kb // 1024
                    if stage:
                        print(f"    [RAM] {stage} — {mb} MB free")
                    return mb
    except Exception:
        return None


def _clear_llama_kv():
    """Ask llama-server to free KV cache."""
    try:
        req = urllib.request.Request(
            f"{LOCAL_SERVER}/slots?action=erase", method="POST", data=b""
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass


def _should_clear_llama(images_since_clear, threshold=10):
    return images_since_clear >= threshold


# ============================================================
# DOWNLOAD
# ============================================================
def _download_image(url, out_path, timeout=180):
    """Download image, save to disk, free response memory immediately."""
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    # Use chunks to avoid huge buffer
    tmp = out_path + ".download"
    total = 0
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if chunk:
                f.write(chunk)
                total += len(chunk)

    # Explicit free
    try:
        r.close()
    except Exception:
        pass
    del r
    gc.collect()

    if total < 5000:
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise Exception(f"image too small: {total} bytes")

    os.replace(tmp, out_path)


# ============================================================
# PROVIDERS
# ============================================================
def _try_agnes(prompt, output_path, timeout=240):
    _ensure_key()
    payload = {
        "model": AGNES_MODEL,
        "prompt": prompt,
        "size": "2K",
        "ratio": "16:9",
        "extra_body": {"response_format": "url"},
    }
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.post(AGNES_URL, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    # Free response from memory
    try:
        r.close()
    except Exception:
        pass
    del r

    url = None
    if isinstance(data, dict) and data.get("data"):
        first = data["data"][0]
        url = first.get("url") or first.get("b64_json")
    del data
    gc.collect()

    if not url:
        raise Exception("no url in response")

    _download_image(url, output_path)
    del url
    gc.collect()


def _try_pollinations(prompt, output_path, timeout=240):
    encoded = urllib.parse.quote(prompt[:1500], safe="")
    url = (
        POLL_FALLBACK + encoded +
        "?model=flux&width=1280&height=720&nologo=true&seed=" +
        str(random.randint(1, 999999))
    )
    _download_image(url, output_path, timeout=timeout)
    del url
    gc.collect()


def generate_image(prompt, output_path, size="2K", ratio="16:9",
                   timeout=240, retries=3):
    """Generate one image. RAM freed after each step."""
    if "cinematic" not in prompt.lower():
        prompt = prompt.rstrip(".") + ". " + DARK_CINEMATIC_SUFFIX

    last_err = None

    # Try Agnes
    for attempt in range(1, 3):
        try:
            print(f"    [AGNES] attempt {attempt}/2")
            _try_agnes(prompt, output_path, timeout=timeout)
            size_kb = os.path.getsize(output_path) // 1024
            print(f"    [AGNES OK] {size_kb} KB")
            return output_path
        except Exception as e:
            last_err = e
            print(f"    [AGNES] failed: {str(e)[:80]}")
            if attempt < 2:
                time.sleep(5)

    # Fallback: Pollinations
    print(f"    [FALLBACK] Pollinations...")
    for attempt in range(1, 3):
        try:
            _try_pollinations(prompt, output_path, timeout=timeout)
            size_kb = os.path.getsize(output_path) // 1024
            print(f"    [POLL OK] {size_kb} KB")
            return output_path
        except Exception as e:
            last_err = e
            print(f"    [POLL] failed: {str(e)[:80]}")
            if attempt < 2:
                time.sleep(5)

    raise Exception(f"[X] All providers failed: {last_err}")


# ============================================================
# MAIN LOOP
# ============================================================
def generate_scene_images(scenes_json="scenes.json",
                          output_dir="frames",
                          size="2K",
                          start_from=1):
    import signal

    def _sig_handler(sig, frame):
        print("\n[!] Stopping — progress saved")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sig_handler)
    signal.signal(signal.SIGINT, _sig_handler)

    _ensure_key()
    os.makedirs(output_dir, exist_ok=True)

    with open(scenes_json, encoding="utf-8") as f:
        scenes = json.load(f)

    total = len(scenes)
    print(f"\n[AGNES] Engine v3 — RAM-first")
    print(f"[AGNES] Scenes: {total} | Size: {size} | 16:9")
    print(f"[AGNES] Output: {output_dir}/\n")

    inter_call_delay = 8 if size == "2K" else 4

    ok, skip, fail = 0, 0, 0
    images_since_clear = 0
    start_ram = _free_ram("start")

    for scene in scenes:
        sid = int(scene["id"])
        if sid < start_from:
            continue

        out_path = os.path.join(output_dir, f"scene_{sid:03d}.png")

        # Skip existing (resume)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            print(f"[{sid:3d}/{total}] SKIP")
            skip += 1
            continue

        prompt = scene.get("prompt", "").strip()
        if not prompt:
            print(f"[{sid:3d}/{total}] NO PROMPT")
            fail += 1
            continue

        print(f"[{sid:3d}/{total}] {prompt[:70]}...")

        try:
            generate_image(prompt, out_path, size=size)
            ok += 1
            images_since_clear += 1
        except Exception as e:
            print(f"    [X] FAILED: {str(e)[:100]}")
            fail += 1

        # ============ RAM CLEANUP AFTER EACH IMAGE ============
        # Free Python memory
        del prompt
        _free_ram()

        # Periodically clear llama-server KV (main RAM hog)
        if _should_clear_llama(images_since_clear, threshold=8):
            _clear_llama_kv()
            gc.collect()
            images_since_clear = 0
            print("    [RAM] llama KV cleared")

        # Small inter-call sleep
        if sid < total:
            time.sleep(inter_call_delay)

    end_ram = _free_ram("end")

    print(f"\n[AGNES] Complete")
    print(f"    Generated: {ok}")
    print(f"    Skipped:   {skip}")
    print(f"    Failed:    {fail}")
    if start_ram and end_ram:
        print(f"    RAM start: {start_ram} MB | end: {end_ram} MB")
    print(f"    Output:    {os.path.abspath(output_dir)}/")

    return ok


if __name__ == "__main__":
    if "--test" in sys.argv:
        generate_image(
            prompt="A woman sits alone at a dim kitchen table, phone face-down",
            output_path="test_agnes.png",
            size="2K",
        )
        print("[TEST] Done")
        sys.exit(0)

    start = 1
    if "--start" in sys.argv:
        start = int(sys.argv[sys.argv.index("--start") + 1])

    size = "2K"
    if "--size" in sys.argv:
        size = sys.argv[sys.argv.index("--size") + 1]

    generate_scene_images(
        scenes_json="scenes.json",
        output_dir="frames",
        size=size,
        start_from=start,
    )
