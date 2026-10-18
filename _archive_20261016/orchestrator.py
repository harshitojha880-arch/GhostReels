# orchestrator.py
# Simple autonomous loop — no daemon, runs in foreground.
# Live output. Crash-resumable. Infinite loop.

import os
import re
import sys
import json
import time
import shutil
import signal
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "pipeline_state.json")
GALLERY_DIR = "/storage/emulated/0/dark psychology"
FRAMES_DIR = os.path.join(BASE_DIR, "frames")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts_history")

ARTIFACT_FILES = [
    "scripts.txt", "scenes.json", "scenes_text.json",
    "voice_raw.mp3", "voice_master.mp3", "voice_tight.mp3",
    "word_timings.json", "captions.srt", "captions.ass",
    "scene_timeline.json",
    "video_motion_master.mp4", "video_subtitled.mp4",
    "final_audio_mix.mp3", "final_master.mp4",
    "bgm_track.mp3", "bgm_looped.mp3", "silence_filter.txt",
    "test_agnes.png", "subtitle_check.mp4",
]

STAGES = ["script", "split", "prompts", "images", "voice",
          "motion", "assembly", "final"]

DEFAULT_STATE = {
    "run_id": None,
    "video_number": 0,
    "script_topic": None,
    "stages": {},
    "started_at": None,
    "updated_at": None,
    "total_videos": 0,
}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ============================================================
# STATE
# ============================================================
def load_state():
    if not os.path.exists(STATE_FILE):
        return dict(DEFAULT_STATE)
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        if not isinstance(st, dict):
            return dict(DEFAULT_STATE)
        for k, v in DEFAULT_STATE.items():
            st.setdefault(k, v)
        return st
    except Exception:
        return dict(DEFAULT_STATE)


def save_state(st):
    st["updated_at"] = datetime.now().isoformat()
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


def new_run(state):
    state["run_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
    state["video_number"] = int(state.get("video_number", 0)) + 1
    state["started_at"] = datetime.now().isoformat()
    state["stages"] = {s: "pending" for s in STAGES}
    state["script_topic"] = None
    save_state(state)
    log(f"===== NEW RUN #{state['video_number']} =====")


def mark(state, stage, status):
    state["stages"][stage] = status
    save_state(state)


def stage_done(state, stage):
    return state["stages"].get(stage) == "done"


# ============================================================
# STAGE RUNNER — live output, no capture
# ============================================================
def run_py(script_name, args=None):
    """Run a python script in BASE_DIR, live output to terminal."""
    cmd = [sys.executable, script_name] + (args or [])
    log(f"  Running: {' '.join(cmd)}")
    rc = subprocess.run(cmd, cwd=BASE_DIR)
    if rc.returncode != 0:
        raise Exception(f"{script_name} exited with code {rc.returncode}")


# ============================================================
# STAGES
# ============================================================
def stage_script(state):
    from script_writer import generate_dark_psychology_script

    log("[SCRIPT] Writing dark-psychology script...")
    script, topic = generate_dark_psychology_script()

    with open(os.path.join(BASE_DIR, "scripts.txt"), "w",
              encoding="utf-8") as f:
        f.write(script)

    state["script_topic"] = topic
    save_state(state)

    wc = len(script.split())
    log(f"[SCRIPT] Done — {wc} words | Topic: {topic}")
    mark(state, "script", "done")


def stage_split(state):
    log("[SPLIT] Splitting into scenes...")
    run_py("scene_splitter.py")

    with open(os.path.join(BASE_DIR, "scenes_text.json"), encoding="utf-8") as f:
        scenes = json.load(f)
    if not scenes:
        raise Exception("No scenes produced")
    log(f"[SPLIT] Done — {len(scenes)} scenes")
    mark(state, "split", "done")


def stage_prompts(state):
    log("[PROMPT] Generating prompts (~10-12 min)...")
    run_py("prompt_builder.py")

    with open(os.path.join(BASE_DIR, "scenes.json"), encoding="utf-8") as f:
        scenes = json.load(f)
    done = sum(1 for s in scenes if s.get("prompt"))
    if done < len(scenes) * 0.9:
        raise Exception(f"Prompts incomplete: {done}/{len(scenes)}")
    log(f"[PROMPT] Done — {done}/{len(scenes)}")
    mark(state, "prompts", "done")


def stage_images(state):
    log("[IMAGE] Generating images via Agnes (~45 min)...")
    run_py("agnes_engine.py")

    with open(os.path.join(BASE_DIR, "scenes.json"), encoding="utf-8") as f:
        scenes = json.load(f)

    missing = []
    for s in scenes:
        p = os.path.join(FRAMES_DIR, f"scene_{s['id']:03d}.png")
        if not os.path.exists(p) or os.path.getsize(p) < 5000:
            missing.append(s["id"])
    if missing:
        raise Exception(f"{len(missing)} images missing")
    log(f"[IMAGE] Done — {len(scenes)} images")
    mark(state, "images", "done")


def stage_voice(state):
    log("[VOICE] Generating narration + subtitles (~3 min)...")
    run_py("voice_engine.py")

    # Regenerate ASS with no-flicker fix
    log("[VOICE] Fixing subtitles (no flicker, lower placement)...")
    run_py("fix_subtitles.py")

    log("[VOICE] Done")
    mark(state, "voice", "done")


def stage_motion(state):
    log("[MOTION] Building clips (~15-20 min)...")

    # Clean old clips + timeline so motion engine rebuilds fresh
    if os.path.exists(os.path.join(BASE_DIR, "scene_timeline.json")):
        os.remove(os.path.join(BASE_DIR, "scene_timeline.json"))
    if os.path.isdir(CLIPS_DIR):
        shutil.rmtree(CLIPS_DIR)
    os.makedirs(CLIPS_DIR, exist_ok=True)

    run_py("motion_engine.py")

    with open(os.path.join(BASE_DIR, "scenes.json"), encoding="utf-8") as f:
        scenes = json.load(f)

    missing = []
    for s in scenes:
        p = os.path.join(CLIPS_DIR, f"clip_{s['id']:03d}.mp4")
        if not os.path.exists(p) or os.path.getsize(p) < 5000:
            missing.append(s["id"])
    if missing:
        raise Exception(f"{len(missing)} clips missing")
    log(f"[MOTION] Done — {len(scenes)} clips")
    mark(state, "motion", "done")


def stage_assembly(state):
    log("[ASSEMBLY] Merging with transitions (~8-10 min)...")
    run_py("assembly_engine.py")

    out = os.path.join(BASE_DIR, "video_motion_master.mp4")
    if not os.path.exists(out) or os.path.getsize(out) < 100000:
        raise Exception("video_motion_master.mp4 missing")
    log("[ASSEMBLY] Done")
    mark(state, "assembly", "done")


def stage_final(state):
    log("[FINAL] Burning subtitles + mixing voice (~5 min)...")
    run_py("final_engine.py", ["--no-bgm"])

    out = os.path.join(BASE_DIR, "final_master.mp4")
    if not os.path.exists(out) or os.path.getsize(out) < 100000:
        raise Exception("final_master.mp4 missing")

    size_mb = os.path.getsize(out) / 1024 / 1024
    log(f"[FINAL] Done — {size_mb:.1f} MB")
    mark(state, "final", "done")


# ============================================================
# CLEANUP
# ============================================================
def cleanup(state):
    log("[CLEANUP] Archiving script and deleting artifacts...")

    os.makedirs(SCRIPTS_DIR, exist_ok=True)

    # Archive script
    script_src = os.path.join(BASE_DIR, "scripts.txt")
    if os.path.exists(script_src):
        topic_slug = re.sub(
            r"[^a-zA-Z0-9]+", "_",
            (state.get("script_topic") or "unknown")[:50]
        ).strip("_")
        run_id = state.get("run_id", "run")
        archive = os.path.join(SCRIPTS_DIR, f"{run_id}_{topic_slug}.txt")
        try:
            shutil.copy2(script_src, archive)
            log(f"  Archived: {archive}")
        except Exception as e:
            log(f"  Archive failed: {e}")

    # Delete per-video artifacts
    for fname in ARTIFACT_FILES:
        p = os.path.join(BASE_DIR, fname)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    # Delete frames/ and clips/
    for d in (FRAMES_DIR, CLIPS_DIR):
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
            except Exception:
                pass
        os.makedirs(d, exist_ok=True)

    log("[CLEANUP] Done")


# ============================================================
# ONE VIDEO
# ============================================================
def run_one_video(state):
    new_run(state)

    stage_funcs = {
        "script":   stage_script,
        "split":    stage_split,
        "prompts":  stage_prompts,
        "images":   stage_images,
        "voice":    stage_voice,
        "motion":   stage_motion,
        "assembly": stage_assembly,
        "final":    stage_final,
    }

    for stage in STAGES:
        if stage_done(state, stage):
            log(f"[SKIP] {stage} already done")
            continue

        log(f"[STAGE] >> {stage.upper()}")
        try:
            stage_funcs[stage](state)
        except Exception as e:
            log(f"[FAIL] {stage}: {e}")
            mark(state, stage, "failed")
            raise

    state["total_videos"] = int(state.get("total_videos", 0)) + 1
    save_state(state)

    log(f"===== VIDEO #{state['video_number']} COMPLETE "
        f"(total: {state['total_videos']}) =====")


# ============================================================
# MAIN LOOP
# ============================================================
def loop(forever=True, delay=15):
    print("=" * 60)
    print("  AUTONOMOUS PIPELINE — infinite loop")
    print("=" * 60)
    print(f"  Gallery:  {GALLERY_DIR}")
    print(f"  State:    {STATE_FILE}")
    print(f"  Delay:    {delay}s between videos")
    print("  Stop:     Ctrl+C")
    print("=" * 60)

    state = load_state()

    if state.get("stages"):
        pending = [s for s in STAGES if state["stages"].get(s) != "done"]
        if pending:
            log(f"[RESUME] Interrupted run detected")
            log(f"[RESUME] Pending stages: {', '.join(pending)}")

    while True:
        try:
            run_one_video(state)
            cleanup(state)

            log(f"[LOOP] Sleeping {delay}s before next video...")
            for i in range(delay, 0, -1):
                print(f"\r[LOOP] Next in {i:2d}s ...", end="", flush=True)
                time.sleep(1)
            print()

        except KeyboardInterrupt:
            log("[STOP] Ctrl+C — saving state")
            save_state(state)
            break

        except Exception as e:
            log(f"[ERROR] {e}")
            log("[RETRY] Waiting 60s before retry...")
            for i in range(60, 0, -1):
                print(f"\r[RETRY] Retry in {i:2d}s ...", end="", flush=True)
                time.sleep(1)
            print()
            # Retry from where we stopped (state has stage marks)

        if not forever:
            break


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true",
                   help="Run only one video (test mode)")
    p.add_argument("--delay", type=int, default=15,
                   help="Seconds between videos")
    args = p.parse_args()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    loop(forever=not args.once, delay=args.delay)
