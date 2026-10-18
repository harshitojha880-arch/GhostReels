# assembly_engine.py
# Assembles clips with xfade transitions (batch-based, Termux-friendly)
# Reads scene_timeline.json for per-clip transition types

import os
import json
import subprocess
import shutil

BASE_DIR = os.getcwd()
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
TIMELINE_JSON = os.path.join(BASE_DIR, "scene_timeline.json")
SILENT_VIDEO = os.path.join(BASE_DIR, "video_motion_master.mp4")

FPS = 25
BATCH_SIZE = 5   # small batches to keep ffmpeg happy on Termux


def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] ffmpeg failed:\n{r.stderr[-600:]}")
    return r.stdout.strip()


def _probe(path):
    out = _run(
        f'ffprobe -v error -show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 "{path}"'
    )
    return float(out)


def _xfade_filter(n, durations, transitions, transition_dur=0.45):
    """
    Build xfade chain for n inputs.
    transitions[i] = transition between clip i and i+1 (for i in 0..n-2)
    """
    parts = []
    prev = "[0:v]"
    cum = durations[0]

    for i in range(1, n):
        ttype = transitions[i - 1]
        td = transition_dur
        offset = max(0.0, cum - td)

        out = f"[vx{i}]"
        parts.append(
            f"{prev}[{i}:v]xfade=transition={ttype}:"
            f"duration={td:.3f}:offset={offset:.3f}{out}"
        )
        prev = out
        cum += durations[i] - td

    return ";".join(parts), prev, cum


def _merge_group(clip_paths, clip_durations, transitions,
                 out_path, label):
    """Merge one group with xfade transitions."""
    n = len(clip_paths)

    if n == 1:
        shutil.copy2(clip_paths[0], out_path)
        return _probe(out_path)

    inputs = " ".join(f'-i "{c}"' for c in clip_paths)
    filter_complex, final_label, total_dur = _xfade_filter(
        n, clip_durations, transitions, transition_dur=0.45
    )

    cmd = (
        f'ffmpeg -y -hide_banner -loglevel error '
        f'{inputs} '
        f'-filter_complex "{filter_complex}" '
        f'-map "{final_label}" '
        f'-an -c:v libx264 -preset ultrafast -crf 21 -threads 2 '
        f'-pix_fmt yuv420p -movflags +faststart '
        f'"{out_path}"'
    )

    _run(cmd)

    if not os.path.exists(out_path) or os.path.getsize(out_path) < 5000:
        raise Exception(f"{label} output too small")

    return _probe(out_path)


def assemble():
    print("=" * 60)
    print(" ASSEMBLY ENGINE — xfade transitions")
    print("=" * 60)

    with open(TIMELINE_JSON, encoding="utf-8") as f:
        timeline = json.load(f)

    # Collect clips (must exist)
    clip_paths = []
    clip_durations = []
    transitions = []

    for i, item in enumerate(timeline):
        sid = item["id"]
        clip = os.path.join(CLIPS_DIR, f"clip_{sid:03d}.mp4")
        if not os.path.exists(clip):
            raise Exception(f"[X] Missing clip: {clip}")
        clip_paths.append(clip)
        clip_durations.append(_probe(clip))

    # Transition between clip i and clip i+1 = timeline[i]["transition"]
    for i in range(len(timeline) - 1):
        transitions.append(timeline[i].get("transition", "fade"))

    total = len(clip_paths)
    print(f" Clips: {total}")
    print(f" Total raw duration: {sum(clip_durations):.2f}s")
    print(f" Batch size: {BATCH_SIZE}")

    # ---- Batch 1: Merge small groups ----
    batch_files = []
    batch_durations = []

    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for b in range(num_batches):
        start = b * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_num = b + 1

        batch_clips = clip_paths[start:end]
        batch_durs = clip_durations[start:end]
        batch_trans = transitions[start:end - 1]

        batch_path = os.path.join(BASE_DIR, f"assemble_batch_{batch_num:03d}.mp4")

        if os.path.exists(batch_path) and os.path.getsize(batch_path) > 5000:
            print(f"[BATCH {batch_num}/{num_batches}] REUSE")
            batch_dur = _probe(batch_path)
        else:
            print(f"[BATCH {batch_num}/{num_batches}] "
                  f"scenes {start+1}-{end} | {len(batch_clips)} clips")
            ttypes = ", ".join(batch_trans)
            print(f"    transitions: {ttypes}")
            batch_dur = _merge_group(
                batch_clips, batch_durs, batch_trans,
                batch_path, f"batch {batch_num}"
            )

        batch_files.append(batch_path)
        batch_durations.append(batch_dur)
        print(f"    -> {batch_dur:.2f}s")

    # ---- Final merge ----
    if len(batch_files) == 1:
        shutil.copy2(batch_files[0], SILENT_VIDEO)
        total_dur = _probe(SILENT_VIDEO)
    else:
        print(f"\n[MASTER] Merging {len(batch_files)} batch masters...")
        # Between batches: use "fade"
        master_transitions = ["fade"] * (len(batch_files) - 1)
        total_dur = _merge_group(
            batch_files, batch_durations, master_transitions,
            SILENT_VIDEO, "master"
        )

    print(f"\n[MASTER] Total: {total_dur:.2f}s")
    print(f"[MASTER] Saved: {SILENT_VIDEO}")

    # Cleanup batches
    for bf in batch_files:
        if os.path.exists(bf) and bf != SILENT_VIDEO:
            try: os.remove(bf)
            except: pass

    print("=" * 60)
    print(" ASSEMBLY COMPLETE")
    print("=" * 60)
    return SILENT_VIDEO


if __name__ == "__main__":
    assemble()
