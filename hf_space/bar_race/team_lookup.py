"""Team name lookup — maps various name formats to canonical abbreviations."""

from __future__ import annotations

# Maps full names, short names, and abbreviations to canonical team codes.
# Case-insensitive matching is done by the lookup function.
_TEAM_MAP: dict[str, str] = {
    # Current 30 NBA teams
    "Atlanta Hawks": "ATL", "Hawks": "ATL", "ATL": "ATL",
    "Boston Celtics": "BOS", "Celtics": "BOS", "BOS": "BOS",
    "Brooklyn Nets": "BKN", "Nets": "BKN", "BKN": "BKN",
    "Charlotte Hornets": "CHA", "Hornets": "CHA", "CHA": "CHA",
    "Chicago Bulls": "CHI", "Bulls": "CHI", "CHI": "CHI",
    "Cleveland Cavaliers": "CLE", "Cavaliers": "CLE", "Cavs": "CLE", "CLE": "CLE",
    "Dallas Mavericks": "DAL", "Mavericks": "DAL", "Mavs": "DAL", "DAL": "DAL",
    "Denver Nuggets": "DEN", "Nuggets": "DEN", "DEN": "DEN",
    "Detroit Pistons": "DET", "Pistons": "DET", "DET": "DET",
    "Golden State Warriors": "GSW", "Warriors": "GSW", "GSW": "GSW",
    "Houston Rockets": "HOU", "Rockets": "HOU", "HOU": "HOU",
    "Indiana Pacers": "IND", "Pacers": "IND", "IND": "IND",
    "Los Angeles Clippers": "LAC", "Clippers": "LAC", "LA Clippers": "LAC", "LAC": "LAC",
    "Los Angeles Lakers": "LAL", "Lakers": "LAL", "LA Lakers": "LAL", "LAL": "LAL",
    "Memphis Grizzlies": "MEM", "Grizzlies": "MEM", "MEM": "MEM",
    "Miami Heat": "MIA", "Heat": "MIA", "MIA": "MIA",
    "Milwaukee Bucks": "MIL", "Bucks": "MIL", "MIL": "MIL",
    "Minnesota Timberwolves": "MIN", "Timberwolves": "MIN", "Wolves": "MIN", "MIN": "MIN",
    "New Orleans Pelicans": "NOP", "Pelicans": "NOP", "NOP": "NOP",
    "New York Knicks": "NYK", "Knicks": "NYK", "NYK": "NYK",
    "Oklahoma City Thunder": "OKC", "Thunder": "OKC", "OKC": "OKC",
    "Orlando Magic": "ORL", "Magic": "ORL", "ORL": "ORL",
    "Philadelphia 76ers": "PHI", "76ers": "PHI", "Sixers": "PHI", "PHI": "PHI",
    "Phoenix Suns": "PHX", "Suns": "PHX", "PHX": "PHX",
    "Portland Trail Blazers": "POR", "Trail Blazers": "POR", "Blazers": "POR", "POR": "POR",
    "Sacramento Kings": "SAC", "Kings": "SAC", "SAC": "SAC",
    "San Antonio Spurs": "SAS", "Spurs": "SAS", "SAS": "SAS",
    "Toronto Raptors": "TOR", "Raptors": "TOR", "TOR": "TOR",
    "Utah Jazz": "UTA", "Jazz": "UTA", "UTA": "UTA",
    "Washington Wizards": "WAS", "Wizards": "WAS", "WAS": "WAS",
    # Historical / relocated teams
    "Seattle SuperSonics": "OKC", "SuperSonics": "OKC", "Sonics": "OKC", "SEA": "OKC",
    "New Jersey Nets": "BKN", "NJN": "BKN",
    "Vancouver Grizzlies": "MEM", "VAN": "MEM",
    "Charlotte Bobcats": "CHA", "Bobcats": "CHA",
    "New Orleans Hornets": "NOP", "NOH": "NOP",
    "New Orleans/Oklahoma City Hornets": "NOP", "NOK": "NOP",
    "Washington Bullets": "WAS", "Bullets": "WAS",
    "San Diego Clippers": "LAC", "SDC": "LAC",
    "Kansas City Kings": "SAC", "KCK": "SAC",
    "Buffalo Braves": "LAC",
    "St. Louis Hawks": "ATL",
    "Minneapolis Lakers": "LAL",
    "Syracuse Nationals": "PHI", "Nationals": "PHI",
    "Fort Wayne Pistons": "DET",
    "Rochester Royals": "SAC",
    "Cincinnati Royals": "SAC",
    "Baltimore Bullets": "WAS",
    "Capital Bullets": "WAS",
    "Chicago Zephyrs": "WAS",
    "Chicago Packers": "WAS",
}

# Build case-insensitive index once.
_LOWER_MAP: dict[str, str] = {k.lower(): v for k, v in _TEAM_MAP.items()}


def lookup_team(name: str) -> str | None:
    """Return the canonical team abbreviation for *name*, or None."""
    return _LOWER_MAP.get(name.strip().lower())


TEAM_SHORT_NAMES: dict[str, str] = {
    "ATL": "Hawks", "BOS": "Celtics", "BKN": "Nets", "CHA": "Hornets",
    "CHI": "Bulls", "CLE": "Cavaliers", "DAL": "Mavericks", "DEN": "Nuggets",
    "DET": "Pistons", "GSW": "Warriors", "HOU": "Rockets", "IND": "Pacers",
    "LAC": "Clippers", "LAL": "Lakers", "MEM": "Grizzlies", "MIA": "Heat",
    "MIL": "Bucks", "MIN": "Timberwolves", "NOP": "Pelicans", "NYK": "Knicks",
    "OKC": "Thunder", "ORL": "Magic", "PHI": "76ers", "PHX": "Suns",
    "POR": "Trail Blazers", "SAC": "Kings", "SAS": "Spurs", "TOR": "Raptors",
    "UTA": "Jazz", "WAS": "Wizards",
}


def get_short_name(name: str) -> str:
    """Return the short franchise name (e.g. 'Lakers') for a team name."""
    abbrev = lookup_team(name)
    if abbrev and abbrev in TEAM_SHORT_NAMES:
        return TEAM_SHORT_NAMES[abbrev]
    return name


def is_team_name(name: str) -> bool:
    """Return True if *name* matches any known team."""
    return name.strip().lower() in _LOWER_MAP


def detect_team_data(names: list[str]) -> bool:
    """Return True if >50% of *names* match known teams."""
    if not names:
        return False
    hits = sum(1 for n in names if is_team_name(n))
    return hits / len(names) > 0.5
