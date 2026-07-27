#!/usr/bin/env python3
import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_FILE = ROOT / "data" / "nyt_puzzles.json"
BASE_URL = "https://raw.githubusercontent.com/iturki/nyt-sudoku-archive/main"

def parse_sdk(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    meta = {}
    board_str = ""
    for line in lines:
        if line.startswith("#CNYT Puzzle Id:"):
            try:
                meta["puzzle_id"] = int(line.split(":")[-1].strip())
            except Exception:
                pass
        elif line.startswith("#B"):
            meta["date"] = line[2:].strip()
        elif line.startswith("#L"):
            meta["difficulty"] = line[2:].strip()
        elif not line.startswith("#") and len(line) == 9:
            board_str += line

    if len(board_str) == 81:
        puzzle = [int(ch) if ch.isdigit() else 0 for ch in board_str]
        meta["puzzle"] = puzzle
        return meta
    return None

def solve_sudoku(puzzle):
    board = list(puzzle)
    def is_valid(b, r, c, val):
        for i in range(9):
            if b[r * 9 + i] == val or b[i * 9 + c] == val:
                return False
        br, bc = (r // 3) * 3, (c // 3) * 3
        for dr in range(3):
            for dc in range(3):
                if b[(br + dr) * 9 + (bc + dc)] == val:
                    return False
        return True

    def backtrack(b):
        for i in range(81):
            if b[i] == 0:
                r, c = i // 9, i % 9
                for val in range(1, 10):
                    if is_valid(b, r, c, val):
                        b[i] = val
                        if backtrack(b):
                            return True
                        b[i] = 0
                return False
        return True

    b_copy = list(board)
    if backtrack(b_copy):
        return b_copy
    return None

def fetch_file_list(diff):
    url = f"https://api.github.com/repos/iturki/nyt-sudoku-archive/contents/nyt-sudoku-{diff}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            items = json.loads(resp.read().decode("utf-8"))
            return [item["name"] for item in items if item["name"].endswith(".sdk")]
    except Exception as e:
        print(f"Error listing {diff}: {e}")
        return []

def process_file(diff, fname):
    match = re.search(r"\d{4}-\d{2}-\d{2}", fname)
    if not match:
        return None
    date_str = match.group(0)
    file_url = f"{BASE_URL}/nyt-sudoku-{diff}/{fname}"
    try:
        req = urllib.request.Request(file_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
        parsed = parse_sdk(text)
        if parsed and parsed.get("puzzle"):
            solution = solve_sudoku(parsed["puzzle"])
            if solution:
                key = f"{date_str}_{diff.lower()}"
                return key, {
                    "date": date_str,
                    "difficulty": diff.capitalize(),
                    "puzzle_id": parsed.get("puzzle_id"),
                    "puzzle": parsed["puzzle"],
                    "solution": solution
                }
    except Exception:
        pass
    return None

def main():
    archive = {}
    print("Building official NYT Sudoku Archive dataset in parallel...")

    tasks = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        for diff in ["easy", "medium", "hard"]:
            filenames = fetch_file_list(diff)
            for fname in filenames:
                tasks.append(executor.submit(process_file, diff, fname))

        for future in as_completed(tasks):
            res = future.result()
            if res:
                key, val = res
                archive[key] = val

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(archive, indent=2), encoding="utf-8")
    print(f"SUCCESS: Archived {len(archive)} official NYT Sudoku puzzles into {OUT_FILE}")

if __name__ == "__main__":
    main()
