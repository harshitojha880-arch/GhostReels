# final_engine.py
import os
import json
import time
import shutil
import subprocess

BASE_DIR = os.getcwd()
VIDEO_IN   = os.path.join(BASE_DIR, "video_motion_master.mp4")
VOICE_IN   = os.path.join(BASE_DIR, "voice_master.mp3")
ASS_IN     = os.path.join(BASE_DIR, "captions.ass")
BGM_IN     = os.path.join(BASE_DIR, "bgm_track.mp3")
VIDEO_SUB  = os.path.join(BASE_DIR, "video_subtitled.mp4")
MIXED_AUD  = os.path.join(BASE_DIR, "final_audio_mix.mp3")
FINAL_OUT  = os.path.join(BASE_DIR, "final_master.mp4")
STATE_FILE = os.path.join(BASE_DIR, "pipeline_state.json")

GALLERY_DIR = "/storage/emulated/0/dark psychology"
FONT_DIR = "/system/fonts"

def _run(cmd, log_tail=600):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] ffmpeg failed:\n{r.stderr[-log_tail:]}")
    return r.stdout.strip()

def _probe(path):
    out = _run(
        f'ffprobe -v error -show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 "{path}"'
    )
    return float(out)

def burn_subtitles():
    print("\n[1/4] Burning word-synced subtitles...")
    if not os.path.exists(ASS_IN):
        raise Exception(f"[X] captions.ass not found: {ASS_IN}")
    ass_escaped = ASS_IN.replace("\\", "/").replace(":", r"\:")
    vf = (
        f"subtitles=filename='{ass_escaped}':"
        f"fontsdir='{FONT_DIR}':"
        f"force_style='FontName=Droid Sans,"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"BorderStyle=1,Outline=3,Shadow=1.2'"
    )
    cmd = (
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{VIDEO_IN}" '
        f'-vf "{vf}" '
        f'-an '
        f'-c:v libx264 -preset veryfast -crf 18 -threads 2 '
        f'-pix_fmt yuv420p -movflags +faststart '
        f'"{VIDEO_SUB}"'
    )
    _run(cmd)
    dur = _probe(VIDEO_SUB)
    print(f"      OK: video_subtitled.mp4 ({dur:.2f}s)")

def mix_audio(use_bgm=True):
    print("\n[2/4] Mixing voice + BGM...")
    voice_dur = _probe(VOICE_IN)
    print(f"      Voice duration: {voice_dur:.2f}s")

    if use_bgm and os.path.exists(BGM_IN):
        looped_bgm = os.path.join(BASE_DIR, "bgm_looped.mp3")
        _run(
            f'ffmpeg -y -hide_banner -loglevel error '
            f'-stream_loop -1 -i "{BGM_IN}" '
            f'-t {voice_dur:.3f} '
            f'-af "aresample=44100,'
            f'loudnorm=I=-24:TP=-2:LRA=7,'
            f'volume=0.55,'
            f'atrim=duration={voice_dur:.3f}" '
            f'-ar 44100 -ac 2 -c:a libmp3lame -b:a 192k '
            f'"{looped_bgm}"'
        )
        mix_filter = (
            "[0:a]aresample=44100,"
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "volume=1.0[voice];"
            "[1:a]aresample=44100,"
            "aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,"
            "volume=0.055[bgm];"
            "[voice][bgm]amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0,"
            "alimiter=limit=0.95[aout]"
        )
        _run(
            f'ffmpeg -y -hide_banner -loglevel error '
            f'-i "{VOICE_IN}" '
            f'-i "{looped_bgm}" '
            f'-filter_complex "{mix_filter}" '
            f'-map "[aout]" '
            f'-t {voice_dur:.3f} '
            f'-ar 44100 -ac 2 -c:a libmp3lame -b:a 192k '
            f'"{MIXED_AUD}"'
        )
        if os.path.exists(looped_bgm):
            os.remove(looped_bgm)
    else:
        shutil.copy2(VOICE_IN, MIXED_AUD)

    print(f"      OK: final_audio_mix.mp3")

def combine():
    print("\n[3/4] Combining video + audio...")
    cmd = (
        f'ffmpeg -y -hide_banner -loglevel error '
        f'-i "{VIDEO_SUB}" '
        f'-i "{MIXED_AUD}" '
        f'-map 0:v:0 -map 1:a:0 '
        f'-c:v copy -c:a aac -b:a 192k '
        f'-shortest -movflags +faststart '
        f'"{FINAL_OUT}"'
    )
    _run(cmd)
    size_mb = os.path.getsize(FINAL_OUT) / 1024 / 1024
    print(f"      OK: final_master.mp4 ({size_mb:.1f} MB)")

def export_to_gallery():
    print("\n[4/4] Exporting to Gallery...")
    os.makedirs(GALLERY_DIR, exist_ok=True)
    
    video_num = None
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                st = json.load(f)
                video_num = st.get("unique_video_number")
        except Exception:
            pass

    target_name = f"video_{video_num}.mp4" if video_num else f"video_{int(time.time())}.mp4"
    target_path = os.path.join(GALLERY_DIR, target_name)
    
    shutil.copy2(FINAL_OUT, target_path)
    print(f"      [GALLERY] {target_path}")

if __name__ == "__main__":
    import sys
    use_bgm = "--no-bgm" not in sys.argv
    print("=" * 60)
    print(" FINAL ENGINE")
    print("=" * 60)
    burn_subtitles()
    mix_audio(use_bgm=use_bgm)
    combine()
    export_to_gallery()
    
    for f in (VIDEO_SUB, MIXED_AUD):
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

    print("\n" + "=" * 60)
    print(" COMPLETE")
    print("=" * 60)
