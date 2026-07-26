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
    progress["next_offset"] = current_offset + 1
    progress["last_sudoku_id"] = story.get("sudoku_id")
    progress["last_date"] = story.get("date")
    progress["difficulty"] = story.get("difficulty", "Easy").lower()
    
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(progress, indent=2))

if __name__ == "__main__":
    main()
