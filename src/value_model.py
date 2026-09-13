"""Compute Value Score = Production Score per dollar of cap hit.

The raw ratio (production_score / cap_hit) is dominated by rookie-scale and
minimum-salary players: a solid rotation player making $2M can post a raw
ratio 10-20x higher than a max-salary star with an equally solid Production
Score, purely from the tiny denominator. That's a real signal (rookie
contracts *are* where most surplus value lives around the league) but a raw
ratio makes the "readable 0-100" scale required by the project meaningless,
since a handful of extreme cheap-labor outliers would compress everyone
else into the bottom few points.

Instead we rank players by that raw ratio and convert the rank to a
percentile (0-100), same approach as the Production Score components. A
Value Score of 90 means "top 10% of qualified players in production
generated per dollar spent," which stays interpretable regardless of how
extreme the raw ratio's tails get.
"""
from __future__ import annotations

import pandas as pd


def compute_value_score(df: pd.DataFrame) -> pd.DataFrame:
    """Add `value_ratio` (raw) and `value_score` (0-100 percentile) to df.

    Requires `production_score` and `cap_hit` (in dollars) columns.
    """
    if "production_score" not in df.columns:
        raise ValueError("compute_value_score requires a 'production_score' column")
    if "cap_hit" not in df.columns:
        raise ValueError("compute_value_score requires a 'cap_hit' column")

    out = df.copy()
    if (out["cap_hit"] <= 0).any():
        raise ValueError("cap_hit must be positive for all rows; found zero/negative values")

    # Production Score points generated per $1M of cap hit -- readable units
    # for anyone spot-checking the numbers, purely a scaling convenience
    # (the percentile conversion below is what actually drives the ranking).
    out["value_ratio"] = out["production_score"] / (out["cap_hit"] / 1_000_000.0)
    out["value_score"] = out["value_ratio"].rank(pct=True) * 100.0
    return out.sort_values("value_score", ascending=False).reset_index(drop=True)
