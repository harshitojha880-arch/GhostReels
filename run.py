#!/usr/bin/env python3
# run.py — Dark Psychology Autopilot — Final Integrated Pipeline
# All systems: cloud LLM chain, local Qwen, video numbering, thermal/RAM guards.

import os
import re
import sys
import json
import time
import shutil
import signal
import threading
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.box import ROUNDED, HEAVY
from rich.console import Group

import thermal_monitor
import memory_monitor
import video_counter


# ============================================================
# PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
FRAMES_DIR = BASE_DIR / "frames"
CLIPS_DIR = BASE_DIR / "clips"
SCRIPTS_DIR = BASE_DIR / "scripts_history"
STATE_FILE = BASE_DIR / "pipeline_state.json"
GALLERY_DIR = Path("/storage/emulated/0/dark psychology")

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
          "motion", "assembly", "final", "package"]

STAGE_LABELS = {
    "script":   "Writing Script",
    "split":    "Splitting Scenes",
    "prompts":  "Generating Prompts",
    "images":   "Rendering Images",
    "voice":    "Synthesizing Voice",
    "motion":   "Building Motion Clips",
    "assembly": "Assembling Video",
    "final":    "Finalizing Master",
    "package":  "Packaging SEO + Thumbnail",
}

STAGE_SCRIPTS = {
    "split":    [("scene_splitter.py", [])],
    "prompts":  [("prompt_builder.py", [])],
    "images":   [("agnes_engine.py", [])],
    "voice":    [("voice_engine.py", []), ("fix_subtitles.py", [])],
    "motion":   [("motion_engine.py", [])],
    "assembly": [("assembly_engine.py", [])],
    "final":    [("final_engine.py", ["--no-bgm"])],
    "package":  [("packaging_engine.py", [])],
}

# ============================================================
# LICENSE CHECK
# ============================================================
import hmac
import hashlib
import base64

SECRET = "GHOSTREELS_SECRET_SALT_987654321"
LICENSE_FILE = BASE_DIR / ".license"

def generate_key(email):
    msg = email.lower().strip().encode()
    sig = hmac.new(SECRET.encode(), msg, hashlib.sha256).digest()
    b32 = base64.b32encode(sig).decode().upper()
    raw = b32[:16]
    return f"GHOST-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

def check_license():
    if LICENSE_FILE.exists():
        try:
            data = json.loads(LICENSE_FILE.read_text())
            if data.get("key") == generate_key(data.get("email", "")):
                return True
        except Exception:
            pass
    
    print("\n[!] LICENSE REQUIRED TO RUN GHOSTREELS")
    print("Please enter your Email ID and License Key.")
    email = input("Email: ").strip()
    key = input("License Key: ").strip()
    
    if key == generate_key(email):
        LICENSE_FILE.write_text(json.dumps({"email": email, "key": key}))
        print("[OK] License activated successfully!\n")
        return True
    else:
        print("[X] Invalid License Key. Please contact the seller.")
        return False

if not check_license():
    import sys
    sys.exit(1)
# ============================================================

console = Console()


# ============================================================
# STATE (UI)
# ============================================================
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.stage_status = {
            s: {"status": "pending", "start": None, "end": None,
                "cur": 0, "tot": 0}
            for s in STAGES
        }
        self.current_stage = None
        self.video_number = 0
        self.unique_video_number = 0
        self.total_videos = 0
        self.loop_started = None
        self.video_started = None
        self.stop_flag = False
        self.recent_logs = deque(maxlen=10)
        self.last_completed = None

    def add_log(self, line):
        ts = datetime.now().strftime("%H:%M:%S")
        line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", str(line))
        self.recent_logs.append((ts, line.rstrip()[:130]))


STATE = State()


# ============================================================
# PERSISTENT STATE
# ============================================================
DEFAULT_STATE = {
    "run_id": None,
    "video_number": 0,
    "unique_video_number": 0,
    "script_topic": None,
    "stages": {},
    "started_at": None,
    "updated_at": None,
    "total_videos": 0,
}


def load_pstate():
    if not STATE_FILE.exists():
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


def save_pstate(st):
    st["updated_at"] = datetime.now().isoformat()
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


def new_pstate_run(st):
    st["run_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
    st["video_number"] = int(st.get("video_number", 0)) + 1
    st["started_at"] = datetime.now().isoformat()
    st["stages"] = {s: "pending" for s in STAGES}
    st["script_topic"] = None
    save_pstate(st)
    return st


def pstate_mark(st, stage, status):
    st["stages"][stage] = status
    save_pstate(st)


# ============================================================
# HELPERS
# ============================================================
def bar(pct, width=22, fill="━", empty="─", head="╸"):
    pct = max(0, min(100, int(pct)))
    if pct <= 0:
        return empty * width
    if pct >= 100:
        return fill * width
    n = int(width * pct / 100)
    return fill * n + head + empty * (width - n - 1)


def fmt_time(sec):
    if sec is None or sec < 0:
        return "--:--"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def count_prompts():
    try:
        with open(BASE_DIR / "scenes_text.json", encoding="utf-8") as f:
            total = len(json.load(f))
    except Exception:
        total = 0
    try:
        with open(BASE_DIR / "scenes.json", encoding="utf-8") as f:
            done = sum(1 for s in json.load(f) if s.get("prompt"))
    except Exception:
        done = 0
    return done, total


def count_files(directory, pattern):
    if not directory.exists():
        return 0
    count = 0
    for p in directory.glob(pattern):
        if ".tmp" in p.name or ".download" in p.name or ".attempt" in p.name:
            continue
        try:
            if p.stat().st_size > 5000:
                count += 1
        except (FileNotFoundError, OSError):
            continue
    return count


def count_total_scenes():
    for fname in ("scenes.json", "scenes_text.json"):
        try:
            with open(BASE_DIR / fname, encoding="utf-8") as f:
                return len(json.load(f))
        except Exception:
            continue
    return 0


def stage_progress(stage):
    if stage == "prompts":
        return count_prompts()
    if stage == "images":
        return count_files(FRAMES_DIR, "scene_*.png"), count_total_scenes()
    if stage == "motion":
        return count_files(CLIPS_DIR, "clip_*.mp4"), count_total_scenes()
    return 0, 0


# ============================================================
# GUARDS
# ============================================================
def _wait_if_hot(max_wait_min=45):
    try:
        too_hot, temp, reason = thermal_monitor.is_too_hot()
    except Exception:
        return
    if not too_hot:
        return

    t_str = f"{temp:.1f}C" if temp is not None else "?"
    STATE.add_log(f"[THERMAL] {reason} {t_str} — cooling down")

    t0 = time.time()
    while time.time() - t0 < max_wait_min * 60:
        if STATE.stop_flag:
            break
        try:
            if thermal_monitor.is_cool_enough():
                break
        except Exception:
            break
        time.sleep(20)

    STATE.add_log("[THERMAL] Cool enough — continuing")


def _clean_ram():
    try:
        free = memory_monitor.free_mb()
    except Exception:
        return

    if free < 800:
        STATE.add_log(f"[RAM] low ({free:.0f}MB) — cleaning")

    import gc
    gc.collect()

    if free < 300:
        STATE.add_log(f"[RAM] critical — restarting llama-server")
        try:
            from local_gemma_server import stop_server, start_server
            stop_server()
            time.sleep(5)
            start_server()
        except Exception as e:
            STATE.add_log(f"[RAM] restart failed: {e}")


# ============================================================
# SUBPROCESS RUNNER (live output)
# ============================================================
def run_subprocess(script_name, args=None):
    cmd = [sys.executable, script_name] + (args or [])
    proc = subprocess.Popen(
        cmd, cwd=str(BASE_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    for line in proc.stdout:
        if line.strip():
            STATE.add_log(line)
    proc.wait()
    return proc.returncode


# ============================================================
# FORCE CLEAR FOR STAGES
# ============================================================
def _force_clear_for_stage(stage):
    if stage == "images":
        # Resume-safe — Agnes skips existing
        if FRAMES_DIR.exists():
            existing = [p for p in FRAMES_DIR.glob("scene_*.png")
                        if p.stat().st_size > 5000]
            if existing:
                STATE.add_log(f"[PRE] Resuming images: {len(existing)} present")
            else:
                STATE.add_log(f"[PRE] Fresh start for images")
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    elif stage == "motion":
        if CLIPS_DIR.exists():
            n = len(list(CLIPS_DIR.glob("*")))
            if n > 0:
                STATE.add_log(f"[PRE] Clearing {n} old clips...")
            shutil.rmtree(CLIPS_DIR, ignore_errors=True)
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        tl = BASE_DIR / "scene_timeline.json"
        if tl.exists():
            try:
                tl.unlink()
            except Exception:
                pass

    elif stage == "voice":
        for f in ("voice_master.mp3", "word_timings.json",
                  "captions.srt", "captions.ass"):
            p = BASE_DIR / f
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass


# ============================================================
# STAGE EXECUTION
# ============================================================
def run_stage(stage, pstate):
    STATE.current_stage = stage
    info = STATE.stage_status[stage]
    info["status"] = "running"
    info["start"] = time.time()
    info["cur"] = 0
    info["tot"] = 0

    # Mark stage running (so resume knows)
    pstate["stages"][stage] = "running"
    save_pstate(pstate)

    # Guards
    _wait_if_hot()
    _clean_ram()
    _force_clear_for_stage(stage)

    STATE.add_log(f">> START: {STAGE_LABELS[stage]}")

    try:
        if stage == "script":
            from script_writer import generate_dark_psychology_script
            script, topic, winning, top2 = generate_dark_psychology_script()
            (BASE_DIR / "scripts.txt").write_text(script, encoding="utf-8")
            pstate["script_topic"] = topic
            save_pstate(pstate)
            STATE.add_log(f"OK Script: {len(script.split())} words")
        else:
            for script_name, args in STAGE_SCRIPTS[stage]:
                rc = run_subprocess(script_name, args)
                if rc != 0:
                    raise Exception(f"{script_name} failed (exit {rc})")

        info["status"] = "done"
        info["end"] = time.time()
        STATE.add_log(f"OK DONE: {STAGE_LABELS[stage]}")

        # Free KV cache after heavy stages
        if stage in ("script", "split", "prompts", "package"):
            try:
                from local_gemma_server import clear_kv_cache
                clear_kv_cache()
            except Exception:
                pass

        time.sleep(2)
        pstate_mark(pstate, stage, "done")

    except Exception as e:
        info["status"] = "failed"
        info["end"] = time.time()
        STATE.add_log(f"FAIL: {stage} — {str(e)[:80]}")
        pstate_mark(pstate, stage, "failed")
        raise


# ============================================================
# CLEANUP
# ============================================================
def cleanup(pstate):
    STATE.add_log("[CLEANUP] Archiving + cleaning")
    SCRIPTS_DIR.mkdir(exist_ok=True)

    src = BASE_DIR / "scripts.txt"
    if src.exists():
        topic = (pstate.get("script_topic") or "unknown")[:50]
        topic = re.sub(r"[^a-zA-Z0-9]+", "_", topic).strip("_")
        run_id = pstate.get("run_id", "run")
        vnum = pstate.get("unique_video_number", 0)
        dst = SCRIPTS_DIR / f"{vnum:04d}_{run_id}_{topic}.txt"
        try:
            shutil.copy2(src, dst)
            STATE.add_log(f"[CLEANUP] Archived: {dst.name}")
        except Exception as e:
            STATE.add_log(f"[CLEANUP] Archive failed: {e}")

    for fname in ARTIFACT_FILES:
        p = BASE_DIR / fname
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    for d in (FRAMES_DIR, CLIPS_DIR):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(exist_ok=True)

    # Rotate log if > 5MB
    try:
        log_path = BASE_DIR / "pipeline.log"
        if log_path.exists() and log_path.stat().st_size > 5 * 1024 * 1024:
            bak = BASE_DIR / "pipeline.log.1"
            if bak.exists():
                bak.unlink()
            log_path.rename(bak)
            log_path.write_text("")
    except Exception:
        pass

    # Reset UI for next video
    for s in STAGES:
        STATE.stage_status[s] = {
            "status": "pending", "start": None, "end": None,
            "cur": 0, "tot": 0,
        }
    STATE.current_stage = None
    STATE.video_started = None

    STATE.add_log("[CLEANUP] Done")


# ============================================================
# VIDEO WORKFLOW
# ============================================================
def _is_incomplete_run(pstate):
    stages = pstate.get("stages") or {}
    if not stages:
        return False
    completed = [s for s in STAGES if stages.get(s) == "done"]
    pending = [s for s in STAGES if stages.get(s) != "done"]
    return len(completed) > 0 and len(pending) > 0


def run_one_video(pstate):
    is_resume = _is_incomplete_run(pstate)

    if is_resume:
        STATE.add_log(f"[RESUME] Continuing video #{pstate.get('unique_video_number', '?')}")
        STATE.video_number = int(pstate.get("video_number", 0))
        STATE.unique_video_number = int(pstate.get("unique_video_number", 0))
        for s in STAGES:
            st_status = pstate["stages"].get(s, "pending")
            STATE.stage_status[s] = {
                "status": st_status,
                "start": None, "end": None,
                "cur": 0, "tot": 0,
            }
    else:
        # Claim unique number
        try:
            claimed = video_counter.claim_number()
            pstate["unique_video_number"] = claimed
            STATE.add_log(f"[NUMBER] Assigned video #{claimed:04d}")
        except Exception as e:
            STATE.add_log(f"[NUMBER] claim failed: {e}")
            claimed = 0

        pstate = new_pstate_run(pstate)
        STATE.video_number = pstate["video_number"]
        STATE.unique_video_number = claimed

    STATE.video_started = time.time()

    # ============================================================
    # UI STAGE STATUS RESET
    # ============================================================
    if is_resume:
        # Resume: reflect pstate accurately
        for s in STAGES:
            st = pstate["stages"].get(s, "pending")
            if st == "done":
                STATE.stage_status[s] = {
                    "status": "done", "start": None, "end": None,
                    "cur": 0, "tot": 0,
                }
            elif st == "running":
                STATE.stage_status[s] = {
                    "status": "pending", "start": None, "end": None,
                    "cur": 0, "tot": 0,
                }
            else:
                STATE.stage_status[s] = {
                    "status": "pending", "start": None, "end": None,
                    "cur": 0, "tot": 0,
                }
    else:
        # Fresh video: reset ALL to pending
        for s in STAGES:
            STATE.stage_status[s] = {
                "status": "pending", "start": None, "end": None,
                "cur": 0, "tot": 0,
            }

    for stage in STAGES:
        st = pstate["stages"].get(stage)
        if st == "done":
            STATE.stage_status[stage]["status"] = "done"
            STATE.add_log(f"SKIP: {STAGE_LABELS[stage]}")
            continue
        if st == "running":
            STATE.add_log(f"[REDO] {STAGE_LABELS[stage]} (interrupted)")

        # Retry stage up to 2 times
        stage_failed = False
        for attempt in range(1, 3):
            try:
                run_stage(stage, pstate)
                break
            except Exception as e:
                STATE.add_log(f"[STAGE RETRY] {stage} {attempt}/2: {str(e)[:80]}")
                if attempt < 2:
                    time.sleep(30)
                else:
                    stage_failed = True

        if stage_failed:
            # Package is optional — don't kill video
            if stage == "package":
                STATE.add_log(f"[SKIP-OPTIONAL] {stage} failed but video is done")
                pstate["stages"][stage] = "done"
                save_pstate(pstate)
                STATE.stage_status[stage]["status"] = "failed"
                continue
            else:
                raise Exception(f"critical stage {stage} failed")

    STATE.total_videos = int(pstate.get("total_videos", 0)) + 1
    pstate["total_videos"] = STATE.total_videos
    save_pstate(pstate)

    # Mark video complete in counter
    if pstate.get("unique_video_number"):
        try:
            video_counter.mark_complete(pstate["unique_video_number"])
        except Exception:
            pass

    STATE.last_completed = datetime.now()
    STATE.current_stage = None

    return pstate


def worker_loop():
    pstate = load_pstate()

    if pstate.get("stages"):
        pending = [s for s in STAGES if pstate["stages"].get(s) != "done"]
        if pending:
            STATE.add_log(f"[RESUME] Pending: {', '.join(pending)}")

    while not STATE.stop_flag:
        try:
            pstate = run_one_video(pstate)
            cleanup(pstate)

            STATE.add_log("[LOOP] Video ready — cooling down 5 min")
            for _ in range(300):
                if STATE.stop_flag:
                    break
                time.sleep(1)

        except Exception as e:
            STATE.add_log(f"[ERROR] {str(e)[:100]}")
            STATE.add_log("[RETRY] Waiting 60s...")
            for _ in range(60):
                if STATE.stop_flag:
                    break
                time.sleep(1)


# ============================================================
# UI RENDER
# ============================================================
def render():
    header = Panel(
        Align.center(
            Text.from_markup(
                "[bold bright_cyan]GHOSTREELS STUDIO[/]\n"
                "[dim]Turn Any Niche Into a Faceless Video Factory[/]"
            )
        ),
        box=HEAVY, border_style="bright_cyan", padding=(0, 2),
    )

    runtime = fmt_time(time.time() - STATE.loop_started) if STATE.loop_started else "--:--"
    vid_runtime = (fmt_time(time.time() - STATE.video_started)
                   if STATE.video_started else "--:--")

    vnum = STATE.unique_video_number if STATE.unique_video_number else STATE.video_number

    status_bar = Table.grid(expand=True)
    for _ in range(5):
        status_bar.add_column(justify="center")
    status_bar.add_row(
        f"[dim]Video #[/]\n[bold yellow]{vnum:04d}[/]",
        f"[dim]Completed[/]\n[bold green]{STATE.total_videos}[/]",
        f"[dim]This Video[/]\n[bold cyan]{vid_runtime}[/]",
        f"[dim]Total Runtime[/]\n[bold cyan]{runtime}[/]",
        f"[dim]Loop[/]\n[bold green]* ACTIVE[/]",
    )

    done = sum(1 for s in STAGES if STATE.stage_status[s]["status"] == "done")
    pct = int(done / len(STAGES) * 100)
    overall = Text.from_markup(
        f"  [bold]Overall[/]  "
        f"[bright_cyan]{bar(pct, 44)}[/]  "
        f"[bold yellow]{pct:3d}%[/]   "
        f"[dim]Stage {done}/{len(STAGES)}[/]"
    )

    stages_tbl = Table(box=None, show_header=False, padding=(0, 1))
    stages_tbl.add_column(width=2)
    stages_tbl.add_column(width=24)
    stages_tbl.add_column(width=28)
    stages_tbl.add_column(justify="right", width=12)

    for stage in STAGES:
        info = STATE.stage_status[stage]
        st = info["status"]
        label = STAGE_LABELS[stage]

        if st == "done":
            elapsed = (info["end"] or time.time()) - (info["start"] or 0) if info["start"] else 0
            icon = "[green]v[/]"
            name = f"[green]{label}[/]"
            detail = "[green]complete[/]"
            tcol = f"[dim]{fmt_time(elapsed)}[/]"
        elif st == "running":
            elapsed = time.time() - info["start"]
            icon = "[yellow]>[/]"
            name = f"[bold yellow]{label}[/]"
            cur, tot = stage_progress(stage)
            info["cur"], info["tot"] = cur, tot
            if tot > 0 and cur >= 0:
                p = int(cur / tot * 100) if tot else 0
                detail = f"[yellow]{bar(p, 20)}[/] [white]{cur}/{tot}[/]"
            else:
                detail = "[yellow]working...[/]"
            tcol = f"[yellow]{fmt_time(elapsed)}[/]"
        elif st == "failed":
            icon = "[red]x[/]"
            name = f"[red]{label}[/]"
            detail = "[red]failed[/]"
            tcol = "[red]--[/]"
        else:
            icon = "[dim]o[/]"
            name = f"[dim]{label}[/]"
            detail = "[dim]pending[/]"
            tcol = "[dim]--[/]"

        stages_tbl.add_row(icon, name, detail, tcol)

    # Current task
    if STATE.current_stage:
        cs = STATE.current_stage
        info = STATE.stage_status[cs]
        if info["status"] == "running":
            elapsed = time.time() - info["start"]
            cur, tot = stage_progress(cs)
            if tot > 0 and cur > 0:
                rate = cur / max(elapsed, 0.1)
                eta = (tot - cur) / rate if rate > 0 else 0
                task = Text.from_markup(
                    f"  [bold yellow]>[/]  [bold]{STAGE_LABELS[cs]}[/]\n"
                    f"     [dim]Elapsed[/] [cyan]{fmt_time(elapsed)}[/]   "
                    f"[dim]Rate[/] [cyan]{rate*60:.1f}/min[/]   "
                    f"[dim]ETA[/] [yellow]{fmt_time(eta)}[/]"
                )
            else:
                task = Text.from_markup(
                    f"  [bold yellow]>[/]  [bold]{STAGE_LABELS[cs]}[/]\n"
                    f"     [dim]Elapsed[/] [cyan]{fmt_time(elapsed)}[/]   "
                    f"[dim]processing...[/]"
                )
        else:
            task = Text.from_markup("  [dim]transitioning...[/]")
    else:
        task = Text.from_markup("  [dim]initializing pipeline...[/]")

    task_panel = Panel(task, title="[bold yellow]CURRENT TASK[/]",
                       border_style="yellow", box=ROUNDED, padding=(0, 1))

    # Activity log
    if STATE.recent_logs:
        log_lines = []
        for ts, line in list(STATE.recent_logs)[-9:]:
            styled = line
            if "OK" in line or "DONE" in line: styled = f"[green]{line}[/]"
            elif "FAIL" in line or "ERROR" in line: styled = f"[red]{line}[/]"
            elif "START" in line or ">>" in line: styled = f"[yellow]{line}[/]"
            elif "SKIP" in line or "RESUME" in line or "NUMBER" in line: styled = f"[cyan]{line}[/]"
            log_lines.append(f"[dim]{ts}[/]  {styled}")
        log_text = "\n".join(log_lines)
    else:
        log_text = "[dim]waiting...[/]"

    log_panel = Panel(log_text, title="[bold bright_black]ACTIVITY[/]",
                      border_style="bright_black", box=ROUNDED, padding=(0, 1))

    footer = Align.center(Text.from_markup(
        "[dim]Ctrl+C to stop  |  State auto-saved  |  "
        "Gallery: /storage/emulated/0/GhostReels/[/]"
    ))

    return Group(header, status_bar, "", overall, "",
                 stages_tbl, "", task_panel, log_panel, "", footer)


# ============================================================
# MAIN
# ============================================================
def _ensure_llama_server():
    try:
        from local_gemma_server import ensure_server
        STATE.add_log("[BOOT] Ensuring llama-server...")
        ensure_server()
        STATE.add_log("[BOOT] llama-server ready")
    except Exception as e:
        STATE.add_log(f"[BOOT] llama-server failed: {e}")


def handle_sigint(sig, frame):
    if STATE.stop_flag:
        console.print("\n[red]Force quit[/]")
        sys.exit(1)
    STATE.stop_flag = True
    console.print("\n[yellow]Stopping gracefully...[/]")


def main():
    signal.signal(signal.SIGINT, handle_sigint)
    STATE.loop_started = time.time()

    # Auto-run niche selector if config missing
    config_file = BASE_DIR / "niche_config.json"
    if not config_file.exists():
        print("[BOOT] No niche selected. Running selector...")
        subprocess.run([sys.executable, "niche_selector.py"])

    try:
        GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    _ensure_llama_server()

    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

    try:
        with Live(render(), console=console, screen=True,
                  refresh_per_second=4) as live:
            while not STATE.stop_flag:
                live.update(render())
                time.sleep(0.25)
    except KeyboardInterrupt:
        STATE.stop_flag = True

    console.print("\n[green]Pipeline stopped. State saved.[/]")
    console.print(f"[dim]Gallery: {GALLERY_DIR}[/]")
    console.print(f"[dim]Scripts archive: {SCRIPTS_DIR}[/]\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run one video only")
    args = p.parse_args()

    if args.once:
        # Single video mode
        console.print("[yellow]Single-video mode[/]")
        pstate = load_pstate()
        try:
            pstate = run_one_video(pstate)
            cleanup(pstate)
            console.print("[green]Video complete[/]")
        except Exception as e:
            console.print(f"[red]Failed: {e}[/]")
    else:
        main()
