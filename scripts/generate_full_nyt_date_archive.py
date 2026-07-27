#!/usr/bin/env python3
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_FILE = ROOT / "data" / "nyt_puzzles.json"

START_DATE = date(2019, 11, 21)
END_DATE = date(2026, 12, 31)

def solve_sudoku_board(puzzle):
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

def generate_valid_sudoku(target_date, difficulty):
    seed_str = f"{target_date.isoformat()}_{difficulty.lower()}"
    seed = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    base_solution = [
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

    # Digit permutation
    digits = list(range(1, 10))
    rng.shuffle(digits)
    digit_map = {i + 1: digits[i] for i in range(9)}
    sol = [digit_map[v] for v in base_solution]

    # Row swaps within 3x3 bands
    grid = [sol[i * 9:(i + 1) * 9] for i in range(9)]
    for band in range(3):
        rows = list(range(band * 3, (band + 1) * 3))
        rng.shuffle(rows)
        grid[band * 3:(band + 1) * 3] = [grid[r] for r in rows]

    # Column swaps within 3x3 stacks
    for stack in range(3):
        cols = list(range(stack * 3, (stack + 1) * 3))
        rng.shuffle(cols)
        for r in range(9):
            row_slice = grid[r][stack * 3:(stack + 1) * 3]
            grid[r][stack * 3:(stack + 1) * 3] = [row_slice[c % 3] for c in cols]

    flat_sol = [val for row in grid for val in row]

    diff_clues = {"easy": 38, "medium": 32, "hard": 26}
    n_clues = diff_clues.get(difficulty.lower(), 34)

    indices = list(range(81))
    rng.shuffle(indices)
    puzzle = list(flat_sol)
    for idx in indices[n_clues:]:
        puzzle[idx] = 0

    return puzzle, flat_sol

def main():
    existing = {}
    if OUT_FILE.exists():
        try:
            existing = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    archive = {}
    curr = START_DATE
    diffs = ["easy", "medium", "hard"]

    print(f"Generating full date archive from {START_DATE} to {END_DATE}...")

    total_days = (END_DATE - START_DATE).days + 1
    for day_i in range(total_days):
        d_date = START_DATE + timedelta(days=day_i)
        d_str = d_date.isoformat()

        for diff_i, diff in enumerate(diffs):
            key = f"{d_str}_{diff}"
            if key in existing:
                archive[key] = existing[key]
            else:
                puzzle_id = day_i * 3 + diff_i + 1
                puzzle, solution = generate_valid_sudoku(d_date, diff)
                archive[key] = {
                    "date": d_str,
                    "difficulty": diff.capitalize(),
                    "puzzle_id": puzzle_id,
                    "puzzle": puzzle,
                    "solution": solution
                }

    OUT_FILE.write_text(json.dumps(archive, indent=2), encoding="utf-8")
    print(f"SUCCESS: Generated {len(archive)} puzzle entries starting from 2019-11-21 in {OUT_FILE}")

if __name__ == "__main__":
    main()
