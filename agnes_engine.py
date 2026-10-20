import os, sys, time, json, gc, random, subprocess, requests, asyncio, urllib.parse

try:
    from picwish import PicWish, T2ITheme, T2IQuality, T2ISize
    PICWISH_AVAILABLE = True
except ImportError:
    PICWISH_AVAILABLE = False
    print("[!] PicWish not installed. Run: pip install picwish")

AGNES_API_KEY = os.environ.get("AGNES_API_KEY", "")
AGNES_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.1-flash"
BASE_DIR = os.getcwd()

DARK_CINEMATIC_SUFFIX = (
    "Cinematic dark psychological drama aesthetic, controlled shadows, "
    "moody atmospheric lighting, muted desaturated color palette, "
    "deep blacks with careful highlights, film grain texture, "
    "shallow depth of field, 16:9 widescreen composition, "
    "photorealistic film still quality, no text, no watermarks, no logos."
)

def _free_ram():
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except: pass

def _download_image(url, out_path, timeout=180):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.content
    if len(data) < 5000: raise Exception(f"Too small: {len(data)} bytes")
    tmp = out_path + ".download"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, out_path)

def _try_agnes(prompt, output_path, timeout=240):
    if not AGNES_API_KEY: raise Exception("AGNES_API_KEY missing")
    payload = {
        "model": AGNES_MODEL, "prompt": prompt, "size": "2K", "ratio": "16:9",
        "extra_body": {"response_format": "url"}
    }
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    r = requests.post(AGNES_URL, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("data"):
        first = data["data"][0]
        url = first.get("url") or first.get("b64_json")
        if url:
            _download_image(url, output_path)
            return True
    raise Exception(f"Unexpected response: {str(data)[:100]}")

def _try_picwish(prompt, output_path):
    if not PICWISH_AVAILABLE: raise Exception("PicWish library not available")
    async def _run():
        pw = PicWish()
        res = await pw.text_to_image(prompt=prompt, theme=T2ITheme.GENERAL, size=T2ISize.FHD_1_1, batch_size=1, quality=T2IQuality.HIGH)
        for r in res: await r.download(str(output_path))
    asyncio.run(_run())
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 5000:
        raise Exception("PicWish invalid image")

def generate_image(prompt, output_path, size="2K"):
    if "cinematic" not in prompt.lower():
        prompt = prompt.rstrip(".") + ". " + DARK_CINEMATIC_SUFFIX
    last_err = None

    # 1. PRIMARY: AGNES
    for attempt in range(1, 3):
        try:
            print(f"    [AGNES] attempt {attempt}/2")
            _try_agnes(prompt, output_path)
            print(f"    [AGNES OK] {os.path.getsize(output_path)//1024} KB")
            return output_path
        except Exception as e:
            last_err = e
            print(f"    [AGNES] failed: {str(e)[:80]}")
            if attempt < 2: time.sleep(5)

    # 2. FALLBACK: PICWISH
    print(f"    [FALLBACK] Agnes failed. Trying PicWish...")
    for attempt in range(1, 3):
        try:
            _try_picwish(prompt, output_path)
            print(f"    [PICWISH OK] {os.path.getsize(output_path)//1024} KB")
            return output_path
        except Exception as e:
            last_err = e
            print(f"    [PICWISH] failed: {str(e)[:80]}")
            if attempt < 2: time.sleep(5)

    raise Exception(f"[X] All image providers failed: {last_err}")

def generate_scene_images(scenes_json="scenes.json", output_dir="frames", size="2K", start_from=1):
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    os.makedirs(output_dir, exist_ok=True)
    with open(scenes_json, encoding="utf-8") as f: scenes = json.load(f)

    total = len(scenes)
    print(f"\n[AGNES] Scenes: {total} | Size: {size} | 16:9\n")
    inter_call_delay = 10 if size == "2K" else 5
    
    ok, skip, fail = 0, 0, 0
    images_since_clear = 0

    for scene in scenes:
        sid = int(scene["id"])
        if sid < start_from: continue
        out_path = os.path.join(output_dir, f"scene_{sid:03d}.png")

        if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            print(f"[{sid:3d}/{total}] SKIP")
            skip += 1
            continue

        prompt = scene.get("prompt", "").strip()
        if not prompt:
            print(f"[{sid:3d}/{total}] NO PROMPT")
            fail += 1
            continue

        print(f"[{sid:3d}/{total}] {prompt[:60]}...")
        try:
            generate_image(prompt, out_path, size=size)
            ok += 1
            images_since_clear += 1
        except Exception as e:
            print(f"    [X] FAILED: {str(e)[:100]}")
            fail += 1

        del prompt
        _free_ram()

        if images_since_clear >= 8:
            images_since_clear = 0
            print("    [RAM] cleanup")

        if sid < total: time.sleep(inter_call_delay)

    print(f"\n[AGNES] Complete\n    Generated: {ok}\n    Skipped: {skip}\n    Failed: {fail}\n")

if __name__ == "__main__":
    start = 1
    if "--start" in sys.argv: start = int(sys.argv[sys.argv.index("--start") + 1])
    generate_scene_images(start_from=start)
