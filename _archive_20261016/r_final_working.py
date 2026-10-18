import os
import re
import subprocess
import time
import json
import asyncio
import requests
import edge_tts

BASE_DIR = os.getcwd()
SCRIPT_FILE = os.path.join(BASE_DIR, "scripts.txt")
STATE_FILE = os.path.join(BASE_DIR, "pipeline_state_flash.json")
GALLERY_DIR = "/storage/emulated/0/Movies/WhatElse"

def run_cmd(command):
    retries = 3

    for attempt in range(retries):
        try:
            result = subprocess.run(
                command,
                shell=True,
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            return result.stdout.strip()

        except subprocess.CalledProcessError as e:
            print(
                f"[!] Command failed "
                f"(Attempt {attempt + 1}/{retries}): {e}"
            )

            if e.stderr:
                print(e.stderr.strip())

            time.sleep(1)

        except Exception as e:
            print(
                f"[!] Unexpected system error "
                f"(Attempt {attempt + 1}/{retries}): {e}"
            )

            time.sleep(1)

    raise Exception(
        f"[X] Critical command failure after {retries} attempts:\n{command}"
    )

def load_state():
    default_state = {
        "last_completed_scene": 0,
        "scenes": [],
        "clips": []
    }

    if not os.path.exists(STATE_FILE):
        return default_state

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            return default_state

        state = json.loads(content)

        if not isinstance(state, dict):
            return default_state

        state.setdefault("last_completed_scene", 0)
        state.setdefault("scenes", [])
        state.setdefault("clips", [])

        return state

    except (json.JSONDecodeError, OSError, TypeError) as e:
        print(f"[!] State file invalid or unreadable: {e}")

        backup_file = STATE_FILE + ".broken"

        try:
            os.replace(STATE_FILE, backup_file)
            print(f"[!] Broken state backed up to: {backup_file}")
        except OSError:
            pass

        return default_state


def save_state(state_data):
    temp_file = STATE_FILE + ".tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                state_data,
                f,
                indent=4,
                ensure_ascii=False
            )
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, STATE_FILE)

    except OSError as e:
        print(f"[X] Failed to save pipeline state: {e}")

        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass

        raise


def load_and_split_script():
    state = load_state()

    if state.get("scenes"):
        print(f"[✓] Loaded {len(state['scenes'])} scenes from saved state.")
        return state["scenes"]

    if not os.path.exists(SCRIPT_FILE):
        raise Exception(f"[X] Script file not found: {SCRIPT_FILE}")

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        raise Exception("[X] scripts.txt is empty.")

    # Normalize whitespace.
    content = re.sub(r"\s+", " ", content).strip()

    # Split only at real sentence endings.
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", content)
        if s.strip()
    ]

    if not sentences:
        raise Exception("[X] No usable narration found in scripts.txt.")

    # Merge very short fragments with the following sentence.
    merged = []
    pending = ""

    for sentence in sentences:
        if pending:
            sentence = pending + " " + sentence
            pending = ""

        word_count = len(sentence.split())

        # Short fragments, headings and continuation phrases belong
        # to the surrounding visual thought rather than becoming
        # isolated scenes.
        if word_count < 10:
            pending = sentence
        else:
            merged.append(sentence)

    if pending:
        if merged:
            merged[-1] = merged[-1] + " " + pending
        else:
            merged.append(pending)

    scenes = []

    def build_visual_direction(scene_text):
        """
        Generic scene director.
        The narration is the only source of truth.
        No topic-specific visual is hard-coded here.
        """

        clean_text = " ".join(scene_text.split()).strip()

        return (
            "Visually interpret ONLY the exact narration provided for this scene. "
            f"The exact narration is: \"{clean_text}\". "
            "Determine the most literal and visually understandable moment "
            "described or strongly implied by these words. "
            "Show the actual subjects, their physical actions, interactions, "
            "important objects, location, environment and emotional body "
            "language required by this specific moment. "
            "If multiple important people are required by the narration, "
            "show them together in the same frame and make their relationship "
            "and actions visually clear. "
            "If the narration describes a person performing an action, show "
            "that action rather than a portrait of the person. "
            "If it describes an interaction, show the interaction. "
            "If it describes an object or place, make that object or place "
            "clearly visible and relevant to the composition. "
            "If the narration is abstract, use a restrained cinematic visual "
            "metaphor that still communicates the specific meaning of the "
            "narration. "
            "Never force a recurring visual concept into a scene when the "
            "current narration does not require it. "
            "Do not reuse the visual idea of another scene merely for style. "
            "The final frame must tell the current scene's story even with "
            "the audio muted."
        )


    visual_styles = [
        "photorealistic cinematic documentary photography, natural skin texture, realistic physical environment, controlled dramatic lighting",
        "photorealistic psychological thriller cinematography, realistic human expressions, atmospheric practical lighting, cinematic depth",
        "premium cinematic film still, physically believable environment, natural human proportions, sophisticated dramatic lighting",
        "high-end documentary reenactment, realistic people and locations, subtle film lighting, authentic visual details",
        "serious psychological drama cinematography, photorealistic environment, believable body language, dramatic but natural lighting",
        "cinematic investigative documentary frame, realistic human behavior, detailed environment, controlled shadows",
        "premium streaming-series film still, photorealistic subjects, realistic architecture and props, sophisticated composition"
    ]

    camera_variants = [
        "wide establishing shot showing the complete environment and spatial relationships",
        "medium shot clearly showing the subjects and their interaction",
        "over-the-shoulder shot showing the relationship between the people and the environment",
        "cinematic medium-wide shot showing the complete physical action",
        "close-to-medium shot emphasizing facial expression and body language while keeping the environment recognizable",
        "side-angle cinematic shot showing the action and surrounding context",
        "dramatic but natural eye-level film shot with strong depth"
    ]

    for index, scene_text in enumerate(merged, start=1):
        visual_direction = build_visual_direction(scene_text)

        style = visual_styles[(index - 1) % len(visual_styles)]
        camera = camera_variants[(index - 1) % len(camera_variants)]

        visual_prompt = (
            f"{style}. "
            f"{camera}. "
            "Create ONE highly specific cinematic visual frame for the exact "
            f"story moment described by this narration: \"{scene_text}\". "

            f"{visual_direction} "

            "The image must function as a literal visual reenactment of this "
            "specific story moment. Every important subject mentioned or "
            "strongly implied by the narration must be visually represented. "
            "Show the correct number of important people when the scene "
            "requires multiple people. Do not silently remove secondary "
            "characters just because one person is easier to generate. "

            "Prioritize visible actions, relationships, body language, "
            "facial expressions, objects, location and spatial context. "
            "Make the scene understandable even if the narration audio is "
            "muted. "

            "Do NOT create a generic psychology illustration, generic "
            "portrait, generic brain image, generic businessman image, "
            "generic mysterious person, abstract concept art or unrelated "
            "stock-photo composition. Do not replace a concrete story event "
            "with a symbolic image. "

            "Do not add written words, captions, subtitles, labels, logos, "
            "watermarks, UI elements, diagrams or infographic elements. "
            "Photorealistic cinematic quality, coherent anatomy, natural "
            "human proportions, believable environment, realistic lighting, "
            "professional visual storytelling, 16:9 composition."
        )

        scenes.append({
            "id": index,
            "text": scene_text,
            "prompt": visual_prompt
        })

    save_state(state)

    print(f"[✓] Created {len(scenes)} meaningful scene prompts.")

    for scene in scenes[:3]:
        print(f"[SCENE {scene['id']}] {scene['text'][:120]}")

    return scenes


async def generate_perfect_voice(scenes):
    """
    PROFESSIONAL NARRATION ENGINE — EXACT TIMELINE MODE

    IMPORTANT:
    - Edge-TTS WordBoundary timestamps are the source of truth.
    - Audio timeline is NEVER shortened, trimmed, stretched or compressed.
    - Studio processing is timeline-safe.
    - Subtitle timings therefore remain perfectly synchronized.
    """

    audio_file = os.path.join(BASE_DIR, "master_voice.mp3")
    raw_audio_path = os.path.join(BASE_DIR, "raw_edge_voice.mp3")
    timings_file = os.path.join(BASE_DIR, "word_timings.json")
    srt_file = os.path.join(BASE_DIR, "captions.srt")

    print("[🎙️] Generating professional narration + EXACT word timings...")

    if not os.path.exists(SCRIPT_FILE):
        raise Exception(f"[X] Script file not found: {SCRIPT_FILE}")

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        script_text = f.read().strip()

    if not script_text:
        raise Exception("[X] scripts.txt is empty.")

    # --------------------------------------------------------
    # EDGE TTS
    # --------------------------------------------------------

    communicate = edge_tts.Communicate(
        script_text,
        "en-US-ChristopherNeural",
        rate="+2%",
        volume="+0%",
        pitch="-2Hz",
        boundary="WordBoundary"
    )

    words = []

    try:
        with open(raw_audio_path, "wb") as f:

            async for chunk in communicate.stream():

                if chunk["type"] == "audio":
                    f.write(chunk["data"])

                elif chunk["type"] == "WordBoundary":

                    offset = chunk.get("offset", 0)
                    duration = chunk.get("duration", 0)
                    text = chunk.get("text", "").strip()

                    if text:

                        start_time = offset / 10000000.0
                        end_time = (
                            offset + duration
                        ) / 10000000.0

                        words.append({
                            "word": text,
                            "start": start_time,
                            "end": end_time
                        })

    except Exception as e:
        raise Exception(
            f"[X] Edge TTS generation failed: {e}"
        )

    if not words:
        raise Exception(
            "[X] No WordBoundary events received."
        )

    if (
        not os.path.exists(raw_audio_path)
        or os.path.getsize(raw_audio_path) == 0
    ):
        raise Exception("[X] Empty TTS audio.")

    print(
        f"[✓] Exact WordBoundary timings captured: "
        f"{len(words)} words"
    )

    # --------------------------------------------------------
    # CRITICAL SYNC RULE
    #
    # DO NOT USE:
    #   silenceremove
    #   atrim
    #   silence compression
    #   time compression
    #   tempo changes
    #
    # Any of these can change the timeline and break
    # Edge-TTS WordBoundary synchronization.
    # --------------------------------------------------------

    print(
        "[🔒 SYNC LOCK] Original narration timeline preserved"
    )

    # --------------------------------------------------------
    # TIMELINE-SAFE STUDIO PROCESSING
    # --------------------------------------------------------

    studio_filters = (
        "highpass=f=70,"
        "lowpass=f=15500,"
        "afftdn=nr=8:nf=-35,"
        "acompressor="
        "threshold=-18dB:"
        "ratio=2.2:"
        "attack=8:"
        "release=90:"
        "makeup=2,"
        "loudnorm=I=-15:TP=-1.5:LRA=7"
    )

    print(
        "[🎚️] Applying timeline-safe studio vocal processing..."
    )

    run_cmd(
        f'ffmpeg -y -hide_banner '
        f'-i "{raw_audio_path}" '
        f'-af "{studio_filters}" '
        f'-codec:a libmp3lame '
        f'-b:a 192k '
        f'"{audio_file}"'
    )

    if (
        not os.path.exists(audio_file)
        or os.path.getsize(audio_file) == 0
    ):
        raise Exception(
            "[X] Final studio voice was not created."
        )

    # --------------------------------------------------------
    # FINAL AUDIO DURATION
    # --------------------------------------------------------

    duration_cmd = (
        f'ffprobe -v error '
        f'-show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 '
        f'"{audio_file}"'
    )

    try:
        total_audio_duration = float(
            run_cmd(duration_cmd)
        )
    except Exception as e:
        raise Exception(
            f"[X] Could not read final voice duration: {e}"
        )

    if total_audio_duration <= 0:
        raise Exception(
            "[X] Invalid final voice duration."
        )

    print(
        f"[✓] Final voice duration: "
        f"{total_audio_duration:.2f}s"
    )

    # --------------------------------------------------------
    # EXACT TIMING PRESERVATION
    #
    # NO REMAPPING.
    # NO SILENCE COMPENSATION.
    #
    # Edge-TTS timestamps already belong to the exact
    # narration timeline that we preserved.
    # --------------------------------------------------------

    exact_timings = []

    for item in words:

        st = max(
            0.0,
            float(item["start"])
        )

        en = max(
            st + 0.02,
            float(item["end"])
        )

        # Never allow timestamps beyond final audio.
        st = min(
            st,
            total_audio_duration
        )

        en = min(
            en,
            total_audio_duration
        )

        if en <= st:
            continue

        exact_timings.append({
            "word": str(item["word"]),
            "start": round(st, 4),
            "end": round(en, 4)
        })

    if not exact_timings:
        raise Exception(
            "[X] No valid synchronized word timings remain."
        )

    # --------------------------------------------------------
    # SAVE MASTER WORD TIMINGS
    # --------------------------------------------------------

    with open(
        timings_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            exact_timings,
            f,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # CREATE GROUPED SRT
    # --------------------------------------------------------

    def srt_time(sec):

        sec = max(
            0.0,
            float(sec)
        )

        h = int(sec // 3600)
        m = int((sec % 3600) // 60)

        remainder = sec % 60
        s = int(remainder)

        ms = int(
            round(
                (remainder - s) * 1000
            )
        )

        if ms >= 1000:
            s += 1
            ms = 0

        return (
            f"{h:02d}:"
            f"{m:02d}:"
            f"{s:02d},"
            f"{ms:03d}"
        )

    groups = []

    # Six words per SRT block.
    # Actual highlighted ASS continues to use
    # the individual exact word timings.
    for i in range(
        0,
        len(exact_timings),
        6
    ):

        chunk = exact_timings[
            i:i + 6
        ]

        if not chunk:
            continue

        groups.append(
            (
                chunk[0]["start"],
                chunk[-1]["end"],
                " ".join(
                    x["word"]
                    for x in chunk
                )
            )
        )

    with open(
        srt_file,
        "w",
        encoding="utf-8"
    ) as f:

        for idx, (
            st,
            en,
            text
        ) in enumerate(
            groups,
            1
        ):

            f.write(
                f"{idx}\n"
            )

            f.write(
                f"{srt_time(st)} --> "
                f"{srt_time(en)}\n"
            )

            f.write(
                f"{text}\n\n"
            )

    print(
        f"[✓] Exact synchronized timings saved: "
        f"{len(exact_timings)} words"
    )

    print(
        f"[✓] Subtitle groups created: "
        f"{len(groups)}"
    )

    print(
        f"[✓] Timing file: "
        f"{timings_file}"
    )

    print(
        f"[✓] SRT file: "
        f"{srt_file}"
    )

    print(
        f"[🔒] AUDIO/SUBTITLE TIMELINE LOCKED"
    )

    if os.path.exists(raw_audio_path):
        try:
            os.remove(raw_audio_path)
        except Exception:
            pass

    return (
        audio_file,
        total_audio_duration
    )


def fetch_scene_image(prompt, output_filename):
    """
    Pollinations + Flux image provider.

    Generates one 16:9 cinematic scene image and writes it
    atomically so partial downloads never become valid outputs.
    """

    import urllib.parse

    if not prompt or not str(prompt).strip():
        raise Exception("[X] Empty scene image prompt")

    output_filename = os.path.abspath(output_filename)
    os.makedirs(os.path.dirname(output_filename), exist_ok=True)

    encoded_prompt = urllib.parse.quote(
        str(prompt).strip(),
        safe=""
    )

    url = (
        "https://image.pollinations.ai/prompt/"
        + encoded_prompt
        + "?model=flux"
        + "&width=1280"
        + "&height=720"
        + "&nologo=true"
        + "&enhance=true"
    )

    temp_filename = output_filename + ".download"

    last_error = None

    for attempt in range(1, 4):
        try:
            print(
                f"[🌐] Pollinations image request "
                f"{attempt}/3"
            )

            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except Exception:
                    pass

            response = requests.get(
                url,
                timeout=(20, 180),
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            if response.status_code != 200:
                raise Exception(
                    f"HTTP {response.status_code}"
                )

            data = response.content

            if not data or len(data) < 1000:
                raise Exception(
                    f"Image response too small: {len(data)} bytes"
                )

            content_type = (
                response.headers
                .get("content-type", "")
                .lower()
            )

            if "image" not in content_type:
                # Pollinations can occasionally return an error body.
                preview = data[:200].decode(
                    "utf-8",
                    errors="ignore"
                )
                raise Exception(
                    f"Non-image response: {content_type} "
                    f"{preview}"
                )

            with open(temp_filename, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())

            if (
                not os.path.exists(temp_filename)
                or os.path.getsize(temp_filename) < 1000
            ):
                raise Exception(
                    "[X] Downloaded image is invalid"
                )

            # Atomic replacement.
            os.replace(
                temp_filename,
                output_filename
            )

            print(
                f"[✓] Scene image ready: "
                f"{output_filename}"
            )

            return output_filename

        except Exception as e:
            last_error = e

            print(
                f"[!] Pollinations attempt "
                f"{attempt}/3 failed: {e}"
            )

            if attempt < 3:
                time.sleep(2 * attempt)

    if os.path.exists(temp_filename):
        try:
            os.remove(temp_filename)
        except Exception:
            pass

    raise Exception(
        f"[X] Pollinations image generation failed: "
        f"{last_error}"
    )

def process_scenes_flash(scenes, total_audio_duration):
    """
    RESUMABLE SCENE GENERATION ENGINE

    Guarantees:
      - Successful scenes are never regenerated.
      - Failed scene is retried independently.
      - Checkpoint is saved immediately after every successful scene.
      - Existing valid clips are reused.
      - Corrupt/incomplete outputs are discarded.
      - Network/API/FFmpeg failures do not reset progress.
      - Safe to restart after crash, Termux kill or connection failure.
    """

    def valid_file(path, minimum_size=1000):
        try:
            return (
                os.path.exists(path)
                and os.path.isfile(path)
                and os.path.getsize(path) >= minimum_size
            )
        except Exception:
            return False

    def checkpoint(scene_id, clips):
        """
        Atomic checkpoint after every successful scene.
        """
        state["last_completed_scene"] = int(scene_id)
        state["clips"] = list(
            dict.fromkeys(clips)
        )

        save_state(state)

        print(
            f"[💾 CHECKPOINT] Scene {scene_id} permanently saved"
        )

    def choose_motion(scene_text, scene_id):
        t = scene_text.lower()

        if any(k in t for k in [
            "suddenly", "shock", "shocking", "realize",
            "revealed", "discover", "warning", "impact",
            "truth", "caught", "instant"
        ]):
            return "punch"

        if any(k in t for k in [
            "fear", "afraid", "terrifying", "terror",
            "danger", "threat", "dark", "secret",
            "uneasy", "creepy", "silence", "quietly",
            "slowly", "unknown"
        ]):
            return "creep"

        if any(k in t for k in [
            "enter", "entered", "entering", "walk",
            "walking", "move", "moving", "cross",
            "crossing", "through", "doorway", "threshold",
            "room"
        ]):
            return "drift"

        if any(k in t for k in [
            "look", "watch", "see", "focus", "notice",
            "face", "eyes", "expression", "memory",
            "brain", "remember", "forget", "confused"
        ]):
            return "focus"

        if any(k in t for k in [
            "manipulator", "manipulators", "manipulate",
            "gaslight", "gaslighting", "exploit",
            "deceive", "lie", "hidden", "reveal",
            "revealing", "exposed"
        ]):
            return "reveal"

        if any(k in t for k in [
            "rise", "rising", "above", "overwhelming",
            "power", "control", "dominant", "pressure"
        ]):
            return "rise"

        if any(k in t for k in [
            "fall", "falling", "collapse", "loss",
            "losing", "breakdown", "destroyed"
        ]):
            return "descend"

        if any(k in t for k in [
            "side", "across", "direction", "turn",
            "turning", "left", "right", "toward"
        ]):
            return "diagonal"

        modes = [
            "push",
            "pull",
            "drift",
            "focus",
            "creep",
            "reveal",
            "diagonal",
            "rise",
            "descend",
            "punch"
        ]

        return modes[(scene_id - 1) % len(modes)]

    def choose_story_effect(scene_text, scene_id):
        t = scene_text.lower()

        if any(k in t for k in (
            "suddenly", "shock", "shocking", "impact",
            "realize", "revealed", "discover", "truth",
            "caught", "instant"
        )):
            return "impact"

        if any(k in t for k in (
            "fear", "afraid", "terrifying", "terror",
            "danger", "threat", "dark", "secret",
            "uneasy", "creepy", "unknown"
        )):
            return "suspense"

        if any(k in t for k in (
            "memory", "remember", "forget", "forgot",
            "brain", "confused", "psychological",
            "manipulator", "manipulate", "gaslight",
            "gaslighting", "exploit", "deceive", "lie"
        )):
            return "psychological"

        if any(k in t for k in (
            "calm", "quiet", "peaceful", "slowly",
            "silence", "alone"
        )):
            return "quiet"

        return "cinematic"

    # -------------------------------------------------
    # RESUME / SCENE LOOP
    # -------------------------------------------------


    # -------------------------------------------------
    # HARD RESUME / CLIP RECONCILIATION
    # -------------------------------------------------

    state = load_state()

    total_scenes = len(scenes)

    # Existing valid clips are the real source of truth.
    # This prevents regeneration after a later-stage failure.

    valid_existing_clips = []

    for _scene in scenes:
        try:
            _sid = int(_scene["id"])
        except Exception:
            continue

        _clip = os.path.join(
            BASE_DIR,
            f"clip_{_sid}.mp4"
        )

        if valid_file(_clip):
            valid_existing_clips.append(_clip)

    valid_existing_clips = list(
        dict.fromkeys(valid_existing_clips)
    )

    # Find the highest CONTIGUOUS valid scene.
    # 1..76 valid + 77 missing = resume at 77.
    # 1..77 valid = skip scene generation entirely.

    _resume_completed = 0

    for _sid in range(1, total_scenes + 1):

        _clip = os.path.join(
            BASE_DIR,
            f"clip_{_sid}.mp4"
        )

        if valid_file(_clip):
            _resume_completed = _sid
        else:
            break

    _checkpoint_completed = int(
        state.get(
            "last_completed_scene",
            0
        ) or 0
    )

    # Never move backwards because a later pipeline stage failed.
    completed = max(
        _checkpoint_completed,
        _resume_completed
    )

    completed = min(
        completed,
        total_scenes
    )

    # Rebuild clip list from actual files.
    clip_files = []

    for _sid in range(1, completed + 1):

        _clip = os.path.join(
            BASE_DIR,
            f"clip_{_sid}.mp4"
        )

        if valid_file(_clip):
            clip_files.append(_clip)

    state["last_completed_scene"] = completed
    state["clips"] = clip_files

    save_state(state)

    print(
        f"[🛡️ RESUME] Verified clips: "
        f"{len(clip_files)}/{total_scenes}"
    )

    print(
        f"[🛡️ RESUME] Reconciled checkpoint: "
        f"{completed}/{total_scenes}"
    )


    completed = int(
        state.get("last_completed_scene", 0) or 0
    )

    saved_clips = state.get("clips", [])

    if not isinstance(saved_clips, list):
        saved_clips = []

    # Remove duplicate paths while preserving order.
    clip_files = list(dict.fromkeys(saved_clips))

    total_scenes = len(scenes)
    total_chars = max(
        1,
        sum(len(s["text"]) for s in scenes)
    )

    MAX_SCENE_RETRIES = 5
    RETRY_BASE_DELAY = 3

    print("\n==========================================")
    print(" RESUMABLE SMART CINEMATIC MOTION ENGINE")
    print(f" TOTAL SCENES: {total_scenes}")
    print(f" LAST COMPLETED: {completed}")
    print("==========================================\n")


    for scene in scenes:

        scene_id = int(scene["id"])

        img_name = os.path.join(
            BASE_DIR,
            f"scene_{scene_id}.png"
        )

        clip_name = os.path.join(
            BASE_DIR,
            f"clip_{scene_id}.mp4"
        )

        # -------------------------------------------------
        # ALREADY COMPLETED
        # -------------------------------------------------

        if scene_id <= completed:

            if clip_name not in clip_files:

                if valid_file(clip_name):
                    clip_files.append(clip_name)

                    state["clips"] = list(
                        dict.fromkeys(clip_files)
                    )

                    save_state(state)

            print(
                f"[⏭️] Scene {scene_id}: "
                f"already completed — SKIP"
            )

            continue

        # -------------------------------------------------
        # EXISTING VALID CLIP
        # -------------------------------------------------

        if valid_file(clip_name):

            print(
                f"[♻️] Scene {scene_id}: "
                f"valid existing clip found — REUSING"
            )

            if clip_name not in clip_files:
                clip_files.append(clip_name)

            checkpoint(
                scene_id,
                clip_files
            )

            if valid_file(img_name):
                try:
                    os.remove(img_name)
                except Exception:
                    pass

            completed = scene_id
            continue

        # -------------------------------------------------
        # CALCULATE SCENE DURATION
        # -------------------------------------------------

        scene_duration = max(
            1.0,
            (
                len(scene["text"])
                / total_chars
            ) * total_audio_duration
        )

        frames = max(
            25,
            int(scene_duration * 25)
        )

        motion_type = choose_motion(
            scene["text"],
            scene_id
        )

        transition_type = choose_transition(
            scene["text"],
            scene_id
        )

        story_effect = choose_story_effect(
            scene["text"],
            scene_id
        )

        print("\n------------------------------------------")
        print(
            f"[🎬] STARTING SCENE "
            f"{scene_id}/{total_scenes}"
        )
        print(
            f"[🎥] MOTION={motion_type.upper()} | "
            f"TRANSITION={transition_type.upper()}"
        )
        print("------------------------------------------")

        # -------------------------------------------------
        # RETRY ENTIRE SCENE
        # -------------------------------------------------

        scene_success = False

        for attempt in range(
            1,
            MAX_SCENE_RETRIES + 1
        ):

            t_start = time.time()

            print(
                f"[🔁] Scene {scene_id} "
                f"attempt {attempt}/{MAX_SCENE_RETRIES}"
            )

            try:

                # -----------------------------------------
                # CLEAN PARTIAL OUTPUT
                # -----------------------------------------

                for partial in (
                    img_name,
                    clip_name
                ):
                    if os.path.exists(partial):
                        try:
                            if (
                                partial == clip_name
                                and valid_file(partial)
                            ):
                                continue

                            os.remove(partial)

                        except Exception:
                            pass

                # -----------------------------------------
                # IMAGE GENERATION
                # -----------------------------------------

                fetch_scene_image(
                    scene["prompt"],
                    img_name
                )

                if not valid_file(
                    img_name,
                    1000
                ):
                    raise Exception(
                        f"Scene image missing/invalid: "
                        f"{img_name}"
                    )

                # -----------------------------------------
                # CINEMATIC EFFECTS
                # -----------------------------------------

                if story_effect == "impact":

                    cinematic_effects = (
                        "eq=contrast=1.09:"
                        "brightness=0.0:"
                        "saturation=1.03,"
                        "unsharp=5:5:0.65:5:5:0,"
                        "vignette=PI/4:eval=frame"
                    )

                elif story_effect == "suspense":

                    cinematic_effects = (
                        "eq=contrast=1.075:"
                        "brightness=-0.012:"
                        "saturation=0.92,"
                        "unsharp=5:5:0.50:5:5:0,"
                        "vignette=PI/3:eval=frame"
                    )

                elif story_effect == "psychological":

                    cinematic_effects = (
                        "eq=contrast=1.06:"
                        "brightness=-0.004:"
                        "saturation=0.98,"
                        "unsharp=5:5:0.58:5:5:0,"
                        "vignette=PI/4.5:eval=frame"
                    )

                elif story_effect == "quiet":

                    cinematic_effects = (
                        "eq=contrast=1.035:"
                        "brightness=0.003:"
                        "saturation=1.0,"
                        "unsharp=5:5:0.45:5:5:0,"
                        "vignette=PI/6:eval=frame"
                    )

                else:

                    cinematic_effects = (
                        "eq=contrast=1.045:"
                        "brightness=0.002:"
                        "saturation=1.045,"
                        "unsharp=5:5:0.55:5:5:0,"
                        "vignette=PI/5:eval=frame"
                    )

                # -----------------------------------------
                # MOTION
                # -----------------------------------------

                progress = f"(on/{frames})"

                if motion_type == "push":

                    motion = (
                        f"zoompan="
                        f"z='1.0+0.075*"
                        f"(3*{progress}^2-2*{progress}^3)':"
                        f"x='iw/2-(iw/zoom/2)':"
                        f"y='ih/2-(ih/zoom/2)':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "pull":

                    motion = (
                        f"zoompan="
                        f"z='1.075-0.075*"
                        f"(3*{progress}^2-2*{progress}^3)':"
                        f"x='iw/2-(iw/zoom/2)':"
                        f"y='ih/2-(ih/zoom/2)':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "drift":

                    motion = (
                        f"zoompan="
                        f"z='1.055':"
                        f"x='(iw-iw/zoom)*"
                        f"(0.08+0.84*"
                        f"(3*{progress}^2-2*{progress}^3))':"
                        f"y='(ih-ih/zoom)*"
                        f"(0.5+0.06*sin({progress}*PI))':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "focus":

                    motion = (
                        f"zoompan="
                        f"z='1.0+0.065*"
                        f"(3*{progress}^2-2*{progress}^3)':"
                        f"x='(iw-iw/zoom)*"
                        f"(0.5+0.08*sin({progress}*PI))':"
                        f"y='(ih-ih/zoom)*0.5':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "creep":

                    motion = (
                        f"zoompan="
                        f"z='1.0+0.04*{progress}+"
                        f"0.006*sin({progress}*PI*2)':"
                        f"x='(iw-iw/zoom)*"
                        f"(0.5+0.035*sin({progress}*PI*2))':"
                        f"y='(ih-ih/zoom)*"
                        f"(0.5+0.02*sin({progress}*PI))':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "reveal":

                    motion = (
                        f"zoompan="
                        f"z='1.045':"
                        f"x='(iw-iw/zoom)*"
                        f"(1-(3*{progress}^2-2*{progress}^3))':"
                        f"y='(ih-ih/zoom)*"
                        f"(0.25+0.5*{progress})':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "diagonal":

                    motion = (
                        f"zoompan="
                        f"z='1.055+0.015*sin({progress}*PI)':"
                        f"x='(iw-iw/zoom)*"
                        f"(0.08+0.84*{progress})':"
                        f"y='(ih-ih/zoom)*"
                        f"(0.85-0.70*{progress})':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "rise":

                    motion = (
                        f"zoompan="
                        f"z='1.0+0.055*"
                        f"(3*{progress}^2-2*{progress}^3)':"
                        f"x='iw/2-(iw/zoom/2)':"
                        f"y='(ih-ih/zoom)*"
                        f"(0.85-0.70*{progress})':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "descend":

                    motion = (
                        f"zoompan="
                        f"z='1.055-0.025*sin({progress}*PI)':"
                        f"x='iw/2-(iw/zoom/2)':"
                        f"y='(ih-ih/zoom)*"
                        f"(0.15+0.70*{progress})':"
                        f"d=1:s=1280x720:fps=25"
                    )

                elif motion_type == "punch":

                    motion = (
                        f"zoompan="
                        f"z='1.0+0.09*"
                        f"pow(sin({progress}*PI),2)':"
                        f"x='iw/2-(iw/zoom/2)':"
                        f"y='ih/2-(ih/zoom/2)':"
                        f"d=1:s=1280x720:fps=25"
                    )

                else:

                    motion = (
                        f"zoompan="
                        f"z='1.0+0.045*"
                        f"(3*{progress}^2-2*{progress}^3)':"
                        f"x='iw/2-(iw/zoom/2)':"
                        f"y='ih/2-(ih/zoom/2)':"
                        f"d=1:s=1280x720:fps=25"
                    )

                filter_chain = (
                    "scale=1280:720:"
                    "force_original_aspect_ratio=increase,"
                    "crop=1280:720,"
                    + cinematic_effects
                    + ","
                    + motion
                )

                # -----------------------------------------
                # ATOMIC CLIP GENERATION
                # -----------------------------------------

                temp_clip = (
                    clip_name[:-4]
                    + f".attempt{attempt}.tmp.mp4"
                )

                if os.path.exists(temp_clip):
                    os.remove(temp_clip)

                command = (
                    f'ffmpeg -y '
                    f'-loop 1 '
                    f'-i "{img_name}" '
                    f'-vf "{filter_chain}" '
                    f'-frames:v {frames} '
                    f'-an '
                    f'-c:v libx264 '
                    f'-preset ultrafast '
                    f'-pix_fmt yuv420p '
                    f'-movflags +faststart '
                    f'"{temp_clip}"'
                )

                run_cmd(command)

                # -----------------------------------------
                # VALIDATE CLIP
                # -----------------------------------------

                if not valid_file(
                    temp_clip,
                    1000
                ):
                    raise Exception(
                        f"Generated clip invalid: "
                        f"{temp_clip}"
                    )

                # FFprobe validation.
                probe = (
                    f'ffprobe -v error '
                    f'-select_streams v:0 '
                    f'-show_entries stream=codec_name,duration '
                    f'-of default=noprint_wrappers=1 '
                    f'"{temp_clip}"'
                )

                probe_output = run_cmd(
                    probe
                )

                if not probe_output:
                    raise Exception(
                        "FFprobe could not validate clip"
                    )

                # -----------------------------------------
                # ATOMIC SUCCESS
                # -----------------------------------------

                os.replace(
                    temp_clip,
                    clip_name
                )

                if not valid_file(
                    clip_name,
                    1000
                ):
                    raise Exception(
                        f"Final clip invalid after replace: "
                        f"{clip_name}"
                    )

                if clip_name not in clip_files:
                    clip_files.append(
                        clip_name
                    )

                # MOST IMPORTANT:
                # SAVE BEFORE DOING ANYTHING ELSE.
                checkpoint(
                    scene_id,
                    clip_files
                )

                completed = scene_id
                scene_success = True

                # Image is no longer needed.
                if os.path.exists(img_name):
                    try:
                        os.remove(img_name)
                    except Exception:
                        pass

                elapsed = (
                    time.time()
                    - t_start
                )

                print(
                    f"[✓] Scene {scene_id}/"
                    f"{total_scenes} COMPLETE | "
                    f"{scene_duration:.2f}s | "
                    f"{elapsed:.1f}s"
                )

                break

            except Exception as e:

                print(
                    f"\n[⚠️] Scene {scene_id} "
                    f"attempt {attempt} FAILED:"
                )
                print(
                    f"    {e}"
                )

                # Remove only partial attempt output.
                temp_clip = (
                    clip_name[:-4]
                    + f".attempt{attempt}.tmp.mp4"
                )

                for partial in (
                    temp_clip,
                ):
                    if os.path.exists(partial):
                        try:
                            os.remove(partial)
                        except Exception:
                            pass

                if attempt < MAX_SCENE_RETRIES:

                    delay = (
                        RETRY_BASE_DELAY
                        * (2 ** (attempt - 1))
                    )

                    print(
                        f"[⏳] Retrying scene "
                        f"{scene_id} in "
                        f"{delay}s..."
                    )

                    time.sleep(delay)

                else:

                    print(
                        f"\n[🛑] Scene {scene_id} "
                        f"failed after "
                        f"{MAX_SCENE_RETRIES} attempts."
                    )

                    print(
                        "[💾] Previous checkpoints "
                        "are preserved."
                    )

                    raise

        if not scene_success:
            raise Exception(
                f"Scene {scene_id} did not complete"
            )

    # -------------------------------------------------
    # FINAL CHECK
    # -------------------------------------------------

    missing = []

    for scene in scenes:

        sid = int(scene["id"])

        expected = os.path.join(
            BASE_DIR,
            f"clip_{sid}.mp4"
        )

        if not valid_file(
            expected,
            1000
        ):
            missing.append(sid)

    if missing:

        raise Exception(
            "[X] Missing final scene clips: "
            + ", ".join(
                map(str, missing)
            )
        )

    print(
        "\n[🔥] ALL SCENES COMPLETE"
    )

    print(
        f"[✓] {total_scenes} scenes ready"
    )

    return [
        os.path.join(
            BASE_DIR,
            f"clip_{int(scene['id'])}.mp4"
        )
        for scene in scenes
    ]

def choose_transition(scene_text, scene_id):
    """Choose a lightweight transition from the narration context."""
    t = scene_text.lower()

    if any(k in t for k in (
        "suddenly", "shock", "shocking", "impact",
        "realize", "revealed", "discover", "truth"
    )):
        return "impact"

    if any(k in t for k in (
        "fear", "afraid", "terrifying", "terror",
        "danger", "threat", "dark", "secret",
        "uneasy", "creepy"
    )):
        return "dark"

    if any(k in t for k in (
        "memory", "remember", "forget", "forgot",
        "brain", "confused", "psychological",
        "gaslight", "manipulator", "manipulate"
    )):
        return "memory"

    if any(k in t for k in (
        "before", "after", "change", "different",
        "transition", "shift", "then"
    )):
        return "dissolve"

    return "clean"


def build_transition_filter(transition_type, duration=0.35):
    """
    Returns a lightweight transition strategy.
    Actual concatenation remains FFmpeg based.
    """
    d = max(0.15, min(float(duration), 0.8))

    if transition_type == "impact":
        return f"fade=t=out:st=0:d={d}"

    if transition_type == "dark":
        return f"fade=t=out:st=0:d={d}:color=black"

    if transition_type == "memory":
        return f"fade=t=out:st=0:d={d}"

    if transition_type == "dissolve":
        return f"fade=t=out:st=0:d={d}"

    return f"fade=t=out:st=0:d={d}"


def build_highlighted_ass():
    """
    Premium word-synchronized subtitles.

    Design:
      - Stable 4-6 word caption blocks.
      - Exact Edge-TTS WordBoundary timing.
      - White normal words.
      - Yellow active word.
      - Caption stays visible while highlight moves.
      - Higher cinematic placement.
      - No subtitle flicker.
    """

    timings_file = os.path.join(BASE_DIR, "word_timings.json")
    ass_file = os.path.join(BASE_DIR, "highlighted_captions.ass")

    if not os.path.exists(timings_file):
        raise Exception("[X] word_timings.json not found")

    with open(timings_file, "r", encoding="utf-8") as f:
        words = json.load(f)

    if not words:
        raise Exception("[X] No word timings available")

    def ass_time(seconds):
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        sec = seconds % 60
        return f"{h}:{m:02d}:{sec:05.2f}"

    def esc(text):
        return (
            str(text)
            .replace("\\", r"\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
        )

    # ---------------------------------------------------------
    # CAPTION GROUPING
    # ---------------------------------------------------------
    # Keep captions stable instead of creating one full line
    # for every individual word.
    groups = []

    current = []
    current_chars = 0

    for item in words:
        word = str(item.get("word", "")).strip()

        if not word:
            continue

        # New block after 5 words or approximately 34 characters.
        # Never split extremely short blocks unnecessarily.
        projected = current_chars + len(word) + (1 if current else 0)

        if current and (
            len(current) >= 5
            or projected > 34
        ):
            groups.append(current)
            current = []
            current_chars = 0

        current.append(item)
        current_chars += len(word) + (1 if len(current) > 1 else 0)

    if current:
        groups.append(current)

    # ---------------------------------------------------------
    # ASS HEADER
    # ---------------------------------------------------------

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1280",
        "PlayResY: 720",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",

        # White normal text.
        # Yellow active word.
        # Higher placement: MarginV 145.
        "Style: Premium,Montserrat SemiBold,40,"
        "&H00FFFFFF,&H00FFFFFF,&H00141414,&H90000000,"
        "1,0,0,0,100,100,0.2,0,1,2.5,1.2,2,70,70,145,1",

        "Style: Active,Montserrat ExtraBold,40,"
        "&H0000D7FF,&H0000D7FF,&H00141414,&H90000000,"
        "1,0,0,0,100,100,0.2,0,1,2.7,1.3,2,70,70,145,1",

        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text"
    ]

    # ---------------------------------------------------------
    # WORD-SYNCHRONIZED STABLE BLOCKS
    # ---------------------------------------------------------

    for group in groups:

        if not group:
            continue

        group_start = float(group[0]["start"])

        # Keep block visible until the next block begins.
        # This prevents gaps/flicker between individual word events.
        group_end = float(group[-1]["end"])

        # Small natural tail so the caption doesn't disappear
        # immediately after the final spoken word.
        group_end += 0.06

        for index, active in enumerate(group):

            active_word = str(active["word"]).strip()
            active_start = float(active["start"])
            active_end = float(active["end"])

            # Keep highlight exactly aligned with speech.
            start_time = active_start
            end_time = active_end

            before = []
            after = []

            active_seen = False

            for item in group:
                word = esc(item["word"])

                if item is active and not active_seen:
                    active_seen = True
                    continue

                if not active_seen:
                    before.append(word)
                else:
                    after.append(word)

            text_parts = []

            if before:
                text_parts.append(" ".join(before))

            # Active word = yellow.
            text_parts.append(
                r"{\rActive}" + esc(active_word) + r"{\rPremium}"
            )

            if after:
                text_parts.append(" ".join(after))

            text = " ".join(text_parts)

            lines.append(
                "Dialogue: 0,"
                + ass_time(start_time)
                + ","
                + ass_time(end_time)
                + ",Premium,,0,0,145,,"
                + text
            )

    with open(ass_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(
        f"[✓] Premium stable highlighted ASS created: {ass_file}"
    )
    print(
        f"[✓] Word-synced events: {len(words)} | "
        f"Caption blocks: {len(groups)}"
    )
    print(
        "[✓] White base + yellow active word"
    )
    print(
        "[✓] Higher cinematic subtitle position"
    )

    return ass_file




def get_jamendo_bgm(keyword=None):
    """
    ROBUST JAMENDO BGM ENGINE

    Priority:
      1. Dark cinematic piano
      2. Slow ambient / atmospheric
      3. Psychological documentary
      4. Broad piano / cinematic fallback

    Features:
      - Multiple search strategies
      - API retry with exponential backoff
      - Candidate scoring
      - Hard rejection of drums/beats/EDM/etc.
      - Atomic download
      - Final MP3 validation
      - Never leaves a broken bgm_track.mp3
    """

    import os
    import json
    import random
    import time
    import urllib.parse
    import urllib.request

    print("\n[🎵] ROBUST JAMENDO BGM ENGINE")

    client_id = os.environ.get(
        "JAMENDO_CLIENT_ID",
        "c94b6491"
    )

    if not client_id:
        raise Exception("[X] JAMENDO_CLIENT_ID missing")

    bgm_file = os.path.join(
        BASE_DIR,
        "bgm_track.mp3"
    )

    temp_file = bgm_file + ".download"

    # -------------------------------------------------
    # FIXED MUSICAL DNA
    # -------------------------------------------------

    primary_keyword = (
        keyword
        or
        "dark cinematic piano slowed ambient psychological suspense"
    )

    searches = [
        primary_keyword,

        "dark cinematic piano ambient suspense",

        "slow piano cinematic atmospheric instrumental",

        "dark piano ambient documentary soundtrack",

        "cinematic piano ambient instrumental"
    ]

    # -------------------------------------------------
    # HARD NEGATIVE FILTERS
    # -------------------------------------------------

    banned = {
        "drum",
        "drums",
        "drumming",
        "percussion",
        "trap",
        "hip hop",
        "hip-hop",
        "rap",
        "rock",
        "metal",
        "punk",
        "edm",
        "techno",
        "house",
        "dance",
        "dubstep",
        "beat",
        "beats",
        "groove",
        "funk",
        "hardstyle",
        "dj",
        "bass drum",
        "electro",
        "electronic",
        "disco",
        "reggaeton",
        "reggae"
    }

    preferred = {
        "piano": 45,
        "cinematic": 32,
        "ambient": 30,
        "atmospheric": 25,
        "suspense": 25,
        "dark": 24,
        "psychological": 22,
        "documentary": 18,
        "soundtrack": 18,
        "minimal": 16,
        "slow": 15,
        "calm": 8,
        "emotional": 8,
        "instrumental": 15
    }

    # -------------------------------------------------
    # API REQUEST
    # -------------------------------------------------

    def request_candidates(search_term):

        params = {
            "client_id": client_id,
            "format": "json",

            "limit": "80",
            "offset": "0",

            "search": search_term,

            "fuzzytags":
                "piano cinematic ambient soundtrack "
                "suspense atmospheric instrumental",

            "vocalinstrumental":
                "instrumental",

            "speed":
                "verylow low",

            "durationbetween":
                "30_600",

            "probackground":
                "true",

            "audioformat":
                "mp32",

            "audiodlformat":
                "mp32",

            "include":
                "licenses musicinfo",

            "order":
                "relevance"
        }

        url = (
            "https://api.jamendo.com/v3.0/tracks/?"
            +
            urllib.parse.urlencode(params)
        )

        last_error = None

        for attempt in range(1, 4):

            try:

                print(
                    f"[🌐] API attempt "
                    f"{attempt}/3"
                )

                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent":
                        "AI_VIDEO_OS/1.0"
                    }
                )

                with urllib.request.urlopen(
                    req,
                    timeout=30
                ) as response:

                    raw = response.read()

                payload = json.loads(
                    raw.decode("utf-8")
                )

                results = payload.get(
                    "results",
                    []
                )

                return results

            except Exception as e:

                last_error = e

                print(
                    f"[!] Jamendo request failed: "
                    f"{e}"
                )

                if attempt < 3:

                    wait = 2 ** attempt

                    print(
                        f"[⏳] Retry in {wait}s..."
                    )

                    time.sleep(wait)

        print(
            f"[!] API failed after retries: "
            f"{last_error}"
        )

        return []

    # -------------------------------------------------
    # CANDIDATE SCORING
    # -------------------------------------------------

    def score_track(track):

        title = str(
            track.get("name", "")
        )

        artist = str(
            track.get("artist_name", "")
        )

        album = str(
            track.get("album_name", "")
        )

        musicinfo = track.get(
            "musicinfo",
            {}
        )

        haystack = (
            title
            + " "
            + artist
            + " "
            + album
            + " "
            + str(musicinfo)
        ).lower()

        # ---------------------------------------------
        # DOWNLOAD URL
        # ---------------------------------------------

        audio_url = (
            track.get("audiodownload")
            or
            track.get("audio")
        )

        if not audio_url:
            return None

        allowed = track.get(
            "audiodownload_allowed"
        )

        if allowed is False:
            return None

        # ---------------------------------------------
        # HARD NEGATIVE FILTER
        # ---------------------------------------------

        for bad in banned:

            if bad in haystack:

                return None

        score = 0

        # ---------------------------------------------
        # POSITIVE SCORING
        # ---------------------------------------------

        for word, points in preferred.items():

            if word in haystack:
                score += points

        # Strong piano preference.

        if "piano" in haystack:
            score += 60

        # Strong cinematic + ambient.

        if (
            "cinematic" in haystack
            and
            "ambient" in haystack
        ):
            score += 40

        # Psychological atmosphere.

        if (
            "dark" in haystack
            and
            "piano" in haystack
        ):
            score += 30

        # Reject vocals.

        if any(
            x in haystack
            for x in (
                "vocal",
                "vocals",
                "singer",
                "lyrics",
                "rap",
                "voice"
            )
        ):
            score -= 100

        # Prefer long tracks.

        try:
            duration = float(
                track.get(
                    "duration",
                    0
                )
            )
        except Exception:
            duration = 0

        if duration >= 90:
            score += 10

        if duration >= 180:
            score += 10

        return score

    # -------------------------------------------------
    # SEARCH ENGINE
    # -------------------------------------------------

    all_candidates = {}

    for search_index, search_term in enumerate(
        searches,
        start=1
    ):

        print(
            "\n"
            f"[🔎] Search "
            f"{search_index}/{len(searches)}: "
            f"{search_term}"
        )

        results = request_candidates(
            search_term
        )

        print(
            f"[🔎] Candidates received: "
            f"{len(results)}"
        )

        if not results:
            print(
                "[!] No candidates. "
                "Trying next search..."
            )
            continue

        for track in results:

            track_id = str(
                track.get(
                    "id",
                    ""
                )
            )

            if not track_id:
                continue

            score = score_track(
                track
            )

            if score is None:
                continue

            old = all_candidates.get(
                track_id
            )

            if old is None or score > old[0]:

                all_candidates[
                    track_id
                ] = (
                    score,
                    track
                )

        print(
            f"[✓] Suitable accumulated: "
            f"{len(all_candidates)}"
        )

        # Once we have enough good tracks,
        # don't hammer the API unnecessarily.

        if len(all_candidates) >= 15:

            break

    # -------------------------------------------------
    # FINAL CANDIDATE CHECK
    # -------------------------------------------------

    if not all_candidates:

        raise Exception(
            "[X] Jamendo returned no suitable "
            "BGM after all retry/search strategies"
        )

    candidates = list(
        all_candidates.values()
    )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    # Keep top candidates but randomize
    # selection so every video differs.

    top_pool = candidates[
        :min(12, len(candidates))
    ]

    score, track = random.choice(
        top_pool
    )

    audio_url = (
        track.get("audiodownload")
        or
        track.get("audio")
    )

    title = track.get(
        "name",
        "Unknown"
    )

    artist = track.get(
        "artist_name",
        "Unknown"
    )

    duration = track.get(
        "duration",
        "?"
    )

    print(
        f"\n[✓] Selected BGM: {title}"
    )

    print(
        f"[✓] Artist: {artist}"
    )

    print(
        f"[✓] Score: {score}"
    )

    print(
        f"[✓] Duration: {duration}s"
    )

    # -------------------------------------------------
    # DOWNLOAD WITH RETRIES
    # -------------------------------------------------

    if os.path.exists(temp_file):

        try:
            os.remove(temp_file)
        except Exception:
            pass

    download_error = None

    for attempt in range(1, 4):

        try:

            print(
                f"[⬇️] Download attempt "
                f"{attempt}/3"
            )

            req = urllib.request.Request(
                audio_url,
                headers={
                    "User-Agent":
                    "AI_VIDEO_OS/1.0"
                }
            )

            with urllib.request.urlopen(
                req,
                timeout=90
            ) as response:

                with open(
                    temp_file,
                    "wb"
                ) as out:

                    while True:

                        chunk = response.read(
                            256 * 1024
                        )

                        if not chunk:
                            break

                        out.write(chunk)

            if (
                not os.path.exists(
                    temp_file
                )
                or
                os.path.getsize(
                    temp_file
                ) < 10000
            ):

                raise Exception(
                    "Downloaded file is too small"
                )

            # -----------------------------------------
            # VALIDATE AUDIO
            # -----------------------------------------

            probe = (
                f'ffprobe -v error '
                f'-show_entries format=duration '
                f'-of default=noprint_wrappers=1:nokey=1 '
                f'"{temp_file}"'
            )

            output = run_cmd(
                probe
            )

            try:
                downloaded_duration = float(
                    output
                )
            except Exception:
                downloaded_duration = 0

            if downloaded_duration <= 0:

                raise Exception(
                    "FFprobe reported invalid duration"
                )

            print(
                f"[✓] Download validated: "
                f"{downloaded_duration:.2f}s"
            )

            # -----------------------------------------
            # ATOMIC REPLACEMENT
            # -----------------------------------------

            os.replace(
                temp_file,
                bgm_file
            )

            # -----------------------------------------
            # FINAL VALIDATION
            # -----------------------------------------

            if (
                not os.path.exists(
                    bgm_file
                )
                or
                os.path.getsize(
                    bgm_file
                ) < 10000
            ):

                raise Exception(
                    "Final BGM file invalid"
                )

            print(
                f"[🎵] BGM READY: "
                f"{bgm_file}"
            )

            return bgm_file

        except Exception as e:

            download_error = e

            print(
                f"[!] BGM download attempt "
                f"{attempt} failed: {e}"
            )

            if os.path.exists(
                temp_file
            ):

                try:
                    os.remove(
                        temp_file
                    )
                except Exception:
                    pass

            if attempt < 3:

                wait = 2 ** attempt

                print(
                    f"[⏳] Download retry "
                    f"in {wait}s..."
                )

                time.sleep(wait)

    raise Exception(
        "[X] BGM download failed after "
        f"3 attempts: {download_error}"
    )

def finalize_flash_video(clip_files, audio_file, scenes=None):
    print("\n[🎬] FINAL CINEMATIC MASTER ASSEMBLY")
    print("[1/4] Motion + transitions")
    print("[2/4] Highlighted subtitles")
    print("[3/4] Voice + low BGM mix")
    print("[4/4] Gallery export")

    if not clip_files:
        raise Exception("[X] No clips available for final assembly")

    bgm_file = os.path.join(BASE_DIR, "bgm_track.mp3")
    ass_file = os.path.join(BASE_DIR, "highlighted_captions.ass")

    if not os.path.exists(audio_file):
        raise Exception(f"[X] Voice file missing: {audio_file}")

    # -------------------------------------------------
    # PERMANENT AUTO BGM GENERATION
    # -------------------------------------------------

    print("\n[🎵] AUTO BGM ENGINE")

    # Never depend on a leftover BGM from a previous run.
    if os.path.exists(bgm_file):
        try:
            os.remove(bgm_file)
            print("[🗑️] Previous BGM removed")
        except Exception as e:
            raise Exception(
                f"[X] Could not remove previous BGM: {e}"
            )

    try:
        generated_bgm = get_jamendo_bgm(
            "dark cinematic piano slowed ambient psychological suspense"
        )

        # get_jamendo_bgm() normally creates bgm_track.mp3.
        # Keep this fallback in case it returns another valid path.
        if not os.path.exists(bgm_file):
            if generated_bgm and os.path.exists(str(generated_bgm)):
                if os.path.abspath(str(generated_bgm)) != os.path.abspath(bgm_file):
                    import shutil
                    shutil.copy2(
                        str(generated_bgm),
                        bgm_file
                    )

    except Exception as e:
        raise Exception(
            f"[X] Automatic Jamendo BGM generation failed: {e}"
        )

    # Mandatory validation before continuing.
    if (
        not os.path.exists(bgm_file)
        or os.path.getsize(bgm_file) < 10000
    ):
        raise Exception(
            f"[X] BGM generation completed but valid bgm_track.mp3 "
            f"was not created: {bgm_file}"
        )

    # Verify that FFmpeg can actually decode the downloaded music.
    try:
        bgm_probe = run_cmd(
            f'ffprobe -v error '
            f'-show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 '
            f'"{bgm_file}"'
        )

        bgm_duration_check = float(str(bgm_probe).strip())

    except Exception as e:
        raise Exception(
            f"[X] Downloaded BGM cannot be decoded: {e}"
        )

    if bgm_duration_check <= 0:
        raise Exception(
            "[X] Downloaded BGM has invalid duration"
        )

    print(
        f"[✓] Fresh BGM ready | "
        f"{bgm_duration_check:.2f}s | "
        f"{os.path.getsize(bgm_file) / 1024 / 1024:.2f} MB"
    )

    # -------------------------------------------------
    # 1. READ CLIP DURATIONS
    # -------------------------------------------------

    durations = []

    for clip in clip_files:
        cmd = (
            f'ffprobe -v error '
            f'-show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 '
            f'"{clip}"'
        )

        try:
            duration = float(run_cmd(cmd))
        except Exception:
            duration = 1.0

        durations.append(max(0.5, duration))

    # -------------------------------------------------
    # 2. BATCHED CINEMATIC XFADE ASSEMBLY
    # -------------------------------------------------
    #
    # IMPORTANT:
    # A single 77-clip xfade filter graph is extremely
    # memory/CPU heavy on Android/Termux.
    #
    # We therefore assemble small batches first and then
    # merge the resulting batch masters.
    #
    # This keeps the largest filter graph small and makes
    # the final assembly much more reliable.
    # -------------------------------------------------

    silent_video = os.path.join(
        BASE_DIR,
        "video_motion_master.mp4"
    )

    BATCH_SIZE = 8

    def _probe_duration(path):
        cmd = (
            f'ffprobe -v error '
            f'-show_entries format=duration '
            f'-of default=noprint_wrappers=1:nokey=1 '
            f'"{path}"'
        )

        try:
            return max(0.5, float(run_cmd(cmd)))
        except Exception:
            return 1.0

    def _build_xfade_group(
        group_clips,
        group_durations,
        group_start_index,
        output_path,
        group_name
    ):
        if not group_clips:
            raise Exception(
                f"[X] Empty assembly group: {group_name}"
            )

        if len(group_clips) == 1:
            run_cmd(
                f'ffmpeg -y '
                f'-i "{group_clips[0]}" '
                f'-an '
                f'-c:v libx264 '
                f'-preset ultrafast '
                f'-threads 2 '
                f'-pix_fmt yuv420p '
                f'-movflags +faststart '
                f'"{output_path}"'
            )

            if not os.path.exists(output_path):
                raise Exception(
                    f"[X] Group output missing: {output_path}"
                )

            return _probe_duration(output_path)

        inputs = ""

        for clip in group_clips:
            inputs += f'-i "{clip}" '

        transitions = []

        accumulated = group_durations[0]
        previous = "[0:v]"

        for local_i in range(1, len(group_clips)):

            previous_duration = group_durations[local_i - 1]

            transition_duration = min(
                0.35,
                max(0.12, previous_duration / 3)
            )

            offset = max(
                0.0,
                accumulated - transition_duration
            )

            global_scene_id = (
                group_start_index +
                local_i +
                1
            )

            scene_text = ""

            if scenes and (
                global_scene_id - 1
            ) < len(scenes):
                scene_text = scenes[
                    global_scene_id - 1
                ].get("text", "")

            transition_type = choose_transition(
                scene_text,
                global_scene_id
            )

            if transition_type == "impact":
                xfade_name = "fade"

                transition_duration = min(
                    transition_duration,
                    0.22
                )

            elif transition_type == "dark":
                xfade_name = "fadeblack"

            elif transition_type == "memory":
                xfade_name = "fade"

            elif transition_type == "dissolve":
                xfade_name = "dissolve"

            else:
                xfade_name = "fade"

            out_label = f"[x{local_i}]"

            transitions.append(
                f"{previous}[{local_i}:v]"
                f"xfade="
                f"transition={xfade_name}:"
                f"duration={transition_duration:.3f}:"
                f"offset={offset:.3f}"
                f"{out_label}"
            )

            print(
                f"[🎞️] {group_name} transition "
                f"{local_i}: "
                f"SCENE={global_scene_id} | "
                f"{transition_type.upper()} | "
                f"{xfade_name} | "
                f"{transition_duration:.2f}s"
            )

            previous = out_label

            accumulated += (
                group_durations[local_i] -
                transition_duration
            )

        filter_complex = ";".join(transitions)

        command = (
            f'ffmpeg -y '
            f'{inputs}'
            f'-filter_complex "{filter_complex}" '
            f'-map "{previous}" '
            f'-an '
            f'-c:v libx264 '
            f'-preset ultrafast '
            f'-threads 2 '
            f'-pix_fmt yuv420p '
            f'-movflags +faststart '
            f'"{output_path}"'
        )

        run_cmd(command)

        if (
            not os.path.exists(output_path)
            or os.path.getsize(output_path) < 10000
        ):
            raise Exception(
                f"[X] Invalid group output: "
                f"{output_path}"
            )

        return _probe_duration(output_path)

    # -------------------------------------------------
    # BUILD SMALL BATCHES
    # -------------------------------------------------

    batch_files = []
    batch_durations = []

    total_clips = len(clip_files)

    print(
        f"\n[🧩] BATCHED XFADE ENGINE ACTIVE"
    )
    print(
        f"[🧩] Total clips: {total_clips}"
    )
    print(
        f"[🧩] Batch size: {BATCH_SIZE}"
    )

    for batch_start in range(
        0,
        total_clips,
        BATCH_SIZE
    ):

        batch_end = min(
            batch_start + BATCH_SIZE,
            total_clips
        )

        batch_number = (
            batch_start // BATCH_SIZE
        ) + 1

        batch_path = os.path.join(
            BASE_DIR,
            f"motion_batch_{batch_number:03d}.mp4"
        )

        group_clips = clip_files[
            batch_start:batch_end
        ]

        group_durations = durations[
            batch_start:batch_end
        ]

        # -------------------------------------------------
        # RESUME BATCH IF VALID
        # -------------------------------------------------

        if (
            os.path.exists(batch_path)
            and os.path.getsize(batch_path) >= 10000
        ):
            print(
                f"[♻️] Reusing batch "
                f"{batch_number}: "
                f"scenes {batch_start + 1}-"
                f"{batch_end}"
            )

            batch_duration = _probe_duration(
                batch_path
            )

        else:
            print(
                f"\n[🧩] Building batch "
                f"{batch_number}: "
                f"scenes {batch_start + 1}-"
                f"{batch_end}"
            )

            if os.path.exists(batch_path):
                try:
                    os.remove(batch_path)
                except Exception:
                    pass

            batch_duration = _build_xfade_group(
                group_clips,
                group_durations,
                batch_start,
                batch_path,
                f"BATCH {batch_number}"
            )

        batch_files.append(batch_path)
        batch_durations.append(batch_duration)

        print(
            f"[✓] Batch {batch_number} ready | "
            f"{batch_duration:.2f}s"
        )

    # -------------------------------------------------
    # FINAL BATCH MERGE
    # -------------------------------------------------

    if len(batch_files) == 1:

        import shutil

        shutil.copy2(
            batch_files[0],
            silent_video
        )

    else:

        print(
            f"\n[🎬] Merging "
            f"{len(batch_files)} batch masters..."
        )

        # Final merge is deliberately small:
        # 77 scenes -> ~10 batch files -> ~9 xfade operations.

        final_batch_start = 0

        final_duration = _build_xfade_group(
            batch_files,
            batch_durations,
            final_batch_start,
            silent_video,
            "MASTER"
        )

        print(
            f"[✓] Motion master ready | "
            f"{final_duration:.2f}s"
        )

    if (
        not os.path.exists(silent_video)
        or os.path.getsize(silent_video) < 10000
    ):
        raise Exception(
            "[X] Motion master video was not created"
        )


    # -------------------------------------------------
    # 3. BUILD HIGHLIGHTED SUBTITLES
    # -------------------------------------------------

    if not os.path.exists(ass_file):
        print("[🎨] Highlighted ASS not found. Building it now...")
        ass_file = build_highlighted_ass()

    if not os.path.exists(ass_file):
        raise Exception("[X] Highlighted subtitle file missing")

    print("[📝] Burning highlighted word-synced subtitles...")

    subtitle_video = os.path.join(
        BASE_DIR,
        "video_subtitled_master.mp4"
    )

    # ASS path is inside a shell-quoted ffmpeg filter.
    subtitle_filter = (
        f"subtitles='{ass_file}':"
        f"fontsdir='/system/fonts'"
    )

    run_cmd(
        f'ffmpeg -y '
        f'-i "{silent_video}" '
        f'-vf "{subtitle_filter}" '
        f'-an '
        f'-c:v libx264 '
        f'-preset ultrafast '
        f'-pix_fmt yuv420p '
        f'-movflags +faststart '
        f'"{subtitle_video}"'
    )

    if not os.path.exists(subtitle_video):
        raise Exception(
            "[X] Subtitle-burned video was not created"
        )

    print("[✓] Highlighted subtitles permanently burned into video")

    # -------------------------------------------------

    # 4. VOICE + VERY LOW CINEMATIC BGM
    # -------------------------------------------------

    print("[🎚️] Building cinematic BGM bed...")
    print("[🎹] Target: slowed piano / atmospheric")
    print("[🔉] BGM level: VERY LOW")

    mixed_audio = os.path.join(
        BASE_DIR,
        "final_mixed_audio.mp3"
    )

    looped_bgm = os.path.join(
        BASE_DIR,
        "bgm_exact_duration.mp3"
    )

    voice_duration_cmd = (
        f'ffprobe -v error '
        f'-show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 '
        f'"{audio_file}"'
    )

    try:
        voice_duration = float(
            run_cmd(voice_duration_cmd)
        )
    except Exception as e:
        raise Exception(
            f"[X] Could not read voice duration: {e}"
        )

    if voice_duration <= 0:
        raise Exception(
            "[X] Invalid voice duration"
        )

    print(
        f"[🎙️] Voice duration: "
        f"{voice_duration:.2f}s"
    )

    # -------------------------------------------------
    # NORMALIZE + LOOP BGM
    # -------------------------------------------------

    run_cmd(
        f'ffmpeg -y '
        f'-stream_loop -1 '
        f'-i "{bgm_file}" '
        f'-t {voice_duration:.3f} '
        f'-af "'
        f'aresample=44100,'
        f'loudnorm=I=-24:TP=-2:LRA=7,'
        f'volume=0.55,'
        f'atrim=duration={voice_duration:.3f}'
        f'" '
        f'-ar 44100 '
        f'-ac 2 '
        f'-c:a libmp3lame '
        f'-b:a 192k '
        f'"{looped_bgm}"'
    )

    if (
        not os.path.exists(looped_bgm)
        or os.path.getsize(looped_bgm) < 1000
    ):
        raise Exception(
            "[X] BGM bed was not created"
        )

    # -------------------------------------------------
    # VOICE FOREGROUND + BGM BACKGROUND
    # -------------------------------------------------

    print(
        "[🎵] Mixing voice foreground + "
        "very-low atmospheric BGM..."
    )

    mix_filter = (
        "[0:a]"
        "aresample=44100,"
        "aformat="
        "sample_fmts=fltp:"
        "sample_rates=44100:"
        "channel_layouts=stereo,"
        "volume=1.0"
        "[voice];"

        "[1:a]"
        "aresample=44100,"
        "aformat="
        "sample_fmts=fltp:"
        "sample_rates=44100:"
        "channel_layouts=stereo,"
        "volume=0.055"
        "[bgm];"

        "[voice][bgm]"
        "amix="
        "inputs=2:"
        "duration=first:"
        "dropout_transition=0:"
        "normalize=0,"
        "alimiter=limit=0.95"
        "[aout]"
    )

    run_cmd(
        f'ffmpeg -y '
        f'-i "{audio_file}" '
        f'-i "{looped_bgm}" '
        f'-filter_complex "{mix_filter}" '
        f'-map "[aout]" '
        f'-t {voice_duration:.3f} '
        f'-ar 44100 '
        f'-ac 2 '
        f'-c:a libmp3lame '
        f'-b:a 192k '
        f'"{mixed_audio}"'
    )

    if (
        not os.path.exists(mixed_audio)
        or os.path.getsize(mixed_audio) < 1000
    ):
        raise Exception(
            "[X] Voice+BGM mix was not created"
        )

    mixed_duration_cmd = (
        f'ffprobe -v error '
        f'-show_entries format=duration '
        f'-of default=noprint_wrappers=1:nokey=1 '
        f'"{mixed_audio}"'
    )

    try:
        mixed_duration = float(
            run_cmd(mixed_duration_cmd)
        )
    except Exception as e:
        raise Exception(
            f"[X] Could not verify mixed audio: {e}"
        )

    if mixed_duration <= 0:
        raise Exception(
            "[X] Mixed audio duration invalid"
        )

    print(
        f"[✓] Final audio duration: "
        f"{mixed_duration:.2f}s"
    )

    print(
        "[✓] Voice: foreground"
    )

    print(
        "[✓] BGM: 5.5% atmospheric background"
    )

    # 5. FINAL MASTER
    # -------------------------------------------------

    final_temp = os.path.join(
        BASE_DIR,
        "final_output.mp4"
    )

    print("[🎬] Combining subtitled video + final audio...")

    run_cmd(
        f'ffmpeg -y '
        f'-i "{subtitle_video}" '
        f'-i "{mixed_audio}" '
        f'-map 0:v:0 '
        f'-map 1:a:0 '
        f'-c:v copy '
        f'-c:a aac '
        f'-b:a 192k '
        f'-shortest '
        f'-movflags +faststart '
        f'"{final_temp}"'
    )

    if not os.path.exists(final_temp):
        raise Exception("[X] Final video was not created")

    if os.path.getsize(final_temp) < 10000:
        raise Exception("[X] Final video appears invalid")

    # -------------------------------------------------
    # 6. GALLERY EXPORT
    # -------------------------------------------------

    os.makedirs(
        GALLERY_DIR,
        exist_ok=True
    )

    target_path = (
        f"{GALLERY_DIR}/"
        f"viral_master_{int(time.time())}.mp4"
    )

    run_cmd(
        f'cp "{final_temp}" "{target_path}"'
    )

    # -------------------------------------------------
    # CLEANUP
    # -------------------------------------------------

    for temp in (
        silent_video,
        subtitle_video,
        mixed_audio,
        looped_bgm
    ):
        if os.path.exists(temp):
            os.remove(temp)

    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

    for clip in clip_files:
        if os.path.exists(clip):
            os.remove(clip)

    print("\n[🔥 SUCCESS] FINAL MASTER READY")
    print("[🎵] BGM: audible cinematic background bed")
    print(f"[🎙️] Voice: foreground")
    print(f"[📝] Subtitles: word-synced highlighted ASS")
    print(f"[🎬] Gallery: {target_path}")



def main():
    try:
        scenes = load_and_split_script()
        audio_file, audio_duration = asyncio.run(generate_perfect_voice(scenes))
        clip_files = process_scenes_flash(scenes, audio_duration)
        finalize_flash_video(clip_files, audio_file, scenes)
    except Exception as e:
        print(f"\n[CRITICAL ERROR]: {e}")

if __name__ == "__main__":
    main()
