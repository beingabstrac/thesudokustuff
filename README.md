# thesudokustuff

Automated daily NYT Sudoku reel renderer and Instagram publisher.

Default puzzle starts at November 21, 2019 (`Sudoku #1`).

Run:

```bash
python3 -m pip install -r requirements.txt
./scripts/render.sh
```

Output:

```text
outputs/thesudokustuff_mvp.mp4
```

Render a specific date:

```bash
SUDOKU_DATE=2019-11-21 ./scripts/render.sh
```

Render old-to-new:

```bash
./scripts/render.sh
python3 scripts/advance_progress.py
```
