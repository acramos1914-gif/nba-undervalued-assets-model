"""Tests for the composite Production Score. Synthetic fixture data only."""
import pandas as pd
import pytest

from src.production_score import compute_production_score, filter_qualified

WEIGHTS = {
    "ts_pct": 0.25,
    "pts_per36": 0.15,
    "reb_pct": 0.10,
    "ast_pct": 0.15,
    "stocks_per36": 0.10,
    "tov_pct": 0.10,
    "usg_pct": 0.05,
    "pie": 0.10,
}


def _make_stats_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player": ["Star", "Role Player", "Inefficient Volume Scorer"],
            "MIN": [2500, 1800, 2200],
            "GP": [75, 70, 72],
            "TS_PCT": [0.62, 0.58, 0.48],
            "PTS_PER36": [28.0, 14.0, 25.0],
            "REB_PCT": [12.0, 8.0, 6.0],
            "AST_PCT": [30.0, 15.0, 10.0],
            "STL_PER36": [1.5, 1.0, 0.8],
            "BLK_PER36": [0.8, 0.5, 0.2],
            "TOV_PCT": [10.0, 9.0, 15.0],
            "USG_PCT": [30.0, 18.0, 32.0],
            "PIE": [15.0, 9.0, 10.0],
        }
    )


def test_filter_qualified_drops_low_minutes_and_games():
    df = pd.DataFrame(
        {
            "player": ["Qualified", "Too Few Minutes", "Too Few Games"],
            "MIN": [1000, 100, 900],
            "GP": [50, 40, 10],
        }
    )
    qualified = filter_qualified(df, min_minutes=500, min_games=20)
    assert list(qualified["player"]) == ["Qualified"]


def test_production_score_is_bounded_0_to_100():
    df = _make_stats_df()
    scored = compute_production_score(df, WEIGHTS)
    assert scored["production_score"].between(0, 100).all()


def test_production_score_rewards_efficiency_over_inefficient_volume():
    df = _make_stats_df()
    scored = compute_production_score(df, WEIGHTS).set_index("player")
    # The efficient star should outscore the high-volume, low-efficiency,
    # low-playmaking scorer despite the volume scorer having more raw points.
    assert scored.loc["Star", "production_score"] > scored.loc[
        "Inefficient Volume Scorer", "production_score"
    ]


def test_production_score_requires_all_input_columns():
    df = _make_stats_df().drop(columns=["TS_PCT"])
    with pytest.raises(ValueError, match="Missing required stat columns"):
        compute_production_score(df, WEIGHTS)


def test_production_score_requires_weights_sum_to_one():
    df = _make_stats_df()
    bad_weights = dict(WEIGHTS)
    bad_weights["ts_pct"] = 0.99  # now sums well over 1.0
    with pytest.raises(ValueError, match="must sum to 1.0"):
        compute_production_score(df, bad_weights)
