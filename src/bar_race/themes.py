"""Visual theme system — 50 selectable themes for bar-chart-race."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Theme:
    """Controls ALL visual aspects of a bar-chart-race render."""

    name: str
    slug: str  # CLI-friendly name like "espn-broadcast"
    description: str

    # Background
    bg_type: str = "gradient"  # "gradient", "solid", "split"
    bg_colors: list[str] = field(default_factory=lambda: ["#0f0c29", "#302b63"])
    bg_angle: int = 180  # gradient angle in degrees (180 = top-to-bottom)

    # Accent elements
    accent_color: str = "#ffffff"
    accent_secondary: str = "#888888"
    show_accent_line: bool = False
    show_diagonal_slash: bool = False
    show_court_lines: bool = False

    # Bar style
    bar_radius: int = 10  # 0=square, 4=slight, 20=pill
    bar_opacity: float = 1.0
    bar_border: bool = False
    bar_border_width: int = 2
    bar_gradient: bool = False
    bar_team_stripe: bool = False
    bar_skew: float = 0.0
    show_highlight_strip: bool = True
    show_shadow_strip: bool = True

    # Leader effects
    leader_glow: bool = True
    leader_glow_color: str = "team"  # "team" or hex
    leader_outline: bool = False
    leader_underline: bool = False
    leader_bg_highlight: bool = False

    # Rank numbers
    show_rank_numbers: bool = False
    rank_giant_watermark: bool = False
    rank_number_style: str = "normal"  # "normal", "padded", "badge"

    # Text
    font_family: str = "sans"  # "sans", "serif", "mono", "condensed"
    text_color: str = "#ffffff"
    text_secondary_color: str = "#cccccc"
    label_case: str = "normal"  # "normal", "upper", "title"
    label_position: str = "outside"  # "outside", "inside", "outside-right"
    value_suffix: str = ""

    # Date display
    date_color: str = "#ffffff"
    date_opacity: float = 0.2
    date_position: str = "bottom-right"
    date_format: str = "MMM DD, YYYY"

    # Headshot
    headshot_shape: str = "circle"  # "circle", "rounded", "square", "none"
    headshot_style: str = "circle"  # "circle", "shrink-pad", "vignette", "hard-alpha", "rectangle"
    headshot_border: bool = False
    headshot_border_color: str = "team"  # "team", "accent", or hex
    headshot_position: str = "in-bar"

    # Title area
    title_color: str = "#ffffff"
    title_position: str = "top-left"
    show_branding_tag: bool = False
    branding_text: str = ""
    branding_color: str = "#ff0000"

    # Decorative
    show_background_circle: bool = False
    show_grid_lines: bool = False
    border_frame: str = "none"  # "none", "top-bottom", "full", "left-accent"

    # Overlays
    show_reign_tracker: bool = True
    show_gap_alerts: bool = True

    # Noise & vignette (inherited from config but theme can override)
    vignette: bool = True
    noise: bool = True
    bar_shadow: bool = True


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

def _t(slug: str, name: str, desc: str, **kw) -> Theme:
    """Shorthand theme constructor."""
    return Theme(name=name, slug=slug, description=desc, **kw)


THEMES: dict[str, Theme] = {}


def _register(*themes: Theme) -> None:
    for t in themes:
        THEMES[t.slug] = t


_register(
    # 1
    _t("espn-broadcast", "ESPN Broadcast",
       "Red/black diagonal slash. Giant rank numbers. ESPN SportsCenter energy.",
       bg_type="gradient", bg_colors=["#1a1a1a", "#0a0a0a"],
       accent_color="#cc0000", accent_secondary="#ff3333",
       show_diagonal_slash=True, show_accent_line=True,
       bar_radius=4, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#cc0000",
       leader_outline=True,
       show_rank_numbers=True, rank_giant_watermark=True, rank_number_style="normal",
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#cccccc",
       date_opacity=0.15, date_position="bottom-right",
       title_color="#ffffff",
       show_branding_tag=True, branding_text="SPORTSCENTER", branding_color="#cc0000",
       headshot_style="rectangle", label_position="inside",
       border_frame="top-bottom",
       vignette=False, noise=False, bar_shadow=True),

    # 2
    _t("bleacher-report", "Bleacher Report",
       "Black with orange-to-red fire borders. Bold condensed type.",
       bg_type="solid", bg_colors=["#0d0d0d"],
       accent_color="#ff6600", accent_secondary="#ff2200",
       show_accent_line=True,
       bar_radius=4, bar_team_stripe=True, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff6600",
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#aaaaaa",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="B/R", branding_color="#ff6600",
       headshot_style="shrink-pad", label_position="inside",
       border_frame="top-bottom",
       vignette=False, noise=False, bar_shadow=True),

    # 3
    _t("stadium-jumbotron", "Stadium Jumbotron",
       "Deep navy, basketball court lines overlay, LED scoreboard feel.",
       bg_type="gradient", bg_colors=["#0a1628", "#051020"],
       accent_color="#00aaff", accent_secondary="#0066cc",
       show_court_lines=True,
       bar_radius=2, bar_opacity=0.95,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_outline=True, leader_glow_color="#00aaff",
       font_family="mono",
       text_color="#e0e8ff", text_secondary_color="#8899bb",
       date_color="#00aaff", date_opacity=0.25,
       headshot_border=True, headshot_border_color="accent",
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 4
    _t("house-of-highlights", "House of Highlights",
       "Pure black, giant transparent rank watermarks. Instagram-native.",
       bg_type="solid", bg_colors=["#000000"],
       accent_color="#ffffff", accent_secondary="#666666",
       bar_radius=6, bar_team_stripe=True,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=True, leader_glow_color="team",
       show_rank_numbers=True, rank_giant_watermark=True,
       font_family="sans", label_case="normal",
       text_color="#ffffff", text_secondary_color="#888888",
       date_opacity=0.1,
       headshot_shape="rounded", headshot_style="rectangle",
       label_position="inside",
       vignette=False, noise=False, bar_shadow=True),

    # 5
    _t("tnt-broadcast", "TNT Broadcast",
       "Dark charcoal, red accent line, elegant broadcast. Red leader underline.",
       bg_type="gradient", bg_colors=["#222222", "#111111"],
       accent_color="#cc0000", accent_secondary="#990000",
       show_accent_line=True,
       bar_radius=6, show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=False, leader_underline=True,
       font_family="serif",
       text_color="#eeeeee", text_secondary_color="#aaaaaa",
       title_color="#ffffff",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="NBA ON TNT", branding_color="#cc0000",
       headshot_style="vignette",
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 6
    _t("hoop-district", "Hoop District",
       "Black with basketball-orange accents. Court circle watermark. Outlined bars.",
       bg_type="solid", bg_colors=["#0a0a0a"],
       accent_color="#ff8844", accent_secondary="#cc6633",
       show_background_circle=True,
       bar_radius=4, bar_border=True, bar_border_width=2, bar_team_stripe=True,
       bar_opacity=0.85,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=True, leader_glow_color="#ff8844",
       font_family="sans", label_case="upper",
       text_color="#ffffff", text_secondary_color="#ff8844",
       date_color="#ff8844", date_opacity=0.2,
       headshot_border=True, headshot_border_color="#ff8844",
       vignette=False, noise=True, bar_shadow=False),

    # 7
    _t("fantasy-leaderboard", "Fantasy Leaderboard",
       "Very dark purple-black. Gold accents. Rank badges. DraftKings energy.",
       bg_type="gradient", bg_colors=["#0c0c14", "#14101e"],
       accent_color="#ffd700", accent_secondary="#ffaa00",
       bar_radius=8, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       show_rank_numbers=True, rank_number_style="badge",
       font_family="sans",
       text_color="#e8e0ff", text_secondary_color="#9988cc",
       value_suffix=" PTS",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="FANTASY", branding_color="#ffd700",
       headshot_style="shrink-pad",
       border_frame="left-accent",
       vignette=True, noise=True, bar_shadow=True),

    # 8
    _t("bold-diagonal", "Bold Diagonal",
       "Aggressive diagonal slash overlays. SportsCenter Top 10 energy.",
       bg_type="gradient", bg_colors=["#1a1a2e", "#0f0f1a"],
       accent_color="#ff4444", accent_secondary="#4444ff",
       show_diagonal_slash=True, show_accent_line=True,
       bar_radius=4, bar_gradient=True, bar_skew=-2.0,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff4444",
       show_rank_numbers=True, rank_giant_watermark=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff",
       label_position="inside",
       date_opacity=0.15,
       border_frame="top-bottom",
       vignette=False, noise=False, bar_shadow=True),

    # 9
    _t("social-card", "Social Card",
       "Dark background, rounded card bars with team gradient. Instagram story native.",
       bg_type="gradient", bg_colors=["#121218", "#1a1a24"],
       accent_color="#6c5ce7", accent_secondary="#a29bfe",
       bar_radius=16, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="team",
       font_family="sans",
       text_color="#ffffff", text_secondary_color="#aaaacc",
       date_opacity=0.12,
       headshot_shape="rounded", headshot_border=True, headshot_border_color="team",
       vignette=True, noise=False, bar_shadow=True),

    # 10
    _t("versus-matchup", "Versus Matchup",
       "Tournament bracket aesthetic. Gold accents. VS energy.",
       bg_type="gradient", bg_colors=["#1a1510", "#0d0a05"],
       accent_color="#ffd700", accent_secondary="#cc9900",
       show_accent_line=True,
       bar_radius=4, bar_border=True, bar_border_width=2,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       leader_outline=True,
       font_family="condensed", label_case="upper",
       text_color="#ffd700", text_secondary_color="#ccaa44",
       date_color="#ffd700", date_opacity=0.2,
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 11
    _t("nba-official", "NBA Official",
       "NBA blue gradient. Clean white bars. Official broadcast look.",
       bg_type="gradient", bg_colors=["#1d428a", "#0e2252"],
       accent_color="#c8102e", accent_secondary="#ffffff",
       show_accent_line=True,
       bar_radius=6,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#c8102e",
       font_family="sans", label_case="upper",
       text_color="#ffffff", text_secondary_color="#b0c4ff",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="NBA", branding_color="#c8102e",
       headshot_border=True, headshot_border_color="#ffffff",
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 12
    _t("midnight-premium", "Midnight Premium",
       "Deep dark gradient, rounded bars, subtle glow. Premium/luxury feel. Default theme.",
       bg_type="gradient", bg_colors=["#0f0c29", "#302b63"],
       accent_color="#ffffff", accent_secondary="#888888",
       bar_radius=10,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="team",
       font_family="sans",
       text_color="#ffffff", text_secondary_color="#cccccc",
       date_opacity=0.2,
       headshot_shape="circle",
       vignette=True, noise=True, bar_shadow=True),

    # 13
    _t("clean-light", "Clean Light",
       "White/cream background, flat colored bars. Bloomberg/FT data viz style.",
       bg_type="gradient", bg_colors=["#f8f6f0", "#eae6dc"],
       accent_color="#333333", accent_secondary="#666666",
       bar_radius=4,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=False,
       show_rank_numbers=True, rank_number_style="padded",
       font_family="serif",
       text_color="#222222", text_secondary_color="#666666",
       title_color="#111111",
       date_color="#888888", date_opacity=0.5,
       headshot_shape="circle", headshot_border=True, headshot_border_color="#cccccc",
       show_grid_lines=True,
       vignette=False, noise=False, bar_shadow=False),

    # 14
    _t("fire-and-ice", "Fire and Ice",
       "Split background: warm red-black left, cool blue-black right.",
       bg_type="split", bg_colors=["#2a0a0a", "#0a0a2a"],
       accent_color="#ff4444", accent_secondary="#4488ff",
       bar_radius=6, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff6644",
       font_family="sans",
       text_color="#ffffff",
       date_opacity=0.15,
       vignette=True, noise=True, bar_shadow=True),

    # 15
    _t("neon-court", "Neon Court",
       "Black background, neon green accents. Cyber/gaming aesthetic.",
       bg_type="solid", bg_colors=["#050505"],
       accent_color="#00ff88", accent_secondary="#00cc66",
       show_court_lines=True,
       bar_radius=0, bar_border=True, bar_border_width=2,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=True, leader_glow_color="#00ff88",
       leader_outline=True,
       font_family="mono",
       text_color="#00ff88", text_secondary_color="#008844",
       date_color="#00ff88", date_opacity=0.2,
       headshot_shape="square", headshot_style="hard-alpha",
       headshot_border=True, headshot_border_color="#00ff88",
       vignette=False, noise=True, bar_shadow=False),

    # 16
    _t("playoff-intensity", "Playoff Intensity",
       "Dark with gold everywhere. Playoff bracket energy. Thick bar borders.",
       bg_type="gradient", bg_colors=["#1a1400", "#0d0a00"],
       accent_color="#ffd700", accent_secondary="#ffaa00",
       show_accent_line=True,
       bar_radius=6, bar_border=True, bar_border_width=3,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       leader_outline=True, leader_bg_highlight=True,
       show_rank_numbers=True, rank_number_style="badge",
       font_family="condensed", label_case="upper",
       text_color="#ffd700", text_secondary_color="#cc9900",
       date_color="#ffd700", date_opacity=0.2,
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 17
    _t("draft-night", "Draft Night",
       "Dark navy with NBA Draft stage lighting feel. Silver/gray secondary.",
       bg_type="gradient", bg_colors=["#0a1628", "#060e1a"],
       accent_color="#c0c0c0", accent_secondary="#808080",
       bar_radius=8, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#c0c0c0",
       leader_bg_highlight=True,
       font_family="sans",
       text_color="#e0e0e0", text_secondary_color="#808080",
       date_opacity=0.15,
       headshot_border=True, headshot_border_color="#c0c0c0",
       show_branding_tag=True, branding_text="DRAFT", branding_color="#c0c0c0",
       vignette=True, noise=True, bar_shadow=True),

    # 18
    _t("streetball", "Streetball",
       "Concrete/asphalt gray background. Graffiti-bold aesthetic. Orange accents.",
       bg_type="gradient", bg_colors=["#2a2a28", "#1a1a18"],
       accent_color="#ff6600", accent_secondary="#cc4400",
       bar_radius=2, bar_team_stripe=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff6600",
       font_family="condensed", label_case="upper",
       text_color="#f0ece0", text_secondary_color="#999080",
       date_color="#ff6600", date_opacity=0.2,
       headshot_shape="square",
       vignette=False, noise=True, bar_shadow=True),

    # 19
    _t("all-star-game", "All-Star Game",
       "Gradient from team blue to team red. All-Star game concept.",
       bg_type="gradient", bg_colors=["#1d428a", "#c8102e"],
       accent_color="#ffffff", accent_secondary="#ffd700",
       show_accent_line=True,
       bar_radius=10,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       font_family="sans",
       text_color="#ffffff", text_secondary_color="#ddcccc",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="ALL-STAR", branding_color="#ffd700",
       headshot_border=True, headshot_border_color="#ffffff",
       vignette=True, noise=False, bar_shadow=True),

    # 20
    _t("clutch-time", "Clutch Time",
       "Deep red/black with urgency. Countdown styling. CLUTCH TIME branding.",
       bg_type="gradient", bg_colors=["#2a0000", "#0a0000"],
       accent_color="#ff0000", accent_secondary="#cc0000",
       show_accent_line=True,
       bar_radius=4, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff0000",
       font_family="condensed", label_case="upper",
       text_color="#ff4444", text_secondary_color="#cc2222",
       date_color="#ff0000", date_opacity=0.25,
       show_branding_tag=True, branding_text="CLUTCH TIME", branding_color="#ff0000",
       border_frame="top-bottom",
       vignette=True, noise=True, bar_shadow=True),

    # 21
    _t("slam-dunk", "Slam Dunk",
       "Orange dominant accent. Bars with upward energy. Impact font feel.",
       bg_type="gradient", bg_colors=["#1a0800", "#0d0400"],
       accent_color="#ff6600", accent_secondary="#ff3300",
       show_accent_line=True,
       bar_radius=6, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff6600",
       leader_outline=True,
       show_rank_numbers=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#ff9944",
       date_color="#ff6600", date_opacity=0.2,
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 22
    _t("triple-double", "Triple Double",
       "Three accent colors cycling. Dashboard/analytics look.",
       bg_type="gradient", bg_colors=["#0a0a14", "#14141e"],
       accent_color="#00ccff", accent_secondary="#ff6600",
       show_grid_lines=True,
       bar_radius=4,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#00ccff",
       show_rank_numbers=True, rank_number_style="padded",
       font_family="mono",
       text_color="#e0e8ff", text_secondary_color="#6688aa",
       value_suffix=" PTS",
       date_opacity=0.2,
       border_frame="left-accent",
       vignette=False, noise=False, bar_shadow=True),

    # 23
    _t("game-winner", "Game Winner",
       "Black with gold burst accent. Dramatic. Leader gets gold treatment.",
       bg_type="gradient", bg_colors=["#0d0a00", "#000000"],
       accent_color="#ffd700", accent_secondary="#ffaa00",
       bar_radius=8,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       leader_outline=True, leader_bg_highlight=True,
       font_family="sans",
       text_color="#ffd700", text_secondary_color="#ccaa44",
       date_color="#ffd700", date_opacity=0.15,
       headshot_border=True, headshot_border_color="#ffd700",
       vignette=True, noise=True, bar_shadow=True),

    # 24
    _t("press-conference", "Press Conference",
       "Dark blue podium aesthetic. Professional press conference vibe.",
       bg_type="gradient", bg_colors=["#0c1a30", "#061020"],
       accent_color="#ffffff", accent_secondary="#4488cc",
       bar_radius=6,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=False, leader_underline=True,
       font_family="serif",
       text_color="#e0e8f0", text_secondary_color="#8899aa",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="PRESS", branding_color="#4488cc",
       headshot_border=True, headshot_border_color="#ffffff",
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 25
    _t("vintage-nba", "Vintage NBA",
       "Retro 80s/90s NBA aesthetic. Muted colors. Serif fonts. Classic feel.",
       bg_type="gradient", bg_colors=["#2c2418", "#1a1410"],
       accent_color="#cc8844", accent_secondary="#886633",
       bar_radius=2, bar_opacity=0.9,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=False, leader_underline=True,
       show_rank_numbers=True, rank_number_style="padded",
       font_family="serif",
       text_color="#e8dcc8", text_secondary_color="#aa9878",
       date_color="#cc8844", date_opacity=0.25,
       headshot_shape="rounded", headshot_border=True, headshot_border_color="#cc8844",
       vignette=True, noise=True, bar_shadow=True),
)

# ---------------------------------------------------------------------------
# Themes 26–50
# ---------------------------------------------------------------------------

_register(
    # 26
    _t("overtime", "Overtime",
       "OT brand aesthetic. Bright white on black. Clean modern. Youth/Gen-Z energy.",
       bg_type="solid", bg_colors=["#000000"],
       accent_color="#ffffff", accent_secondary="#cccccc",
       bar_radius=8, bar_gradient=False,
       show_highlight_strip=True, show_shadow_strip=False,
       leader_glow=True, leader_glow_color="#ffffff",
       font_family="sans", label_case="upper",
       text_color="#ffffff", text_secondary_color="#aaaaaa",
       date_opacity=0.12,
       headshot_shape="rounded",
       show_branding_tag=True, branding_text="OT", branding_color="#ffffff",
       vignette=False, noise=False, bar_shadow=True),

    # 27
    _t("first-take", "First Take",
       "ESPN First Take debate show. Split red/blue. Argumentative energy. Bold opinions.",
       bg_type="split", bg_colors=["#cc0000", "#003399"],
       accent_color="#ffffff", accent_secondary="#ffcc00",
       show_diagonal_slash=True, show_accent_line=True,
       bar_radius=4, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffcc00",
       leader_outline=True,
       show_rank_numbers=True, rank_giant_watermark=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#dddddd",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="FIRST TAKE", branding_color="#ffcc00",
       label_position="inside",
       border_frame="top-bottom",
       vignette=False, noise=False, bar_shadow=True),

    # 28
    _t("undisputed", "Undisputed",
       "Fox Sports. Blue and yellow accents. Skip Bayless energy. UNDISPUTED branding.",
       bg_type="gradient", bg_colors=["#002244", "#001133"],
       accent_color="#ffcc00", accent_secondary="#0066cc",
       show_accent_line=True,
       bar_radius=4, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffcc00",
       leader_outline=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#88aacc",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="UNDISPUTED", branding_color="#ffcc00",
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 29
    _t("the-ringer", "The Ringer",
       "Clean, editorial, data-focused. Minimal decoration. The Ringer web aesthetic.",
       bg_type="solid", bg_colors=["#f5f5f5"],
       accent_color="#222222", accent_secondary="#666666",
       bar_radius=4,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=False, leader_underline=True,
       show_rank_numbers=True, rank_number_style="padded",
       font_family="serif",
       text_color="#1a1a1a", text_secondary_color="#555555",
       title_color="#000000",
       date_color="#888888", date_opacity=0.4,
       headshot_shape="circle", headshot_style="rectangle",
       headshot_border=True, headshot_border_color="#dddddd",
       show_grid_lines=True,
       vignette=False, noise=False, bar_shadow=False),

    # 30
    _t("statmuse", "StatMuse",
       "AI/stats bot aesthetic. Clean data viz. Purple accents. Modern.",
       bg_type="gradient", bg_colors=["#0f0a1a", "#1a1028"],
       accent_color="#7c3aed", accent_secondary="#a855f7",
       bar_radius=10, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#7c3aed",
       show_rank_numbers=True, rank_number_style="padded",
       font_family="sans",
       text_color="#e8e0ff", text_secondary_color="#9988bb",
       date_color="#7c3aed", date_opacity=0.2,
       headshot_border=True, headshot_border_color="#7c3aed",
       show_grid_lines=True,
       vignette=True, noise=False, bar_shadow=True),

    # 31
    _t("basketball-reference", "Basketball Reference",
       "Light background, minimal styling, data-first. Tables aesthetic translated to bars.",
       bg_type="solid", bg_colors=["#ffffff"],
       accent_color="#336699", accent_secondary="#993333",
       bar_radius=2,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=False,
       show_rank_numbers=True, rank_number_style="normal",
       font_family="mono",
       text_color="#000000", text_secondary_color="#444444",
       title_color="#333333",
       date_color="#666666", date_opacity=0.5,
       headshot_shape="square", headshot_style="rectangle",
       headshot_border=True, headshot_border_color="#cccccc",
       show_grid_lines=True,
       vignette=False, noise=False, bar_shadow=False),

    # 32
    _t("2k-myteam", "2K MyTEAM",
       "NBA 2K video game aesthetic. Card game colors. Purple/gold. Gaming energy.",
       bg_type="gradient", bg_colors=["#1a0a2e", "#0d0518"],
       accent_color="#ffd700", accent_secondary="#9933ff",
       show_accent_line=True,
       bar_radius=6, bar_gradient=True, bar_border=True, bar_border_width=2,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       leader_outline=True, leader_bg_highlight=True,
       show_rank_numbers=True, rank_number_style="badge",
       font_family="condensed", label_case="upper",
       text_color="#ffd700", text_secondary_color="#cc99ff",
       date_color="#9933ff", date_opacity=0.2,
       headshot_border=True, headshot_border_color="#ffd700",
       show_branding_tag=True, branding_text="MyTEAM", branding_color="#ffd700",
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 33
    _t("topshot", "Top Shot",
       "NBA Top Shot/NFT aesthetic. Holographic accent concept. Dark with rainbow edge.",
       bg_type="gradient", bg_colors=["#0a0a14", "#050510"],
       accent_color="#00ffcc", accent_secondary="#ff00aa",
       show_accent_line=True,
       bar_radius=12, bar_gradient=True, bar_border=True, bar_border_width=2,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#00ffcc",
       leader_outline=True,
       font_family="sans",
       text_color="#e0fff0", text_secondary_color="#66ccaa",
       date_color="#00ffcc", date_opacity=0.15,
       headshot_shape="rounded", headshot_border=True, headshot_border_color="#00ffcc",
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 34
    _t("betting-odds", "Betting Odds",
       "Sportsbook aesthetic. Green felt background concept. Gold numbers. Odds-board feel.",
       bg_type="gradient", bg_colors=["#0a3010", "#061e08"],
       accent_color="#ffd700", accent_secondary="#44cc44",
       bar_radius=2, bar_border=True, bar_border_width=1,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       show_rank_numbers=True, rank_number_style="normal",
       font_family="mono",
       text_color="#ffd700", text_secondary_color="#88bb88",
       date_color="#ffd700", date_opacity=0.25,
       show_grid_lines=True,
       headshot_shape="square",
       show_branding_tag=True, branding_text="ODDS", branding_color="#ffd700",
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 35
    _t("halftime-report", "Halftime Report",
       "Mid-game broadcast. Split screen feel. HALFTIME branding. Stats overlay look.",
       bg_type="split", bg_colors=["#1a1a22", "#0a0a12"],
       accent_color="#ffffff", accent_secondary="#ff6600",
       show_accent_line=True,
       bar_radius=6,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=False, leader_underline=True,
       show_rank_numbers=True, rank_number_style="padded",
       font_family="sans", label_case="upper",
       text_color="#ffffff", text_secondary_color="#aaaaaa",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="HALFTIME", branding_color="#ff6600",
       border_frame="top-bottom",
       vignette=False, noise=False, bar_shadow=True),

    # 36
    _t("hardwood-classic", "Hardwood Classic",
       "Wood floor color palette concept. Brown/amber tones. Classic gymnasium.",
       bg_type="gradient", bg_colors=["#3d2b1f", "#261a10"],
       accent_color="#d4a56a", accent_secondary="#8b6914",
       bar_radius=4, bar_opacity=0.9,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#d4a56a",
       font_family="serif",
       text_color="#f0e0c8", text_secondary_color="#b8956a",
       date_color="#d4a56a", date_opacity=0.25,
       headshot_shape="rounded", headshot_border=True, headshot_border_color="#d4a56a",
       show_court_lines=True,
       vignette=True, noise=True, bar_shadow=True),

    # 37
    _t("city-edition", "City Edition",
       "Modern gradient with multiple team colors blending. City Edition jersey aesthetic.",
       bg_type="gradient", bg_colors=["#1a0a28", "#0a1428"],
       accent_color="#ff6ec7", accent_secondary="#00ccff",
       bar_radius=14, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="team",
       font_family="sans",
       text_color="#ffffff", text_secondary_color="#cc99dd",
       date_opacity=0.12,
       headshot_shape="circle", headshot_border=True, headshot_border_color="team",
       vignette=True, noise=False, bar_shadow=True),

    # 38
    _t("rising-stars", "Rising Stars",
       "All-Star Rising Stars aesthetic. Young/fresh. Bright gradient accents.",
       bg_type="gradient", bg_colors=["#0a1e3d", "#1a0a3d"],
       accent_color="#00ddff", accent_secondary="#ff44aa",
       show_accent_line=True,
       bar_radius=10, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#00ddff",
       font_family="sans", label_case="upper",
       text_color="#ffffff", text_secondary_color="#88bbdd",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="RISING STARS", branding_color="#00ddff",
       headshot_border=True, headshot_border_color="#00ddff",
       vignette=True, noise=False, bar_shadow=True),

    # 39
    _t("in-season-tournament", "In-Season Tournament",
       "NBA Cup aesthetic. Teal/gold. Tournament bracket energy.",
       bg_type="gradient", bg_colors=["#0a2828", "#051818"],
       accent_color="#00ccaa", accent_secondary="#ffd700",
       show_accent_line=True,
       bar_radius=6, bar_border=True, bar_border_width=2,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       leader_outline=True,
       show_rank_numbers=True, rank_number_style="badge",
       font_family="condensed", label_case="upper",
       text_color="#00ffcc", text_secondary_color="#44aa88",
       date_color="#ffd700", date_opacity=0.2,
       show_branding_tag=True, branding_text="NBA CUP", branding_color="#ffd700",
       border_frame="full",
       vignette=True, noise=True, bar_shadow=True),

    # 40
    _t("christmas-day", "Christmas Day",
       "Christmas game special. Red and green accents. Festive but sporty.",
       bg_type="gradient", bg_colors=["#1a0a0a", "#0a1a0a"],
       accent_color="#cc0000", accent_secondary="#008800",
       show_accent_line=True,
       bar_radius=8,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#cc0000",
       font_family="serif",
       text_color="#ffffff", text_secondary_color="#cccccc",
       date_opacity=0.2,
       show_branding_tag=True, branding_text="CHRISTMAS DAY", branding_color="#cc0000",
       headshot_border=True, headshot_border_color="#ffd700",
       border_frame="top-bottom",
       vignette=True, noise=True, bar_shadow=True),

    # 41
    _t("mvp-race", "MVP Race",
       "Gold/black premium. Trophy aesthetic. MVP TRACKER branding.",
       bg_type="gradient", bg_colors=["#141008", "#0a0804"],
       accent_color="#ffd700", accent_secondary="#ffaa00",
       show_accent_line=True,
       bar_radius=8, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ffd700",
       leader_outline=True, leader_bg_highlight=True,
       show_rank_numbers=True, rank_number_style="badge",
       font_family="sans", label_case="upper",
       text_color="#ffd700", text_secondary_color="#ccaa44",
       date_color="#ffd700", date_opacity=0.2,
       show_branding_tag=True, branding_text="MVP TRACKER", branding_color="#ffd700",
       headshot_border=True, headshot_border_color="#ffd700",
       border_frame="left-accent",
       vignette=True, noise=True, bar_shadow=True),

    # 42
    _t("sixth-man", "Sixth Man",
       "Bench energy. Secondary/complementary colors. 6TH MAN badge.",
       bg_type="gradient", bg_colors=["#14141e", "#0a0a14"],
       accent_color="#ff8800", accent_secondary="#6644cc",
       bar_radius=6, bar_team_stripe=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff8800",
       show_rank_numbers=True, rank_number_style="badge",
       font_family="sans",
       text_color="#ffffff", text_secondary_color="#aaaacc",
       date_opacity=0.15,
       show_branding_tag=True, branding_text="6TH MAN", branding_color="#ff8800",
       vignette=True, noise=True, bar_shadow=True),

    # 43
    _t("fast-break", "Fast Break",
       "Speed/motion aesthetic. Horizontal motion lines concept. Energetic orange.",
       bg_type="gradient", bg_colors=["#1a0800", "#0a0400"],
       accent_color="#ff6600", accent_secondary="#ff3300",
       show_accent_line=True, show_diagonal_slash=True,
       bar_radius=4, bar_gradient=True, bar_skew=-1.5,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff6600",
       leader_outline=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#ff9944",
       date_color="#ff6600", date_opacity=0.2,
       border_frame="top-bottom",
       vignette=False, noise=False, bar_shadow=True),

    # 44
    _t("paint-zone", "Paint Zone",
       "Basketball paint/key zone concept. Strong blocks of color.",
       bg_type="gradient", bg_colors=["#1a1428", "#0d0a18"],
       accent_color="#cc3333", accent_secondary="#3333cc",
       bar_radius=2, bar_border=True, bar_border_width=3, bar_opacity=0.95,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#cc3333",
       leader_bg_highlight=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#bbaacc",
       date_opacity=0.15,
       show_background_circle=True,
       vignette=True, noise=True, bar_shadow=True),

    # 45
    _t("three-point-line", "Three-Point Line",
       "Arc decorative element. Emphasis on long-range. Cool blue tones.",
       bg_type="gradient", bg_colors=["#0a1428", "#050a18"],
       accent_color="#00aaff", accent_secondary="#0066cc",
       show_court_lines=True,
       bar_radius=10, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#00aaff",
       font_family="sans",
       text_color="#c0e0ff", text_secondary_color="#6688aa",
       date_color="#00aaff", date_opacity=0.2,
       headshot_border=True, headshot_border_color="#00aaff",
       vignette=True, noise=False, bar_shadow=True),

    # 46
    _t("dunk-contest", "Dunk Contest",
       "High energy red/orange. Impact visual. SLAM aesthetic.",
       bg_type="gradient", bg_colors=["#2a0000", "#1a0500"],
       accent_color="#ff3300", accent_secondary="#ff6600",
       show_accent_line=True, show_diagonal_slash=True,
       bar_radius=6, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff3300",
       leader_outline=True,
       show_rank_numbers=True, rank_giant_watermark=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#ff8866",
       date_color="#ff3300", date_opacity=0.2,
       show_branding_tag=True, branding_text="SLAM", branding_color="#ff3300",
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 47
    _t("woj-bomb", "Woj Bomb",
       "Breaking news aesthetic. Red BREAKING banner. Alert/urgent feel.",
       bg_type="gradient", bg_colors=["#1a0000", "#0a0000"],
       accent_color="#ff0000", accent_secondary="#ffffff",
       show_accent_line=True,
       bar_radius=4, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff0000",
       leader_outline=True,
       font_family="condensed", label_case="upper",
       text_color="#ffffff", text_secondary_color="#ff6666",
       date_color="#ff0000", date_opacity=0.25,
       show_branding_tag=True, branding_text="BREAKING", branding_color="#ff0000",
       border_frame="top-bottom",
       vignette=True, noise=True, bar_shadow=True),

    # 48
    _t("shams-report", "Shams Report",
       "Breaking news with blue accents. Athletic brand feel.",
       bg_type="gradient", bg_colors=["#0a0a1a", "#050510"],
       accent_color="#1a8cff", accent_secondary="#ffffff",
       show_accent_line=True,
       bar_radius=6, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#1a8cff",
       leader_underline=True,
       font_family="sans", label_case="upper",
       text_color="#ffffff", text_secondary_color="#88aadd",
       date_color="#1a8cff", date_opacity=0.2,
       show_branding_tag=True, branding_text="BREAKING", branding_color="#1a8cff",
       border_frame="top-bottom",
       vignette=True, noise=False, bar_shadow=True),

    # 49
    _t("hoopshype-dark", "HoopsHype Dark",
       "HoopsHype brand theme. Dark navy with orange/blue accents. HoopsHype branding.",
       bg_type="gradient", bg_colors=["#0c1a2e", "#061020"],
       accent_color="#ff6b35", accent_secondary="#1a8cff",
       show_accent_line=True,
       bar_radius=8, bar_gradient=True,
       show_highlight_strip=True, show_shadow_strip=True,
       leader_glow=True, leader_glow_color="#ff6b35",
       leader_underline=True,
       show_rank_numbers=True, rank_number_style="padded",
       font_family="sans",
       text_color="#ffffff", text_secondary_color="#88aacc",
       date_color="#ff6b35", date_opacity=0.2,
       headshot_style="shrink-pad",
       headshot_border=True, headshot_border_color="#ff6b35",
       show_branding_tag=True, branding_text="HOOPSHYPE", branding_color="#ff6b35",
       border_frame="left-accent",
       vignette=True, noise=False, bar_shadow=True),

    # 50
    _t("hoopshype-light", "HoopsHype Light",
       "Light HoopsHype brand. Clean white with brand colors. HoopsHype branding.",
       bg_type="gradient", bg_colors=["#f8f8fc", "#e8e8f0"],
       accent_color="#ff6b35", accent_secondary="#1a8cff",
       bar_radius=8,
       show_highlight_strip=False, show_shadow_strip=False,
       leader_glow=False, leader_underline=True,
       show_rank_numbers=True, rank_number_style="padded",
       font_family="sans",
       text_color="#1a1a2e", text_secondary_color="#555566",
       title_color="#0c1a2e",
       date_color="#888888", date_opacity=0.4,
       headshot_shape="circle", headshot_style="shrink-pad",
       headshot_border=True, headshot_border_color="#ff6b35",
       show_branding_tag=True, branding_text="HOOPSHYPE", branding_color="#ff6b35",
       show_grid_lines=True,
       border_frame="left-accent",
       vignette=False, noise=False, bar_shadow=False),
)


def get_theme(slug: str) -> Theme:
    """Return a theme by slug, raising ValueError if not found."""
    if slug not in THEMES:
        raise ValueError(
            f"Unknown theme {slug!r}. "
            f"Choose from: {', '.join(sorted(THEMES))}"
        )
    return THEMES[slug]


def list_themes() -> str:
    """Return a formatted string listing all themes."""
    lines = []
    for slug in sorted(THEMES):
        t = THEMES[slug]
        lines.append(f"  {slug:24s}  {t.description}")
    return "\n".join(lines)
