#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRESS_FILE = ROOT / "data" / "progress.json"
STORY_FILE = ROOT / "outputs" / "thesudokustuff_storyboard.json"

def main():
    progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8")) if PROGRESS_FILE.exists() else {}
    story = json.loads(STORY_FILE.read_text(encoding="utf-8")) if STORY_FILE.exists() else {}
    
    current_offset = int(story.get("offset", progress.get("next_offset", 0)))
    current_diff = story.get("difficulty", progress.get("difficulty", "easy")).lower()
    
    # Rotate Easy -> Medium -> Hard -> Next Day Easy
    if current_diff == "easy":
        next_diff = "medium"
        next_offset = current_offset
    elif current_diff == "medium":
        next_diff = "hard"
        next_offset = current_offset
    else:  # hard -> easy of next date!
        next_diff = "easy"
        next_offset = current_offset + 1
        
    progress["next_offset"] = next_offset
    progress["difficulty"] = next_diff
    progress["last_sudoku_id"] = story.get("sudoku_id")
    progress["last_date"] = story.get("date")
    
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    print(f"Advanced Progress -> Date Offset: {next_offset}, Difficulty: {next_diff.capitalize()}")
    print(json.dumps(progress, indent=2))

if __name__ == "__main__":
    main()
