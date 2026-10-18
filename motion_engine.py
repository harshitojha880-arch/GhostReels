# motion_engine.py — PREMIUM VERSION
# No-repeat motions + transition assignment + content-aware

import os
import re
import json
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.getcwd()
SCENES_JSON = os.path.join(BASE_DIR, "scenes.json")
TIMINGS_JSON = os.path.join(BASE_DIR, "word_timings.json")
FRAMES_DIR = os.path.join(BASE_DIR, "frames")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
TIMELINE_JSON = os.path.join(BASE_DIR, "scene_timeline.json")
VOICE_FILE = os.path.join(BASE_DIR, "voice_master.mp3")

FPS = 25
MIN_FRAMES = 25
MAX_DURATION = 8.0  # seconds — hard cap for retention
MIN_DURATION = 3.5
OUT_W, OUT_H = 1280, 720
UPSCALE = (1600, 900)


def _run(cmd):
    try:
        # 60 seconds max per clip
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise Exception(f"[X] ffmpeg failed:\n{r.stderr[-500:]}")
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        raise Exception("[X] FFmpeg HUNG (Timeout 60s)")


def _probe_duration(path):
    out = _run(
        f'ffprobe -v error -show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 "{path}"'
    )
    return float(out)


# ============================================================
# TIMELINE (word-count based sync)
# ============================================================
def build_timeline(scenes, timings):
    total_audio = _probe_duration(VOICE_FILE)
    n_timings = len(timings)

    if n_timings == 0:
        raise Exception("[X] No word timings")

    scene_wc = []
    for s in scenes:
        wc = len([w for w in s["text"].split() if w.strip()])
        scene_wc.append(max(1, wc))

    total_words = sum(scene_wc)
    ratio = n_timings / total_words

    timeline = []
    cursor = 0

    for i, scene in enumerate(scenes):
        take = max(1, int(round(scene_wc[i] * ratio)))
        si = cursor
        ei = min(cursor + take - 1, n_timings - 1)

        if si >= n_timings:
            last = timeline[-1] if timeline else None
            st = last["end"] if last else 0.0
            en = total_audio
        else:
            st = timings[si]["start"]
            en = timings[ei]["end"]

        timeline.append({
            "id": scene["id"],
            "start": round(st, 4),
            "end": round(en, 4),
            "duration": round(max(0.5, en - st), 4),
            "text": scene["text"],
            "prompt": scene.get("prompt", ""),
        })
        cursor = ei + 1

    for i in range(len(timeline) - 1):
        ns = timeline[i + 1]["start"]
        timeline[i]["end"] = ns
        timeline[i]["duration"] = round(ns - timeline[i]["start"], 4)

    if timeline:
        timeline[-1]["end"] = total_audio
        timeline[-1]["duration"] = round(max(0.5, total_audio - timeline[-1]["start"]), 4)

    for s in timeline:
        # Cap duration for retention
        if s["duration"] > MAX_DURATION:
            s["duration"] = MAX_DURATION
            s["end"] = round(s["start"] + MAX_DURATION, 4)
        if s["duration"] < MIN_DURATION:
            s["duration"] = MIN_DURATION
            s["end"] = round(s["start"] + MIN_DURATION, 4)
        s["frames"] = max(MIN_FRAMES, int(round(s["duration"] * FPS)))

    return timeline


# ============================================================
# CONTENT ANALYSIS
# ============================================================
def _has(text, words):
    t = text.lower()
    return any(w in t for w in words)


def _suggest_motions(text):
    """Return priority-ordered list of suitable motions for this content."""
    if _has(text, ["suddenly", "shock", "jolt", "wake", "instant", "caught"]):
        return ["punch", "push", "focus", "reveal"]

    if _has(text, ["fear", "afraid", "terror", "creep", "quietly", "slowly",
                   "unknown", "silence", "secret", "hidden"]):
        return ["creep", "focus", "push", "slow_zoom_out"]

    if _has(text, ["walk", "enter", "cross", "move", "through", "past",
                   "doorway", "threshold"]):
        return ["drift_right", "drift_left", "pan_right_zoom", "pan_left_zoom"]

    if _has(text, ["look", "watch", "see", "notice", "face", "eyes",
                   "expression", "remember", "forget"]):
        return ["focus", "slow_zoom_out", "push", "creep"]

    if _has(text, ["rise", "above", "overwhelm", "up", "power", "control"]):
        return ["rise", "push", "diagonal_tr", "pan_right_zoom"]

    if _has(text, ["fall", "collapse", "loss", "sink", "down", "destroy"]):
        return ["descend", "pull", "diagonal_tl", "slow_zoom_out"]

    if _has(text, ["turn", "side", "across", "toward", "away", "left", "right"]):
        return ["diagonal_tl", "diagonal_tr", "drift_left", "drift_right"]

    return []


MOTION_POOL = [
    "push", "pull", "drift_right", "drift_left",
    "rise", "descend", "diagonal_tl", "diagonal_tr",
    "focus", "creep", "punch", "reveal",
    "slow_zoom_out", "pan_left_zoom", "pan_right_zoom",
]


def choose_motion(text, scene_id, recent):
    """
    Pick a motion that:
    - matches content if possible
    - is NOT in recent[3] (last 3 used)
    """
    suggestions = _suggest_motions(text)

    for m in suggestions:
        if m not in recent:
            return m

    # Fallback: first pool motion not in recent
    for m in MOTION_POOL:
        if m not in recent:
            return m

    # All used recently — pick offset by scene_id
    return MOTION_POOL[(scene_id + 3) % len(MOTION_POOL)]


# ============================================================
# TRANSITION SELECTION
# ============================================================
TRANSITION_POOL = [
    "fade", "dissolve", "fadeblack",
    "slideleft", "slideright",
    "smoothleft", "smoothright",
    "circleopen", "radial",
    "wipeleft", "wiperight",
    "pixelize", "hblur",
]


def _suggest_transitions(text):
    if _has(text, ["suddenly", "shock", "jolt", "instant", "caught"]):
        return ["fadeblack", "radial", "pixelize"]
    if _has(text, ["fear", "creep", "quietly", "slowly", "silence", "secret"]):
        return ["fadeblack", "dissolve", "smoothleft"]
    if _has(text, ["walk", "enter", "cross", "move", "through", "past"]):
        return ["slideleft", "slideright", "smoothleft", "smoothright"]
    if _has(text, ["turn", "across", "toward", "away", "left", "right"]):
        return ["slideleft", "slideright", "wipeleft", "wiperight"]
    if _has(text, ["rise", "above", "up", "power"]):
        return ["circleopen", "radial", "fade"]
    if _has(text, ["fall", "collapse", "down", "sink"]):
        return ["fadeblack", "hblur", "pixelize"]
    return ["fade", "dissolve", "smoothleft", "smoothright"]


def choose_transition(text, scene_id, recent):
    suggestions = _suggest_transitions(text)
    for t in suggestions:
        if t not in recent:
            return t
    for t in TRANSITION_POOL:
        if t not in recent:
            return t
    return TRANSITION_POOL[(scene_id + 2) % len(TRANSITION_POOL)]


# ============================================================
# FFmpeg filter builders
# ============================================================
def _motion_filter(motion, frames):
    d = frames
    nd = max(1, d - 1)
    p = f"(on/{nd})"
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    sx = "(iw-iw/zoom)"
    sy = "(ih-ih/zoom)"

    if motion == "push":
        z, x, y = f"1+0.08*{p}", cx, cy
    elif motion == "pull":
        z, x, y = f"1.08-0.08*{p}", cx, cy
    elif motion == "slow_zoom_out":
        z, x, y = f"1.06-0.05*{p}", cx, cy
    elif motion == "drift_right":
        z, x, y = "1.06", f"{sx}*{p}", f"{sy}*0.5"
    elif motion == "drift_left":
        z, x, y = "1.06", f"{sx}*(1-{p})", f"{sy}*0.5"
    elif motion == "rise":
        z, x, y = "1.06", f"{sx}*0.5", f"{sy}*(1-{p})"
    elif motion == "descend":
        z, x, y = "1.06", f"{sx}*0.5", f"{sy}*{p}"
    elif motion == "diagonal_tl":
        z, x, y = "1.08", f"{sx}*(1-{p})", f"{sy}*{p}"
    elif motion == "diagonal_tr":
        z, x, y = "1.08", f"{sx}*{p}", f"{sy}*{p}"
    elif motion == "focus":
        z = f"1+0.06*{p}"
        x = f"{sx}*(0.5+0.05*sin(on/{d}*PI))"
        y = f"{sy}*0.5"
    elif motion == "creep":
        z = f"1+0.04*{p}+0.006*sin(on/{d}*PI*2)"
        x = f"{sx}*(0.5+0.035*sin(on/{d}*PI))"
        y = f"{sy}*(0.5+0.025*sin(on/{d}*PI))"
    elif motion == "punch":
        z = f"1+0.11*pow(sin(on/{d}*PI),2)"
        x, y = cx, cy
    elif motion == "reveal":
        z, x, y = "1.08", f"{sx}*(1-{p})", f"{sy}*(0.28+0.44*{p})"
    elif motion == "pan_left_zoom":
        z = f"1.04+0.04*{p}"
        x, y = f"{sx}*(1-{p})", f"{sy}*0.5"
    elif motion == "pan_right_zoom":
        z = f"1.04+0.04*{p}"
        x, y = f"{sx}*{p}", f"{sy}*0.5"
    else:
        z, x, y = f"1+0.06*{p}", cx, cy

    return (
        f"zoompan=z='{z}':x='{x}':y='{y}':"
        f"d={d}:s={OUT_W}x{OUT_H}:fps={FPS}"
    )


def _effects_filter(effect):
    if effect == "impact":
        return ("eq=contrast=1.12:brightness=-0.02:saturation=1.05,"
                "unsharp=3:3:0.4:3:3:0,vignette=PI/5")
    if effect == "suspense":
        return ("eq=contrast=1.08:brightness=-0.015:saturation=0.85,"
                "colorbalance=bs=0.03:gm=0.02,"
                "unsharp=3:3:0.35:3:3:0,vignette=PI/5.5")
    if effect == "psychological":
        return ("eq=contrast=1.06:brightness=-0.008:saturation=0.9,"
                "colorbalance=rm=0.02:bm=0.03:gm=0.0,"
                "unsharp=3:3:0.4:3:3:0,vignette=PI/5.5")
    if effect == "quiet":
        return ("eq=contrast=1.03:brightness=0.005:saturation=0.95,"
                "unsharp=3:3:0.3:3:3:0,vignette=PI/7")
    return ("eq=contrast=1.05:saturation=1.0,"
            "unsharp=3:3:0.35:3:3:0,vignette=PI/5")


def choose_effect(text):
    if _has(text, ["suddenly", "shock", "impact", "realize", "reveal",
                   "truth", "caught", "instant"]):
        return "impact"
    if _has(text, ["fear", "afraid", "terror", "threat", "dark",
                   "secret", "uneasy", "creep", "unknown", "silence"]):
        return "suspense"
    if _has(text, ["memory", "remember", "forget", "brain", "confused",
                   "manipulate", "gaslight", "exploit", "deceive", "lie",
                   "emotional", "nervous"]):
        return "psychological"
    if _has(text, ["calm", "quiet", "peaceful", "slowly", "silence", "alone"]):
        return "quiet"
    return "cinematic"


# ============================================================
# CLIP BUILDER
# ============================================================
def _build_clip(image_path, out_path, frames, motion, effect):
    """Thermal-safe clip builder. ultrafast + 2 threads."""
    fc = (
        f"scale={UPSCALE[0]}:{UPSCALE[1]}:force_original_aspect_ratio=increase,"
        f"crop={UPSCALE[0]}:{UPSCALE[1]},"
        f"{_motion_filter(motion, frames)},"
        f"{_effects_filter(effect)},"
        "setsar=1,format=yuv420p"
    )

    temp = out_path + ".tmp.mp4"
    if os.path.exists(temp):
        os.remove(temp)

    _run(
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-loop 1 -framerate {FPS} -i "{image_path}" '
        f'-vf "{fc}" '
        f'-frames:v {frames} '
        f'-an '
        f'-c:v libx264 -preset ultrafast -crf 21 '
        f'-threads 2 '
        f'-x264-params "rc-lookahead=0:ref=1:bframes=0" '
        f'-pix_fmt yuv420p -movflags +faststart '
        f'"{temp}"'
    )

    if not os.path.exists(temp) or os.path.getsize(temp) < 5000:
        raise Exception("clip too small")

    os.replace(temp, out_path)


def _process_one_clip(item, total):
    """Process one clip. Returns (status, sid, detail, elapsed)."""
    sid = item["id"]
    img_path = os.path.join(FRAMES_DIR, f"scene_{sid:03d}.png")
    clip_path = os.path.join(CLIPS_DIR, f"clip_{sid:03d}.mp4")

    # Skip existing
    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 5000:
        return ("skip", sid, "exists", 0)

    if not os.path.exists(img_path):
        return ("miss", sid, "no image", 0)

    effect = choose_effect(item["text"])
    motion = item.get("motion", "push")

    t0 = time.time()
    try:
        _build_clip(img_path, clip_path, item["frames"], motion, effect)
        return ("ok", sid, f"{motion}+{effect}", time.time() - t0)
    except Exception as e:
        if os.path.exists(clip_path):
            try:
                os.remove(clip_path)
            except Exception:
                pass
        return ("fail", sid, str(e)[:80], time.time() - t0)


def run(start_from=1, workers=3):
    os.makedirs(CLIPS_DIR, exist_ok=True)

    with open(SCENES_JSON, encoding="utf-8") as f:
        scenes = json.load(f)
    with open(TIMINGS_JSON, encoding="utf-8") as f:
        timings = json.load(f)

    print("=" * 60)
    print(" PREMIUM MOTION ENGINE — PARALLEL MODE")
    print("=" * 60)
    print(f" Scenes: {len(scenes)} | FPS: {FPS} | {OUT_W}x{OUT_H}")
    print(f" Workers: {workers} | Threads/worker: 2")
    print("=" * 60)

    # Build timeline
    if os.path.exists(TIMELINE_JSON):
        print("[SYNC] Loading existing timeline...")
        with open(TIMELINE_JSON, encoding="utf-8") as f:
            timeline = json.load(f)
        if timeline and not timeline[0].get("motion"):
            timeline = build_timeline(scenes, timings)
    else:
        print("[SYNC] Building timeline...")
        timeline = build_timeline(scenes, timings)

    # Assign motions (no consecutive repeats)
    recent_motions = []
    recent_transitions = []
    for item in timeline:
        sid = item["id"]
        if "motion" not in item:
            m = choose_motion(item["text"], sid, recent_motions[-3:])
            item["motion"] = m
            recent_motions.append(m)
        if "transition" not in item:
            t = choose_transition(item["text"], sid, recent_transitions[-3:])
            item["transition"] = t
            item["transition_duration"] = 0.45
            recent_transitions.append(t)

    with open(TIMELINE_JSON, "w", encoding="utf-8") as f:
        json.dump(timeline, f, indent=2, ensure_ascii=False)

    # Filter by start_from
    work = [it for it in timeline if it["id"] >= start_from]
    total = len(work)

    print(f"[PARALLEL] Starting {total} clips with {workers} workers...\n")

    t0 = time.time()
    ok = skip = fail = miss = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_process_one_clip, item, total): item for item in work}

        for future in as_completed(futures):
            status, sid, detail, elapsed = future.result()

            if status == "ok":
                ok += 1
                done = ok + skip
                rate = done / max(1, time.time() - t0)
                eta = (total - done) / rate if rate > 0 else 0
                print(f"[{sid:3d}/{total}] OK  {detail:<28} ({elapsed:.1f}s) | "
                      f"{rate*60:.1f}/min | ETA {int(eta)}s")
            elif status == "skip":
                skip += 1
            elif status == "miss":
                miss += 1
                print(f"[{sid:3d}/{total}] MISS no image")
            else:
                fail += 1
                print(f"[{sid:3d}/{total}] FAIL {detail}")

    elapsed_total = time.time() - t0
    print("\n" + "=" * 60)
    print(f" COMPLETE — Generated: {ok} | Skipped: {skip} | Failed: {fail} | Miss: {miss}")
    print(f" Time: {elapsed_total/60:.1f} min | Avg: {elapsed_total/max(1,ok):.1f}s/clip")
    print(f" Clips: {CLIPS_DIR}/")
    print("=" * 60)
    return ok



if __name__ == "__main__":
    import sys
    start = 1
    if "--start" in sys.argv:
        start = int(sys.argv[sys.argv.index("--start") + 1])
    run(start_from=start)
