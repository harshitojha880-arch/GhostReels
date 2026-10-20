import os, json, time, subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCENES_JSON = BASE_DIR / "scenes.json"
TIMINGS_JSON = BASE_DIR / "word_timings.json"
FRAMES_DIR = BASE_DIR / "frames"
CLIPS_DIR = BASE_DIR / "clips"
TIMELINE_JSON = BASE_DIR / "scene_timeline.json"
VOICE_FILE = BASE_DIR / "voice_master.mp3"

FPS, MIN_FRAMES, OUT_W, OUT_H = 25, 25, 1280, 720
UPSCALE = (2560, 1440)

def _run(cmd, timeout=60):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0: raise Exception(f"FFmpeg: {r.stderr[-200:]}")

def _probe(path):
    cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'
    return float(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip())

def build_timeline(scenes, timings):
    total_audio, n_timings = _probe(str(VOICE_FILE)), len(timings)
    scene_wc = [max(1, len(s["text"].split())) for s in scenes]
    ratio = n_timings / sum(scene_wc)
    timeline, cursor = [], 0
    for i, scene in enumerate(scenes):
        take = max(1, int(round(scene_wc[i] * ratio)))
        si, ei = cursor, min(cursor + take - 1, n_timings - 1)
        st, en = (timings[si]["start"], timings[ei]["end"]) if si < n_timings else ((timeline[-1]["end"] if timeline else 0.0), total_audio)
        timeline.append({"id": scene["id"], "start": round(st, 4), "end": round(en, 4), "duration": round(max(0.5, en - st), 4), "text": scene["text"]})
        cursor = ei + 1
    for i in range(len(timeline) - 1):
        ns = timeline[i + 1]["start"]
        timeline[i]["end"] = ns
        timeline[i]["duration"] = round(ns - timeline[i]["start"], 4)
    if timeline:
        timeline[-1]["end"] = total_audio
        timeline[-1]["duration"] = round(max(0.5, total_audio - timeline[-1]["start"]), 4)
    for s in timeline: s["frames"] = max(MIN_FRAMES, int(round(s["duration"] * FPS)))
    with open(TIMELINE_JSON, "w") as f: json.dump(timeline, f, indent=2)
    return timeline

def _motion_filter(motion, frames):
    d, nd = frames, max(1, frames - 1)
    p = f"(on/{nd})"
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    sx, sy = "(iw-iw/zoom)", "(ih-ih/zoom)"
    if motion == "push": z, x, y = f"1+0.08*{p}", cx, cy
    elif motion == "pull": z, x, y = f"1.08-0.08*{p}", cx, cy
    elif motion == "pan_left": z, x, y = "1.06", f"{sx}*(1-{p})", f"{sy}*0.5"
    elif motion == "pan_right": z, x, y = "1.06", f"{sx}*{p}", f"{sy}*0.5"
    elif motion == "diagonal_tl": z, x, y = "1.08", f"{sx}*(1-{p})", f"{sy}*{p}"
    elif motion == "diagonal_tr": z, x, y = "1.08", f"{sx}*{p}", f"{sy}*{p}"
    elif motion == "slow_zoom": z, x, y = f"1+0.04*{p}", f"{sx}*(0.5+0.05*sin(on/{d}*PI))", f"{sy}*0.5"
    else: z, x, y = f"1+0.05*{p}", cx, cy
    return f"zoompan=z='{z}':x='{x}':y='{y}':d={d}:s={OUT_W}x{OUT_H}:fps={FPS}"

def _build_clip(img, out, frames, motion):
    fc = f"scale={UPSCALE[0]}:{UPSCALE[1]}:flags=lanczos,crop={UPSCALE[0]}:{UPSCALE[1]},{_motion_filter(motion, frames)},eq=contrast=1.06:saturation=1.1,setsar=1,format=yuv420p"
    cmd = f'ffmpeg -y -hide_banner -loglevel error -loop 1 -framerate {FPS} -i "{img}" -vf "{fc}" -frames:v {frames} -an -c:v libx264 -preset ultrafast -crf 20 -threads 1 -pix_fmt yuv420p "{out}"'
    _run(cmd)

def run(start_from=1):
    os.makedirs(CLIPS_DIR, exist_ok=True)
    with open(SCENES_JSON) as f: scenes = json.load(f)
    with open(TIMINGS_JSON) as f: timings = json.load(f)
    print("="*50 + "\n CINEMATIC MOTION ENGINE (Thermal Safe)\n" + "="*50)
    timeline = json.load(open(TIMELINE_JSON)) if os.path.exists(TIMELINE_JSON) else build_timeline(scenes, timings)
    modes = ["push", "pull", "pan_left", "pan_right", "diagonal_tl", "diagonal_tr", "slow_zoom"]
    total, ok, skip, fail = len(timeline), 0, 0, 0
    for item in timeline:
        sid = item["id"]
        if sid < start_from: continue
        img, clip = FRAMES_DIR / f"scene_{sid:03d}.png", CLIPS_DIR / f"clip_{sid:03d}.mp4"
        if clip.exists() and clip.stat().st_size > 5000: skip += 1; continue
        if not img.exists(): fail += 1; continue
        motion = modes[(sid - 1) % len(modes)]
        print(f"[{sid:3d}/{total}] {motion:<15} ({item['duration']:.1f}s)")
        try:
            _build_clip(str(img), str(clip), item["frames"], motion)
            ok += 1
        except Exception as e:
            print(f"  [!] FAIL: {e}"); fail += 1
        time.sleep(1.0)
        if (ok + skip) % 15 == 0: print("  [GUARD] 5s Thermal Cooldown..."); time.sleep(5)
    print(f"\n COMPLETE: {ok} Generated | {skip} Skipped | {fail} Failed")

if __name__ == "__main__":
    import sys
    run(int(sys.argv[sys.argv.index("--start") + 1]) if "--start" in sys.argv else 1)
