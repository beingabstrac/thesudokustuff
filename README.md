# thesudokustuff

Free MVP pipeline for creating vertical NYT-style Sudoku reel videos for `@thesudokustuff`.

Default archive puzzle starts at **November 21, 2019** (`Sudoku #1`).

## Reel Layout Specification

- **Header:** `Sudoku #1   •   November 21, 2019`
- **Sub-Header:** `EASY`, `MEDIUM`, or `HARD`
- **Center:** Animated 9x9 Sudoku grid with active highlights & keypad
- **Footer:** `@thesudokustuff`

## Run Locally

```bash
python3 -m pip install -r requirements.txt
./scripts/render.sh
```

Outputs:
- `outputs/thesudokustuff_mvp.mp4`
- `outputs/thesudokustuff_storyboard.json`

Render specific date or offset:

```bash
SUDOKU_DATE=2019-11-21 ./scripts/render.sh
```

Advance progress (old-to-new):

```bash
./scripts/render.sh
python3 scripts/advance_progress.py
```

## Automation

GitHub Actions (`.github/workflows/post-to-buffer.yml`) renders reels and tops up the Buffer queue automatically.

Required Repository Secrets:
- `BUFFER_API_KEY`
- `BUFFER_INSTAGRAM_CHANNEL_ID`
- `CLOUDINARY_URL`
