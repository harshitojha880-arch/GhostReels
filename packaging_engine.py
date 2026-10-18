import os
import re
import sys
import json
import time
import random
import subprocess
from pathlib import Path
from datetime import datetime

from cloud_llm import generate_with_retry

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install --quiet requests")
    import requests

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    os.system(f"{sys.executable} -m pip install --quiet Pillow")
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    import numpy
except ImportError:
    os.system(f"{sys.executable} -m pip install --quiet numpy")
    import numpy

BASE_DIR = Path(__file__).resolve().parent
SEO_ROOT = Path("/storage/emulated/0/dark psychology/seo")
STATE_FILE = BASE_DIR / "pipeline_state.json"

AGNES_KEY = os.environ.get("AGNES_API_KEY", "")
AGNES_URL = "https://apihub.agnes-ai.com/v1/images/generations"

THUMB_FONTS = [
    "/system/fonts/BarlowSemiCondensed-Black.ttf",
    "/system/fonts/BarlowSemiCondensed-ExtraBold.ttf",
    "/system/fonts/DroidSans-Bold.ttf",
]

ACCENTS = [(220, 30, 30), (255, 215, 0), (255, 255, 255), (255, 100, 30)]

def _llm(system, user, max_tokens=1500, temperature=0.85, task="seo"):
    return generate_with_retry(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens, temperature=temperature, task=task, max_attempts=5, verbose=True,
    )

def _parse_lines(text):
    out = []
    for line in text.split("\n"):
        line = line.strip()
        line = re.sub(r'^\d+[\.\)]\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)
        line = line.strip('"\'`').strip()
        if line and not line.startswith(("Here", "Sure", "Note:")): out.append(line)
    return out

def generate_titles(topic, script_excerpt):
    system = """You write viral YouTube titles for a dark-psychology channel.
STYLE REFERENCE:
- "The Psychology of the Invisible Child"
- "Why Intelligent People Suddenly Disappear"
- "The Psychology of the Man Child"
- "The Dark Side of Kindness"
RULES: 4-10 words. Start with "The Psychology of..." OR "Why..." OR name a person type. Name a SPECIFIC PERSON TYPE. No clickbait.
Output exactly 5 titles, one per line. No numbering. No quotes."""
    user = f"Topic: {topic}\n\nScript excerpt:\n{script_excerpt[:1200]}\n\nWrite 5 titles now."
    raw = _llm(system, user, max_tokens=400, temperature=0.9)
    return _parse_lines(raw)[:5]

def generate_thumbnail_texts(topic, script_excerpt):
    system = """You write 2-4 word BOLD text for YouTube thumbnails.
STYLE REFERENCE:
- THE INVISIBLE CHILD
- SMART PEOPLE LEAVE
- THE MAN CHILD
- CAN FIX EVERYTHING
RULES: 2-4 words ONLY. ALL CAPS. NO trailing word like HOOK, TITLE, TEXT.
Output exactly 3 options, one per line."""
    user = f"Topic: {topic}\n\nScript excerpt:\n{script_excerpt[:1000]}\n\nWrite 3 thumbnail text options now."
    raw = _llm(system, user, max_tokens=200, temperature=0.95)
    META_WORDS = {"hook", "title", "text", "scene", "idea", "concept", "video"}
    options = []
    for o in _parse_lines(raw):
        o = o.upper().strip()
        words = [w for w in o.split() if w.lower() not in META_WORDS]
        clean = " ".join(words)
        if 2 <= len(clean.split()) <= 4 and len(clean) <= 30: options.append(clean)
    return options[:3]

def generate_description(topic, title, script_excerpt):
    system = """You write YouTube descriptions for a dark-psychology channel.
FORMAT:
1. First 2 sentences: a hook.
2. 2-3 short paragraphs explaining the video.
3. 6 hashtags on ONE line.
4. 1 closing sentence.
RULES: No "welcome back". 180-280 words. American English only.
Return ONLY the description text."""
    user = f"Topic: {topic}\nTitle: {title}\n\nScript excerpt:\n{script_excerpt[:1500]}\n\nWrite the description now."
    desc = _llm(system, user, max_tokens=1200, temperature=0.85)
    typos = {"narcisistic": "narcissistic", "psychlogy": "psychology"}
    for bad, good in typos.items(): desc = desc.replace(bad, good)
    return desc

def generate_thumbnail_illustration_prompt(topic, script_excerpt, thumb_text):
    system = """You write ONE image prompt for a YouTube thumbnail.
CRITICAL STYLE:
- Digital illustration, hand-drawn vector crispness.
- ONE symbolic character on the LEFT-CENTER (occupy left 40%).
- RIGHT 55% COMPLETELY EMPTY for text.
- Solid gradient background. High contrast. Poster-like.
ABSOLUTE FORBIDDEN: Any text, letters, words, kanji, stamps, watermarks.
Output 60-90 words, ONLY the prompt text."""
    user = f"Topic: {topic}\nThumbnail text: {thumb_text}\n\nScript excerpt:\n{script_excerpt[:800]}\n\nWrite the illustration prompt now."
    prompt = _llm(system, user, max_tokens=300, temperature=0.9).strip()
    return prompt.strip('"').strip("'")

def _download(url, out_path, timeout=180):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.content
    if len(data) < 5000: raise Exception(f"image too small: {len(data)}")
    tmp = out_path + ".download"
    with open(tmp, "wb") as f: f.write(data)
    os.replace(tmp, out_path)

def generate_illustration(prompt, out_path):
    if not AGNES_KEY: raise Exception("no AGNES_API_KEY")
    enforced = (prompt.rstrip(".") + ". Digital illustration, ONE character on LEFT-CENTER. RIGHT HALF EMPTY. High contrast 16:9. ZERO text, watermarks.")
    payload = {"model": "agnes-image-2.1-flash", "prompt": enforced, "size": "2K", "ratio": "16:9", "extra_body": {"response_format": "url"}}
    headers = {"Authorization": f"Bearer {AGNES_KEY}", "Content-Type": "application/json"}
    for attempt in range(1, 4):
        try:
            print(f"    [AGNES] attempt {attempt}/3")
            r = requests.post(AGNES_URL, headers=headers, json=payload, timeout=240)
            r.raise_for_status()
            data = r.json()
            url = data["data"][0].get("url") or data["data"][0].get("b64_json")
            if not url: raise Exception("no url")
            _download(url, out_path)
            return out_path
        except Exception as e:
            print(f"    [AGNES] failed: {str(e)[:80]}")
            if attempt < 3: time.sleep(5)
    raise Exception("Agnes failed")

def _detect_empty_zone(img):
    try:
        small = img.resize((192, 108), Image.LANCZOS).convert("L")
        arr = numpy.array(small, dtype=float)
        h, w = arr.shape; third = w // 3
        zones = {"left": arr[:, :third], "center": arr[:, third:2*third], "right": arr[:, 2*third:]}
        variances = {k: float(v.std()) for k, v in zones.items()}
        return min(variances, key=variances.get)
    except Exception:
        return "right"

def _load_font(size):
    for p in THUMB_FONTS:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: continue
    return ImageFont.load_default()

def _wrap_text(text, max_words_per_line=2):
    words = text.upper().split()
    n = len(words)
    if n <= 3: return words
    elif n == 4: return [words[0], " ".join(words[1:3]), words[3]]
    elif n == 5: return [words[0], " ".join(words[1:3]), " ".join(words[3:])]
    else:
        per = (n + 2) // 3
        return [" ".join(words[:per]), " ".join(words[per:per*2]), " ".join(words[per*2:])]

def _fit_font_size(lines):
    if not lines: return 100
    longest = max(len(l) for l in lines)
    if longest <= 4: return 140
    elif longest <= 6: return 120
    elif longest <= 8: return 105
    elif longest <= 10: return 90
    elif longest <= 13: return 75
    return 62

def overlay_thumbnail_text(illustration_path, thumb_text, out_path, accent_idx=0):
    img = Image.open(illustration_path).convert("RGB").resize((1280, 720), Image.LANCZOS)
    zone = _detect_empty_zone(img)
    overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if zone == "right":
        for x in range(500, 1280):
            alpha = int(110 * ((x - 500) / 780))
            draw.rectangle([x, 0, x + 1, 720], fill=(0, 0, 0, alpha))
    img_rgba = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img_rgba)
    
    lines = _wrap_text(thumb_text)
    size = _fit_font_size(lines)
    font = _load_font(size)
    stroke = max(4, size // 20)
    
    metrics = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        metrics.append((bbox[2]-bbox[0], bbox[3]-bbox[1]))
    total_h = sum(h for _, h in metrics) + (len(lines)-1) * (size//8)
    total_w = max(w for w, _ in metrics)
    
    if zone == "right": x0 = int(1280 * 0.62)
    elif zone == "left": x0 = int(1280 * 0.05)
    else: x0 = (1280 - total_w) // 2
    y0 = (720 - total_h) // 2
    accent = ACCENTS[accent_idx % len(ACCENTS)]
    
    for i, line in enumerate(lines):
        w, h = metrics[i]
        x = x0
        y = y0 + sum(metrics[j][1] for j in range(i)) + i * (size//8)
        if i == 0 and len(line.split()) >= 2:
            words = line.split(); first = words[0]; rest = " ".join(words[1:])
            draw.text((x + 5, y + 5), first, font=font, fill=(0,0,0), stroke_width=stroke, stroke_fill=(0,0,0))
            draw.text((x, y), first, font=font, fill=accent, stroke_width=stroke, stroke_fill=(0,0,0))
            fw = draw.textbbox((0, 0), first, font=font, stroke_width=stroke)[2]
            draw.text((x + fw + 18 + 5, y + 5), rest, font=font, fill=(0,0,0), stroke_width=stroke, stroke_fill=(0,0,0))
            draw.text((x + fw + 18, y), rest, font=font, fill=(255,255,255), stroke_width=stroke, stroke_fill=(0,0,0))
        else:
            draw.text((x + 5, y + 5), line, font=font, fill=(0,0,0), stroke_width=stroke, stroke_fill=(0,0,0))
            draw.text((x, y), line, font=font, fill=(255,255,255), stroke_width=stroke, stroke_fill=(0,0,0))
    img_rgba.save(out_path, "PNG", optimize=True)

def package_video():
    script_path = BASE_DIR / "scripts.txt"
    script_text = script_path.read_text(encoding="utf-8").strip()
    
    video_num = None
    if STATE_FILE.exists():
        try:
            video_num = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("unique_video_number")
        except Exception: pass
        
    padded = str(video_num) if video_num else datetime.now().strftime("%Y%m%d_%H%M%S")
    seo_dir = SEO_ROOT / padded
    seo_dir.mkdir(parents=True, exist_ok=True)
    print(f"[PACK] Video #{padded} — SEO folder: {seo_dir}")

    titles = generate_titles("dark psychology", script_text) or ["The Psychology of Trauma"]
    winning_title = titles[0]
    
    thumb_texts = generate_thumbnail_texts("dark psychology", script_text) or ["THE PATTERN"]
    winning_thumb = thumb_texts[0]
    
    description = generate_description("dark psychology", winning_title, script_text)
    ill_prompt = generate_thumbnail_illustration_prompt("dark psychology", script_text, winning_thumb)
    
    raw_thumb = seo_dir / "_raw.png"
    generate_illustration(ill_prompt, str(raw_thumb))
    
    try:
        img = Image.open(str(raw_thumb))
        w, h = img.size
        img.crop((int(w*0.08), int(h*0.10), w, h)).resize((1280,720), Image.LANCZOS).save(str(raw_thumb), "PNG")
    except Exception: pass

    overlay_thumbnail_text(str(raw_thumb), winning_thumb, str(seo_dir / "thumbnail.png"), random.randint(0,3))
    if raw_thumb.exists(): raw_thumb.unlink()

    (seo_dir / "title.txt").write_text(winning_title, encoding="utf-8")
    (seo_dir / "description.txt").write_text(description, encoding="utf-8")
    (seo_dir / "thumbnail_text.txt").write_text(winning_thumb, encoding="utf-8")
    if video_num: (seo_dir / "video_number.txt").write_text(str(video_num), encoding="utf-8")
    
    meta = {"video_num": padded, "winning_title": winning_title, "thumbnail_text": winning_thumb}
    (seo_dir / "info.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

if __name__ == "__main__":
    package_video()
