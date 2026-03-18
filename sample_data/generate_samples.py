"""Generate sample NBA cumulative points Excel files for testing."""

import random
from datetime import date, timedelta

import pandas as pd

# ---------------------------------------------------------------------------
# Players and their approximate per-game scoring rates + teams
# ---------------------------------------------------------------------------

PLAYERS = [
    ("Shai Gilgeous-Alexander", "OKC", 33.0),
    ("Luka Doncic",             "DAL", 29.0),
    ("Giannis Antetokounmpo",   "MIL", 30.0),
    ("Donovan Mitchell",        "CLE", 28.0),
    ("Jayson Tatum",            "BOS", 27.5),
    ("Anthony Edwards",         "MIN", 27.0),
    ("Trae Young",              "ATL", 26.0),
    ("Kevin Durant",            "PHX", 26.5),
    ("Karl-Anthony Towns",      "NYK", 25.5),
    ("Jaylen Brown",            "BOS", 24.5),
    ("LeBron James",            "LAL", 25.0),
    ("Nikola Jokic",            "DEN", 26.0),
    ("De'Aaron Fox",            "SAC", 25.0),
    ("Anthony Davis",           "LAL", 24.0),
    ("Devin Booker",            "PHX", 25.5),
]

# ---------------------------------------------------------------------------
# Date grid: ~every 2 days from Oct 22, 2024 → Jan 31, 2025
# ---------------------------------------------------------------------------

start = date(2024, 10, 22)
end = date(2025, 1, 31)

dates: list[date] = []
d = start
while d <= end:
    dates.append(d)
    d += timedelta(days=random.choice([1, 2, 2, 2, 2]))

# Make sure we hit exactly the end date.
if dates[-1] != end:
    dates.append(end)

print(f"Generated {len(dates)} game dates")

# ---------------------------------------------------------------------------
# Build cumulative totals with variance and scripted storylines
# ---------------------------------------------------------------------------

random.seed(42)

# cumulative[player_name] = list of cumulative totals, one per date
cumulative: dict[str, list[float]] = {}

for name, team, avg_ppg in PLAYERS:
    totals: list[float] = []
    running = 0.0
    for i, dt in enumerate(dates):
        # Base points per game with noise.
        pts = avg_ppg + random.gauss(0, 4.5)

        # --- Storyline tweaks to create lead changes ---------------------

        # SGA: slow start first 8 games, then hot streak.
        if name == "Shai Gilgeous-Alexander":
            if i < 8:
                pts -= 5
            elif 15 <= i <= 25:
                pts += 4  # hot streak mid-Nov

        # Luka: strong start, misses ~5 games mid-Dec (injury).
        if name == "Luka Doncic":
            if i < 6:
                pts += 5
            elif 28 <= i <= 33:
                pts = 0  # injury absence

        # Giannis: consistent but big games around Christmas.
        if name == "Giannis Antetokounmpo":
            if 30 <= i <= 38:
                pts += 5

        # Mitchell: hot January.
        if name == "Donovan Mitchell":
            if i >= 40:
                pts += 6

        # Edwards: cold November, heats up December.
        if name == "Anthony Edwards":
            if 5 <= i <= 18:
                pts -= 4
            elif 25 <= i <= 35:
                pts += 3

        # Jokic: gradually ramps up.
        if name == "Nikola Jokic":
            pts += i * 0.08

        # Durant: misses a few games late December.
        if name == "Kevin Durant":
            if 34 <= i <= 37:
                pts = 0

        pts = max(pts, 0)
        running += pts
        totals.append(round(running, 1))

    cumulative[name] = totals

# ---------------------------------------------------------------------------
# Build DataFrames
# ---------------------------------------------------------------------------

# Long format
long_records = []
for name, team, _ in PLAYERS:
    for i, dt in enumerate(dates):
        long_records.append({
            "date": dt,
            "player": name,
            "value": cumulative[name][i],
            "team": team,
        })

df_long = pd.DataFrame(long_records)
df_long = df_long.sort_values(["date", "player"]).reset_index(drop=True)

# Wide format
wide_data: dict[str, list] = {"date": dates}
for name, _, _ in PLAYERS:
    wide_data[name] = cumulative[name]
df_wide = pd.DataFrame(wide_data)

# ---------------------------------------------------------------------------
# Write Excel files
# ---------------------------------------------------------------------------

df_long.to_excel("sample_data/nba_points_2024_long.xlsx", index=False, engine="openpyxl")
df_wide.to_excel("sample_data/nba_points_2024_wide.xlsx", index=False, engine="openpyxl")

print(f"Long format: {len(df_long)} rows, {df_long['player'].nunique()} players, {df_long['date'].nunique()} dates")
print(f"Wide format: {df_wide.shape}")

# Show final leaderboard
final = df_long[df_long["date"] == dates[-1]].sort_values("value", ascending=False)
print("\nFinal leaderboard:")
for _, row in final.iterrows():
    print(f"  {row['player']:30s}  {row['value']:7.1f}  ({row['team']})")
