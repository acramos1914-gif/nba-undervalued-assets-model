"""Build the composite Production Score.

Design goal: measure how good a player's *rate of production* is, not how
much volume a star accumulates by playing 36 minutes a night. Every input
stat is therefore either already a rate/percentage (True Shooting %, Usage
%, Assist %, Rebound %, team Turnover %, PIE) or a per-36-minutes figure,
so a stud who plays 20 minutes a game scores on equal footing with one who
plays 36.

Each component is converted to a percentile rank (0-100) within the
*qualified* player pool before weighting, which:
  - naturally bounds the final score to [0, 100],
  - is robust to outliers (a single absurd per-36 line from a 2-minute
    garbage-time stint can't happen once the minutes/games qualification
    filter has already run),
  - keeps every component on a common, unitless scale so the weights are
    directly comparable to each other.

Why each stat is included and how it's weighted (see config.yaml for the
authoritative numbers):
  - TS_PCT (25%): the single best all-around scoring-efficiency number --
    it folds in three-point and free-throw value, unlike raw FG%. Weighted
    highest because scoring inefficiently at high volume is the classic way
    a box score overstates a player's value.
  - PTS_PER36 (15%): still want to credit actual scoring output, just at a
    normalized rate rather than a real-minutes-biased raw total.
  - AST_PCT (15%): percentage of teammate field goals a player assisted
    while on the floor. Preferred over raw assists per-36 because it's
    already adjusted for team pace and a teammate's own finishing, not just
    the passer's opportunities.
  - REB_PCT (10%): same logic as AST_PCT applied to rebounding -- share of
    available rebounds grabbed while on the floor, independent of pace.
  - STOCKS_PER36 = STL_PER36 + BLK_PER36 (10%): the standard proxy for
    "winning defensive plays" available from box scores; steals and blocks
    are blended into one component so a shot-blocking rim protector and a
    high-steal wing defender aren't compared on two separate undersized
    weights.
  - TOV_PCT (10%, inverted): turnovers per 100 plays used. Inverted
    (100 - percentile) because giving the ball away is a cost, not a
    contribution, and TOV_PCT already normalizes for how often a player has
    the ball versus a teammate.
  - USG_PCT (5%): a small, deliberately modest weight. Usage isn't itself a
    "good" thing -- it's rewarded lightly here to recognize that carrying a
    larger share of the offense is a distinguishable skill/role, while
    TS_PCT (weighted 5x higher) keeps a ball-dominant but inefficient
    player from being rewarded for empty volume.
  - PIE (10%): stats.nba.com's own all-in-one box-score-share metric
    (rebounds, points, assists, steals, blocks, and negatives, as a share
    of all such events in the game). Included as a holistic sanity check
    alongside the more targeted components above, at a moderate weight so
    it can't dominate the score on its own.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

REQUIRED_INPUT_COLS = [
    "TS_PCT",
    "PTS_PER36",
    "REB_PCT",
    "AST_PCT",
    "STL_PER36",
    "BLK_PER36",
    "TOV_PCT",
    "USG_PCT",
    "PIE",
]


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def filter_qualified(
    df: pd.DataFrame, min_minutes: int, min_games: int
) -> pd.DataFrame:
    """Keep only players who cleared the minutes/games sample-size bar.

    Without this, a player who logged 40 garbage-time minutes on hot
    shooting can post a top-of-the-league TS_PCT or per-36 rate. See the
    README's Limitations section for the tradeoffs this filter still
    doesn't fully solve (injury-shortened seasons for otherwise-good
    players, etc.).
    """
    qualified = df[(df["MIN"] >= min_minutes) & (df["GP"] >= min_games)].copy()
    return qualified.reset_index(drop=True)


def _percentile_rank(series: pd.Series) -> pd.Series:
    return series.rank(pct=True) * 100.0


def compute_production_score(
    df: pd.DataFrame, weights: dict[str, float]
) -> pd.DataFrame:
    """Add `production_score` (and each percentile component) to df.

    `df` must already be filtered to the qualified player pool -- percentile
    ranks are computed relative to whatever rows are passed in.
    """
    missing = [c for c in REQUIRED_INPUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required stat columns for scoring: {missing}")

    weight_total = sum(weights.values())
    if not (0.99 <= weight_total <= 1.01):
        raise ValueError(f"production_score weights must sum to 1.0, got {weight_total}")

    out = df.copy()
    out["stocks_per36"] = out["STL_PER36"] + out["BLK_PER36"]

    pctl_ts = _percentile_rank(out["TS_PCT"])
    pctl_pts36 = _percentile_rank(out["PTS_PER36"])
    pctl_reb = _percentile_rank(out["REB_PCT"])
    pctl_ast = _percentile_rank(out["AST_PCT"])
    pctl_stocks = _percentile_rank(out["stocks_per36"])
    pctl_tov = 100.0 - _percentile_rank(out["TOV_PCT"])  # inverted: fewer turnovers is better
    pctl_usg = _percentile_rank(out["USG_PCT"])
    pctl_pie = _percentile_rank(out["PIE"])

    out["pctl_ts_pct"] = pctl_ts
    out["pctl_pts_per36"] = pctl_pts36
    out["pctl_reb_pct"] = pctl_reb
    out["pctl_ast_pct"] = pctl_ast
    out["pctl_stocks_per36"] = pctl_stocks
    out["pctl_tov_pct"] = pctl_tov
    out["pctl_usg_pct"] = pctl_usg
    out["pctl_pie"] = pctl_pie

    out["production_score"] = (
        weights["ts_pct"] * pctl_ts
        + weights["pts_per36"] * pctl_pts36
        + weights["reb_pct"] * pctl_reb
        + weights["ast_pct"] * pctl_ast
        + weights["stocks_per36"] * pctl_stocks
        + weights["tov_pct"] * pctl_tov
        + weights["usg_pct"] * pctl_usg
        + weights["pie"] * pctl_pie
    )
    return out


def run(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Convenience entry point: filter for qualification, then score."""
    config = config or load_config()
    qualified = filter_qualified(
        df,
        min_minutes=config["qualification"]["min_minutes"],
        min_games=config["qualification"]["min_games"],
    )
    return compute_production_score(qualified, config["production_score"]["weights"])
