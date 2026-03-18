# bar-chart-race

Animated bar chart race MP4 video generator for NBA stats data.

Reads Excel, CSV, or public Google Sheets and outputs social-media-ready videos using Pillow rendering and ffmpeg encoding.

## Presets

| Preset   | Resolution  | Aspect | Use case                      |
|----------|-------------|--------|-------------------------------|
| `reels`  | 1080x1920   | 9:16   | Instagram Reels / TikTok / Shorts |
| `youtube`| 1920x1080   | 16:9   | YouTube landscape             |
| `square` | 1080x1080   | 1:1    | Twitter / Instagram feed      |

## Quick start

```bash
pip install -e ".[dev]"

# From CSV
python -m bar_race -i data.csv -o race.mp4 --preset reels --title "Scoring Leaders"

# From YAML config
python -m bar_race --config config.yaml

# From Google Sheets
python -m bar_race --gsheet-url "https://docs.google.com/spreadsheets/d/.../edit" -o race.mp4
```

## Data formats

The tool auto-detects two input formats:

**Long/tidy** — columns named `date`, `player`, `value` (and optionally `team`):

| date       | player  | value | team |
|------------|---------|-------|------|
| 2024-01-01 | LeBron  | 30    | LAL  |
| 2024-01-01 | Curry   | 28    | GSW  |

**Wide** — first column is the date, remaining columns are player names:

| date       | LeBron | Curry |
|------------|--------|-------|
| 2024-01-01 | 30     | 28    |
| 2024-02-01 | 32     | 35    |

## Requirements

- Python 3.10+
- ffmpeg on PATH

## Tests

```bash
pytest
```
