import os, json, subprocess, shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CLIPS_DIR = BASE_DIR / "clips"
TIMELINE_JSON = BASE_DIR / "scene_timeline.json"
SILENT_VIDEO = BASE_DIR / "video_motion_master.mp4"
BATCH_SIZE = 6

def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
    if r.returncode != 0: raise Exception(f"FFmpeg: {r.stderr[-200:]}")
    return r.stdout.strip()

def _probe(path):
    return float(_run(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"'))

def _build_xfade(clips, durs, trans, out):
    if len(clips) == 1: shutil.copy2(clips[0], out); return _probe(out)
    inputs, parts, prev, cum = " ".join(f'-i "{c}"' for c in clips), [], "[0:v]", durs[0]
    td = 0.4
    for i in range(1, len(clips)):
        offset = max(0.0, cum - td)
        out_lbl = f"[vx{i}]"
        parts.append(f"{prev}[{i}:v]xfade=transition={trans[i-1]}:duration={td:.3f}:offset={offset:.3f}{out_lbl}")
        prev, cum = out_lbl, cum + durs[i] - td
    _run(f'ffmpeg -y -hide_banner -loglevel error {inputs} -filter_complex "{";".join(parts)}" -map "{prev}" -an -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p -movflags +faststart "{out}"')
    return _probe(out)

def assemble():
    print("="*50 + "\n CINEMATIC ASSEMBLY (Transitions)\n" + "="*50)
    timeline = json.load(open(TIMELINE_JSON))
    clips, durs = [str(CLIPS_DIR / f"clip_{i['id']:03d}.mp4") for i in timeline], [_probe(str(CLIPS_DIR / f"clip_{i['id']:03d}.mp4")) for i in timeline]
    trans = [["fade", "dissolve", "slideleft", "slideright", "smoothleft", "smoothright", "circleopen", "radial"][(timeline[i]["id"] - 1) % 8] for i in range(len(timeline) - 1)]
    total, batches, b_durs = len(clips), [], []
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for b in range(num_batches):
        s, e = b * BATCH_SIZE, min((b + 1) * BATCH_SIZE, total)
        bp = str(BASE_DIR / f"batch_{b+1:03d}.mp4")
        if os.path.exists(bp): print(f"[BATCH {b+1}/{num_batches}] REUSE")
        else:
            print(f"[BATCH {b+1}/{num_batches}] Rendering...")
            _build_xfade(clips[s:e], durs[s:e], trans[s:e-1], bp)
        batches.append(bp)
        b_durs.append(_probe(bp))
    if len(batches) == 1: shutil.copy2(batches[0], str(SILENT_VIDEO))
    else:
        print(f"[MASTER] Merging {len(batches)} batches...")
        _build_xfade(batches, b_durs, ["fade"] * (len(batches) - 1), str(SILENT_VIDEO))
    for b in batches:
        if os.path.exists(b) and b != str(SILENT_VIDEO):
            try: os.remove(b)
            except: pass
    print(f"[MASTER] Ready: {SILENT_VIDEO.name}")

if __name__ == "__main__":
    assemble()
