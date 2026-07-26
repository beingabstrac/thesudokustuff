#!/usr/bin/env python3
import asyncio
import html
import json
import math
import os
import re
import shutil
import sys
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import wave
import struct
from array import array
from datetime import datetime, timedelta, date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEPS_VENV = ROOT / ".deps" / "venv"
if DEPS_VENV.exists():
    for site_pkg in DEPS_VENV.glob("lib/python*/site-packages"):
        if str(site_pkg) not in sys.path:
            sys.path.insert(0, str(site_pkg))

OUT = ROOT / "outputs"
VIDEO_OUT = OUT / "thesudokustuff_mvp.mp4"
STORY_OUT = OUT / "thesudokustuff_storyboard.json"
DATA_DIR = ROOT / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"
PUZZLES_FILE = DATA_DIR / "puzzles.json"
FONTS_DIR = ROOT / "assets" / "fonts"

W, H = 1080, 1920
FPS = 30
START_DATE = date(2019, 11, 21)

# Colors (Exact NYT Sudoku Light Theme with Soft Gray Meta & Realistic Markers)
COLOR_BG = (255, 255, 255)                  # Pure white #FFFFFF
COLOR_GRID_INNER = (185, 192, 200)          # Inner line #B9C0C8
COLOR_GRID_OUTER = (0, 0, 0)                # Heavy black outer border #000000
COLOR_TEXT_ALL = (0, 0, 0)                  # Solid black digits #000000
COLOR_CELL_BG = (255, 255, 255)             # White empty cell #FFFFFF
COLOR_CELL_GIVEN = (227, 229, 232)          # Light gray given cell #E3E5E8
COLOR_CELL_CROSSHAIR_EMPTY = (252, 243, 212) # Warm cream empty crosshair #FCF3D4
COLOR_CELL_CROSSHAIR_GIVEN = (205, 196, 178) # Medium tan given crosshair #CDC4B2
COLOR_CELL_MATCH = (235, 140, 0)            # NYT Vivid Orange matching digit #EB8C00
COLOR_CELL_ERROR = (239, 68, 68)            # Vibrant Red Error Flash #EF4444
COLOR_TEXT_ERROR = (255, 255, 255)         # White text on error cell
COLOR_PENCIL = (100, 116, 139)               # Slate pencil mark gray #64748B
COLOR_MUTED = (100, 116, 139)               # Soft muted gray #64748B

# Exact Wordle Voice Pool & Dynamic Prosody
EDGE_VOICES = [
    "en-US-AvaNeural",
    "en-US-AndrewNeural",
    "en-US-EmmaNeural",
    "en-US-BrianNeural",
]

EDGE_BEAT_PROSODY = {
    "opener": ("+0%", "+0Hz"),
    "calm": ("+0%", "+0Hz"),
    "focused": ("+3%", "+1Hz"),
    "uncertain": ("-4%", "-1Hz"),
    "triumphant": ("+2%", "+2Hz"),
}

def ensure_inter_fonts():
    """Ensure Inter font files exist in assets/fonts/, auto-downloading from CDN if missing."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    bold_path = FONTS_DIR / "Inter-Bold.ttf"
    reg_path = FONTS_DIR / "Inter-Regular.ttf"
    if bold_path.exists() and reg_path.exists() and bold_path.stat().st_size > 0 and reg_path.stat().st_size > 0:
        return
    try:
        css_url = "https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap"
        req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            css = resp.read().decode("utf-8")
        ttf_urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", css)
        if len(ttf_urls) >= 2:
            urllib.request.urlretrieve(ttf_urls[0], reg_path)
            urllib.request.urlretrieve(ttf_urls[1], bold_path)
    except Exception:
        pass

ensure_inter_fonts()

def font(size, bold=False):
    """Load Inter font across all platforms (macOS, GitHub Actions, Linux)."""
    target = FONTS_DIR / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf")
    if target.exists():
        try:
            return ImageFont.truetype(str(target), size)
        except Exception:
            pass
    system_candidates = [
        "/System/Library/Fonts/SFProText-Bold.ttf" if bold else "/System/Library/Fonts/SFProText-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for cand in system_candidates:
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                pass
    return ImageFont.load_default()

def load_progress():
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"next_offset": 0, "difficulty": "easy"}

def puzzle_date():
    raw = os.getenv("SUDOKU_DATE")
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            pass
    prog = load_progress()
    offset = int(os.getenv("SUDOKU_OFFSET", str(prog.get("next_offset", 0))))
    return START_DATE + timedelta(days=offset)

def pretty_date(d):
    return d.strftime("%B %d, %Y").replace(" 0", " ")

def fetch_nyt_sudoku(target_date, difficulty="easy"):
    """Fetch daily NYT Sudoku puzzle data from NYT or local fallback."""
    diff_key = difficulty.lower()
    diff_idx = {"easy": 0, "medium": 1, "hard": 2}.get(diff_key, 0)
    offset = (target_date - START_DATE).days
    puzzle_id = offset * 3 + diff_idx + 1
    date_str = pretty_date(target_date)

    url = f"https://www.nytimes.com/puzzles/sudoku/{diff_key}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            html_content = resp.read().decode("utf-8")
        match = re.search(r'window\.gameData\s*=\s*(\{.*?\})\s*</script>', html_content)
        if match:
            data = json.loads(match.group(1))
            if diff_key in data:
                item = data[diff_key]
                p_data = item.get("puzzle_data", {})
                return {
                    "puzzle_id": puzzle_id,
                    "difficulty": difficulty.capitalize(),
                    "displayDate": date_str,
                    "puzzle": p_data.get("puzzle", []),
                    "solution": p_data.get("solution", [])
                }
    except Exception:
        pass

    # Check local puzzles JSON
    if PUZZLES_FILE.exists():
        try:
            p_json = json.loads(PUZZLES_FILE.read_text(encoding="utf-8"))
            puzzles = p_json.get("puzzles", [])
            for p in puzzles:
                if p.get("difficulty", "").lower() == diff_key:
                    res = dict(p)
                    res["puzzle_id"] = puzzle_id
                    res["displayDate"] = date_str
                    return res
        except Exception:
            pass

    # Default Verified NYT Sudoku Fallback
    return {
        "puzzle_id": puzzle_id,
        "difficulty": difficulty.capitalize(),
        "displayDate": date_str,
        "puzzle": [
            9, 0, 5, 0, 1, 0, 8, 0, 7,
            0, 2, 0, 7, 9, 0, 1, 3, 0,
            3, 0, 0, 6, 2, 0, 0, 0, 0,
            0, 4, 1, 0, 0, 0, 7, 0, 8,
            0, 0, 3, 0, 0, 4, 2, 0, 5,
            8, 0, 0, 0, 5, 9, 0, 0, 3,
            2, 0, 0, 9, 0, 0, 0, 8, 0,
            1, 3, 4, 0, 0, 6, 0, 7, 0,
            0, 8, 0, 2, 0, 1, 5, 6, 0
        ],
        "solution": [
            9, 6, 5, 4, 1, 3, 8, 2, 7,
            4, 2, 8, 7, 9, 5, 1, 3, 6,
            3, 1, 7, 6, 2, 8, 4, 5, 9,
            5, 4, 1, 3, 6, 2, 7, 9, 8,
            6, 9, 3, 8, 7, 4, 2, 1, 5,
            8, 7, 2, 1, 5, 9, 6, 4, 3,
            2, 5, 6, 9, 4, 7, 3, 8, 1,
            1, 3, 4, 5, 8, 6, 9, 7, 2,
            7, 8, 9, 2, 3, 1, 5, 6, 4
        ]
    }

def get_candidates(board, idx):
    """Return list of valid candidates for empty cell idx."""
    if board[idx] != 0:
        return []
    r, c = idx // 9, idx % 9
    used = set()
    for i in range(9):
        used.add(board[r * 9 + i])
        used.add(board[i * 9 + c])
    box_r, box_c = (r // 3) * 3, (c // 3) * 3
    for br in range(3):
        for bc in range(3):
            used.add(board[(box_r + br) * 9 + (box_c + bc)])
    return [d for d in range(1, 10) if d not in used]

def solve_steps(puzzle, solution):
    """Generate smooth natural left-to-right top-to-bottom solving sequence for clean eye comfort."""
    empty_indices = [i for i, val in enumerate(puzzle) if val == 0]
    empty_indices.sort()  # Pure left-to-right, top-to-bottom reading order (0..80)
    
    steps = []
    for i_count, idx in enumerate(empty_indices):
        r, c = idx // 9, idx % 9
        val = solution[idx]
        box = (r // 3) * 3 + (c // 3) + 1
        
        # Wordle-styled contextual human speech
        if i_count == 0:
            speech = f"Starting in box {box}, {val}."
        elif i_count == 14:
            speech = f"Let me try a 5 in box {box}."
        elif i_count == len(empty_indices) - 1:
            speech = f"And the final digit is {val}."
        elif i_count % 6 == 0:
            if (r + c) % 2 == 0:
                speech = f"Row {r + 1} takes {val}."
            else:
                speech = f"Column {c + 1} gets {val}."
        elif i_count % 9 == 0:
            speech = f"Box {box}, placing {val}."
        elif i_count % 13 == 0:
            speech = f"Only a {val} fits here."
        else:
            speech = None
            
        steps.append({
            "index": idx,
            "row": r,
            "col": c,
            "digit": val,
            "speech": speech,
            "is_mistake_step": (i_count == 14)
        })
        
    return steps

def draw_frame(board, givens, active_cell=None, just_placed=None, error_cell=None, pencil_marks=None, puzzle_info=None):
    """Render a 1080x1920 frame with dead-center Sudoku grid, Snyder notes & error states."""
    img = Image.new("RGB", (W, H), COLOR_BG)
    draw = ImageDraw.Draw(img)
    
    f_header = font(38, bold=True)
    f_digit = font(58, bold=True)
    f_pencil = font(22, bold=False)
    f_footer = font(38, bold=True)
    
    # 1. Header Spec: Sudoku #1 Easy   •   November 21, 2019 (Soft Muted Gray #64748B)
    p_id = puzzle_info.get("puzzle_id", 1) if puzzle_info else 1
    d_str = puzzle_info.get("displayDate", "November 21, 2019") if puzzle_info else "November 21, 2019"
    diff_str = puzzle_info.get("difficulty", "Easy").capitalize() if puzzle_info else "Easy"
    header_str = f"Sudoku #{p_id} {diff_str}   •   {d_str}"
    draw.text((W // 2, 360), header_str, font=f_header, fill=COLOR_MUTED, anchor="mm")
    
    # 2. Sudoku Grid (DEAD CENTER: 954x954 at X=63, Y=483)
    cell_s = 106
    grid_size = cell_s * 9
    gx, gy = (W - grid_size) // 2, (H - grid_size) // 2
    
    active_r = active_cell // 9 if active_cell is not None else None
    active_c = active_cell % 9 if active_cell is not None else None
    active_digit = board[active_cell] if (active_cell is not None and board[active_cell] != 0) else None
    
    for r in range(9):
        for c in range(9):
            idx = r * 9 + c
            x1 = gx + c * cell_s
            y1 = gy + r * cell_s
            x2 = x1 + cell_s
            y2 = y1 + cell_s
            
            is_given = givens[idx]
            val = board[idx]
            
            bg_color = COLOR_CELL_GIVEN if is_given else COLOR_CELL_BG
            
            if active_r is not None and active_c is not None:
                if r == active_r or c == active_c or ((r // 3 == active_r // 3) and (c // 3 == active_c // 3)):
                    bg_color = COLOR_CELL_CROSSHAIR_GIVEN if is_given else COLOR_CELL_CROSSHAIR_EMPTY
                    
            if active_digit is not None and val == active_digit:
                bg_color = COLOR_CELL_MATCH
            elif active_cell == idx or just_placed == idx:
                bg_color = COLOR_CELL_MATCH
                
            if error_cell == idx:
                bg_color = COLOR_CELL_ERROR
                
            draw.rectangle([x1, y1, x2, y2], fill=bg_color)
            draw.rectangle([x1, y1, x2, y2], outline=COLOR_GRID_INNER, width=1)
            
            if val != 0:
                text_fill = COLOR_TEXT_ERROR if error_cell == idx else COLOR_TEXT_ALL
                draw.text((x1 + cell_s // 2, y1 + cell_s // 2), str(val), font=f_digit, fill=text_fill, anchor="mm")
            elif pencil_marks and idx in pencil_marks:
                # Draw Snyder Candidate Pencil Notes (3x3 grid inside cell)
                candidates = sorted(list(pencil_marks[idx]))
                for p_val in candidates:
                    pr = (p_val - 1) // 3
                    pc = (p_val - 1) % 3
                    px = x1 + 20 + pc * 33
                    py = y1 + 20 + pr * 33
                    draw.text((px, py), str(p_val), font=f_pencil, fill=COLOR_PENCIL, anchor="mm")
                
    # Heavy 3x3 Outer & Inner Grid Lines
    for i in range(1, 9):
        pos = i * cell_s
        if i % 3 == 0:
            draw.rectangle([gx + pos - 2, gy, gx + pos + 2, gy + grid_size], fill=COLOR_GRID_OUTER)
            draw.rectangle([gx, gy + pos - 2, gx + grid_size, gy + pos + 2], fill=COLOR_GRID_OUTER)
        else:
            draw.rectangle([gx + pos, gy, gx + pos + 1, gy + grid_size], fill=COLOR_GRID_INNER)
            draw.rectangle([gx, gy + pos, gx + grid_size, gy + pos + 1], fill=COLOR_GRID_INNER)
            
    # Exact 4px Uniform Outer Borders on all 4 sides
    b_w = 4
    draw.rectangle([gx - b_w, gy - b_w, gx + grid_size + b_w, gy], fill=COLOR_GRID_OUTER)           # Top
    draw.rectangle([gx - b_w, gy + grid_size, gx + grid_size + b_w, gy + grid_size + b_w], fill=COLOR_GRID_OUTER) # Bottom
    draw.rectangle([gx - b_w, gy - b_w, gx, gy + grid_size + b_w], fill=COLOR_GRID_OUTER)           # Left
    draw.rectangle([gx + grid_size, gy - b_w, gx + grid_size + b_w, gy + grid_size + b_w], fill=COLOR_GRID_OUTER) # Right

    # 3. Bottom Footer: @thesudokustuff (Soft Muted Gray #64748B)
    draw.text((W // 2, 1560), "@thesudokustuff", font=f_footer, fill=COLOR_MUTED, anchor="mm")
    
    return img

async def generate_edge_tts(text, out_path, voice_index=0, beat="calm"):
    voice_name = EDGE_VOICES[voice_index % len(EDGE_VOICES)]
    rate, pitch = EDGE_BEAT_PROSODY.get(beat, ("+0%", "+0Hz"))
    mp3 = out_path.with_suffix(".mp3")
    
    import edge_tts  # pyrefly: ignore [missing-import]
    communicate = edge_tts.Communicate(text, voice_name, rate=rate, pitch=pitch)
    await communicate.save(str(mp3))
    
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3), "-ar", "44100", "-ac", "1", "-acodec", "pcm_s16le", str(out_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    mp3.unlink(missing_ok=True)

def soften_clip(path):
    """Apply micro fade in/out to prevent audio pops."""
    tmp = path.with_suffix(".soft.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(path),
            "-af", "afade=t=in:st=0:d=0.025,areverse,afade=t=in:st=0:d=0.035,areverse",
            "-ar", "44100", "-ac", "1", "-acodec", "pcm_s16le", str(tmp)
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    tmp.replace(path)

def make_voice_clip(text, out_path, voice_index=0, beat="calm"):
    try:
        asyncio.run(generate_edge_tts(text, out_path, voice_index, beat))
        soften_clip(out_path)
        return
    except Exception as exc:
        print(f"Edge TTS error: {exc}")
        
    try:
        subprocess.run(["say", "-o", str(out_path), "--data-format=LEI16@44100", text], check=True)
        soften_clip(out_path)
        return
    except Exception:
        pass
        
    write_silent_wav(out_path, 1.2)

def write_silent_wav(path, duration_sec):
    sample_rate = 44100
    n_samples = int(sample_rate * duration_sec)
    with wave.open(str(path), 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b'\x00\x00' * n_samples)

def write_sfx(path, sfx_type):
    sample_rate = 44100
    if sfx_type == "click":
        duration = 0.04
        n_samples = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n_samples):
            v = int(14000 * math.sin(2 * math.pi * 880 * (i / sample_rate)) * math.exp(-i / (n_samples * 0.2)))
            buf.extend(struct.pack('<h', v))
    elif sfx_type == "error":
        duration = 0.18
        n_samples = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n_samples):
            v = int(16000 * (math.sin(2 * math.pi * 180 * (i / sample_rate)) + math.sin(2 * math.pi * 240 * (i / sample_rate))))
            v = int(v * math.exp(-i / (n_samples * 0.5)))
            buf.extend(struct.pack('<h', v))
    elif sfx_type == "chime":
        duration = 0.4
        n_samples = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n_samples):
            v = int(9000 * (math.sin(2 * math.pi * 523 * (i / sample_rate)) + math.sin(2 * math.pi * 659 * (i / sample_rate))))
            v = int(v * math.exp(-i / (n_samples * 0.4)))
            buf.extend(struct.pack('<h', v))
    else:
        duration = 0.1
        n_samples = int(sample_rate * duration)
        buf = bytearray(n_samples * 2)

    with wave.open(str(path), 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(buf)

def wav_duration(path):
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()

def write_audio_timeline(events, out_path, total_seconds):
    """Mix audio timeline events sample-by-sample with Wordle's exact PCM array algorithm."""
    framerate = 44100
    sampwidth = 2
    total_samples = max(1, int(round((total_seconds + 0.25) * framerate)))
    mix = array("i", [0]) * total_samples

    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for start, clip_path in events:
            start_sample = max(0, int(round(start * framerate)))
            with wave.open(str(clip_path), "rb") as clip:
                frames = array("h")
                frames.frombytes(clip.readframes(clip.getnframes()))
            for i, sample in enumerate(frames):
                pos = start_sample + i
                if pos >= total_samples:
                    break
                mix[pos] += sample
        clipped = array("h", (max(-32768, min(32767, sample)) for sample in mix))
        out.writeframes(clipped.tobytes())

def main():
    print("--- Generating Smooth In-Sequence Sudoku Reel ---")
    OUT.mkdir(parents=True, exist_ok=True)
    
    target_d = puzzle_date()
    prog = load_progress()
    difficulty = os.getenv("DIFFICULTY", prog.get("difficulty", "easy"))
    puzzle_info = fetch_nyt_sudoku(target_d, difficulty)
    offset = (target_d - START_DATE).days
    
    puzzle_id = puzzle_info["puzzle_id"]
    voice_index = puzzle_id % len(EDGE_VOICES)
    print(f"Loaded Puzzle #{puzzle_id} ({puzzle_info['difficulty']} - {puzzle_info['displayDate']}) using voice {EDGE_VOICES[voice_index]}")
    
    puzzle = list(puzzle_info["puzzle"])
    solution = list(puzzle_info["solution"])
    givens = [v != 0 for v in puzzle]
    
    steps = solve_steps(puzzle, solution)
    total_moves = len(steps)
    
    # Initialize Snyder Pencil Marks for initial 2-candidate cells
    pencil_marks = {}
    for idx in range(81):
        if puzzle[idx] == 0:
            cands = get_candidates(puzzle, idx)
            if len(cands) == 2:
                pencil_marks[idx] = set(cands)
    
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        audio_events = []
        
        click_sfx = tmp_dir / "click.wav"
        error_sfx = tmp_dir / "error.wav"
        chime_sfx = tmp_dir / "chime.wav"
        write_sfx(click_sfx, "click")
        write_sfx(error_sfx, "error")
        write_sfx(chime_sfx, "chime")
        
        frame_actions = []
        current_frame = 0
        
        # 1. Intro
        intro_text = "Let's solve today's Sudoku."
        intro_wav = tmp_dir / "intro.wav"
        make_voice_clip(intro_text, intro_wav, voice_index, beat="opener")
        intro_dur = wav_duration(intro_wav)
        intro_frames = max(30, int(round(intro_dur * FPS)))
        
        audio_events.append((0.0, intro_wav))
        for _ in range(intro_frames):
            frame_actions.append({"type": "intro", "cell": None, "just_placed": None, "error": None})
        current_frame += intro_frames
        
        storyboard_segments = [{"type": "intro", "text": intro_text, "duration": intro_frames / FPS}]
        
        # 2. Human Play Moves with Pencil Marks, Eye Scanning & 1 Realistic Correction
        for step_i, st in enumerate(steps):
            cell_idx = st["index"]
            digit = st["digit"]
            speech = st["speech"]
            is_mistake = st.get("is_mistake_step", False)
            
            st_start_frame = current_frame
            
            if is_mistake:
                # ----------------------------------------------------
                # REALISTIC MISTAKE & CORRECTION MOMENT
                # ----------------------------------------------------
                wrong_digit = 5 if digit != 5 else 7
                wrong_speech = f"Let's try a {wrong_digit} in row {st['row'] + 1}."
                
                wav_wrong = tmp_dir / f"step_{step_i}_wrong.wav"
                make_voice_clip(wrong_speech, wav_wrong, voice_index, beat="uncertain")
                w_dur = wav_duration(wav_wrong)
                
                audio_events.append((current_frame / FPS, wav_wrong))
                sel_frames = int(round(max(0.5, w_dur) * FPS))
                for _ in range(sel_frames):
                    frame_actions.append({"type": "select", "cell": cell_idx, "just_placed": None, "error": None})
                current_frame += sel_frames
                
                # Place WRONG digit -> Red Error Flash & Buzz SFX!
                audio_events.append((current_frame / FPS, error_sfx))
                
                # Correction speech: "Wait, that conflicts with column X. Let me fix that."
                fix_text = f"Wait, that conflicts with column {st['col'] + 1}. Let me fix that."
                wav_fix = tmp_dir / f"step_{step_i}_fix.wav"
                make_voice_clip(fix_text, wav_fix, voice_index, beat="calm")
                f_dur = wav_duration(wav_fix)
                
                audio_events.append((current_frame / FPS, wav_fix))
                fix_frames = int(round(max(0.6, f_dur + 0.2) * FPS))
                # KEEP RED BOX & WRONG DIGIT VISIBLE UNTIL VOICEOVER FINISHES!
                for _ in range(fix_frames):
                    frame_actions.append({"type": "error", "cell": cell_idx, "just_placed": None, "error": cell_idx, "override_digit": wrong_digit})
                current_frame += fix_frames
                
                # Place CORRECT digit -> Click SFX & Orange Flash!
                audio_events.append((current_frame / FPS, click_sfx))
                for _ in range(8):
                    frame_actions.append({"type": "flash", "cell": cell_idx, "just_placed": cell_idx, "error": None, "digit": digit})
                current_frame += 8
                
                for _ in range(6):
                    frame_actions.append({"type": "hold", "cell": cell_idx, "just_placed": None, "error": None, "digit": digit})
                current_frame += 6
                
            else:
                # Normal move
                if speech:
                    step_wav = tmp_dir / f"step_{step_i}.wav"
                    make_voice_clip(speech, step_wav, voice_index, beat="focused")
                    v_dur = wav_duration(step_wav)
                    audio_events.append((current_frame / FPS, step_wav))
                    sel_frames = int(round(max(0.5, v_dur) * FPS))
                else:
                    sel_frames = 4
                    
                for _ in range(sel_frames):
                    frame_actions.append({"type": "select", "cell": cell_idx, "just_placed": None, "error": None})
                current_frame += sel_frames
                
                # EXACT PLACEMENT MOMENT
                audio_events.append((current_frame / FPS, click_sfx))
                
                for _ in range(8):
                    frame_actions.append({"type": "flash", "cell": cell_idx, "just_placed": cell_idx, "error": None, "digit": digit})
                current_frame += 8
                
                for _ in range(6):
                    frame_actions.append({"type": "hold", "cell": cell_idx, "just_placed": None, "error": None, "digit": digit})
                current_frame += 6
                
            storyboard_segments.append({
                "type": "move",
                "cell": cell_idx,
                "digit": digit,
                "text": speech,
                "duration": (current_frame - st_start_frame) / FPS
            })
            
        # 3. Outro
        diff_str = puzzle_info.get("difficulty", "Easy").capitalize()
        outro_text = f"And that's today's {diff_str} Sudoku complete! See you tomorrow."
        outro_wav = tmp_dir / "outro.wav"
        make_voice_clip(outro_text, outro_wav, voice_index, beat="triumphant")
        outro_dur = wav_duration(outro_wav)
        outro_frames = max(30, int(round(outro_dur * FPS)))
        
        outro_start_time = current_frame / FPS
        audio_events.append((outro_start_time, outro_wav))
        audio_events.append((outro_start_time, chime_sfx))
        for _ in range(outro_frames):
            frame_actions.append({"type": "outro", "cell": None, "just_placed": None, "error": None})
        current_frame += outro_frames
        
        storyboard_segments.append({"type": "outro", "text": outro_text, "duration": outro_frames / FPS})
        
        total_duration = current_frame / FPS
        
        # 4. Mix Master Audio Track with 44.1kHz Sample-Accurate PCM Timeline Mixer
        master_wav = tmp_dir / "master_mix.wav"
        write_audio_timeline(audio_events, master_wav, total_duration)
        
        # 5. Open FFmpeg Streaming Pipe
        cmd_video = [
            "ffmpeg", "-y",
            "-f", "image2pipe",
            "-vcodec", "png",
            "-framerate", str(FPS),
            "-i", "-",
            "-i", str(master_wav),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            str(VIDEO_OUT)
        ]
        
        ffmpeg_proc = subprocess.Popen(cmd_video, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        def push_frame(image):
            try:
                image.save(ffmpeg_proc.stdin, format="PNG")
            except Exception as e:
                err_out = ffmpeg_proc.stderr.read().decode("utf-8", errors="ignore")
                print(f"FFmpeg Stdin Error: {e}\nFFmpeg Stderr:\n{err_out}")
                raise e

        # 6. Execute Frame Rendering Loop with Dynamic Pencil Notes Removal
        render_board = list(puzzle)
        current_pencil = dict(pencil_marks)
        
        for act in frame_actions:
            cell_idx = act.get("cell")
            just_placed = act.get("just_placed")
            error_cell = act.get("error")
            digit = act.get("digit")
            override_digit = act.get("override_digit")
            
            if override_digit is not None and cell_idx is not None:
                temp_board = list(render_board)
                temp_board[cell_idx] = override_digit
                img = draw_frame(temp_board, givens, active_cell=cell_idx, just_placed=None, error_cell=error_cell, pencil_marks=current_pencil, puzzle_info=puzzle_info)
            else:
                if digit is not None and cell_idx is not None:
                    render_board[cell_idx] = digit
                    current_pencil.pop(cell_idx, None)
                    # Clear this placed digit from all pencil marks in same row/col/box!
                    r_p, c_p = cell_idx // 9, cell_idx % 9
                    box_p = (r_p // 3) * 3 + (c_p // 3)
                    for p_k in list(current_pencil.keys()):
                        r_k, c_k = p_k // 9, p_k % 9
                        box_k = (r_k // 3) * 3 + (c_k // 3)
                        if r_k == r_p or c_k == c_p or box_k == box_p:
                            current_pencil[p_k].discard(digit)
                            if not current_pencil[p_k]:
                                current_pencil.pop(p_k, None)
                    
                img = draw_frame(render_board, givens, active_cell=cell_idx, just_placed=just_placed, error_cell=error_cell, pencil_marks=current_pencil, puzzle_info=puzzle_info)
                
            push_frame(img)
            
        storyboard_data = {
            "sudoku_id": puzzle_info["puzzle_id"],
            "difficulty": puzzle_info["difficulty"],
            "date": target_d.isoformat(),
            "displayDate": puzzle_info["displayDate"],
            "offset": offset,
            "total_duration": total_duration,
            "voice": EDGE_VOICES[voice_index],
            "segments": storyboard_segments
        }
        STORY_OUT.write_text(json.dumps(storyboard_data, indent=2), encoding="utf-8")
        
        ffmpeg_proc.stdin.close()
        ffmpeg_proc.wait()

        print(f"SUCCESS: Generated Smooth In-Sequence Sudoku Reel -> {VIDEO_OUT} ({total_duration:.1f}s)")

if __name__ == "__main__":
    main()
