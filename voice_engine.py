import os, re, json, asyncio, subprocess, edge_tts, time

VOICE = "en-US-AndrewMultilingualNeural"
RATE = "-2%"
PITCH = "-5Hz"
VOLUME = "+0%"

BASE_DIR = os.getcwd()
RAW_AUDIO = os.path.join(BASE_DIR, "voice_raw.mp3")
MASTER_AUDIO = os.path.join(BASE_DIR, "voice_master.mp3")
TIMINGS_FILE = os.path.join(BASE_DIR, "word_timings.json")
SCRIPT_FILE = os.path.join(BASE_DIR, "scripts.txt")

def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise Exception(f"[X] {r.stderr[-300:]}")
    return r.stdout.strip()

def _probe_duration(path):
    out = _run(f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"')
    return float(out)

async def _tts_chunk(text, out_path):
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME, pitch=PITCH, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                offset = chunk.get("offset", 0)
                duration = chunk.get("duration", 0)
                w_text = chunk.get("text", "").strip()
                if w_text:
                    st = offset / 10_000_000.0
                    en = (offset + duration) / 10_000_000.0
                    words.append({"word": w_text, "start": st, "end": en})
    return words

def generate_voice(script_text=None):
    if script_text is None:
        if not os.path.exists(SCRIPT_FILE):
            raise Exception("[X] scripts.txt not found")
        with open(SCRIPT_FILE, encoding="utf-8") as f:
            script_text = f.read().strip()
            
    print("[VOICE] Starting Chunked TTS Generation...")
    
    # Script ko sentences me todo
    sentences = re.split(r'(?<=[.!?])\s+', script_text)
    chunks = []
    current_chunk = ""
    
    # Har chunk ko 400 characters (approx 3-4 lines) ka banao
    for sentence in sentences:
        if len(current_chunk) + len(sentence) < 400:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    print(f"[VOICE] Split script into {len(chunks)} chunks.")
    
    all_words = []
    concat_list = []
    current_time_offset = 0.0
    
    for i, chunk in enumerate(chunks):
        if not chunk.strip(): continue
        print(f"  -> Processing chunk {i+1}/{len(chunks)}...")
        
        chunk_audio = os.path.join(BASE_DIR, f"_chunk_{i}.mp3")
        
        for attempt in range(3):
            try:
                words = asyncio.run(_tts_chunk(chunk, chunk_audio))
                if not words: raise Exception("No words generated")
                break
            except Exception as e:
                print(f"     [!] Chunk {i+1} retry {attempt+1}: {e}")
                time.sleep(3)
        else:
            raise Exception(f"Chunk {i+1} failed after 3 attempts")
            
        # Duration nikalo
        duration = _probe_duration(chunk_audio)
        
        # Word timings ko shift karo current offset ke hisaab se
        for w in words:
            w["start"] += current_time_offset
            w["end"] += current_time_offset
            all_words.append(w)
            
        current_time_offset += duration
        concat_list.append(chunk_audio)
        
        # Chhota sa break taaki server par load na pade
        time.sleep(1)
        
    print("[VOICE] Merging all chunks...")
    concat_file = os.path.join(BASE_DIR, "_concat.txt")
    with open(concat_file, "w") as f:
        for c in concat_list:
            f.write(f"file '{c}'\n")
            
    # FFmpeg se saari audios ko jodo (bina re-encode kiye)
    _run(f'ffmpeg -y -f concat -safe 0 -i "{concat_file}" -c copy "{MASTER_AUDIO}"')
    
    # Studio processing (EQ, Compressor, Loudnorm)
    print("[VOICE] Applying final studio processing...")
    filters = (
        "highpass=f=80,lowpass=f=16000,"
        "equalizer=f=2500:t=q:w=1.5:g=0.8,"
        "equalizer=f=180:t=q:w=1.5:g=1.0,"
        "equalizer=f=7000:t=q:w=2.0:g=-2.0,"
        "afftdn=nr=5:nf=-42,"
        "acompressor=threshold=-24dB:ratio=1.8:attack=30:release=250:makeup=1.0,"
        "aecho=0.85:0.9:20|40:0.05|0.025,"
        "volume=0.85,loudnorm=I=-24:TP=-4:LRA=9"
    )
    processed_audio = os.path.join(BASE_DIR, "voice_processed.mp3")
    _run(f'ffmpeg -y -i "{MASTER_AUDIO}" -af "{filters}" -ar 44100 -ac 2 -c:a libmp3lame -b:a 192k "{processed_audio}"')
    os.replace(processed_audio, MASTER_AUDIO)
    
    # Cleanup
    for c in concat_list:
        try: os.remove(c)
        except: pass
    try: os.remove(concat_file)
    except: pass
    
    # Save Timings
    with open(TIMINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_words, f, indent=2, ensure_ascii=False)
        
    duration = _probe_duration(MASTER_AUDIO)
    print(f"[VOICE] Complete! Duration: {duration:.2f}s")
    return MASTER_AUDIO, duration, all_words

if __name__ == "__main__":
    generate_voice()
