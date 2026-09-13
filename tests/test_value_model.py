"""Tests for Value Score = Production Score per dollar of cap hit."""
import pandas as pd
import pytest

from src.value_model import compute_value_score


def _make_scored_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player": ["Cheap Star", "Fair Deal", "Overpaid Vet"],
            "production_score": [80.0, 60.0, 55.0],
            "cap_hit": [5_000_000, 25_000_000, 45_000_000],
        }
    )


def test_value_score_bounded_0_to_100():
    df = compute_value_score(_make_scored_df())
    assert df["value_score"].between(0, 100).all()


def test_value_score_ranks_cheap_high_production_as_best_value():
    df = compute_value_score(_make_scored_df()).set_index("player")
    assert df.loc["Cheap Star", "value_score"] > df.loc["Fair Deal", "value_score"]
    assert df.loc["Fair Deal", "value_score"] > df.loc["Overpaid Vet", "value_score"]


def test_value_score_output_sorted_descending():
    df = compute_value_score(_make_scored_df())
    assert list(df["player"]) == ["Cheap Star", "Fair Deal", "Overpaid Vet"]


def test_compute_value_score_requires_production_score_column():
    df = _make_scored_df().drop(columns=["production_score"])
    with pytest.raises(ValueError, match="production_score"):
        compute_value_score(df)


def test_compute_value_score_requires_cap_hit_column():
    df = _make_scored_df().drop(columns=["cap_hit"])
    with pytest.raises(ValueError, match="cap_hit"):
        compute_value_score(df)


def test_compute_value_score_rejects_non_positive_cap_hit():
    df = _make_scored_df()
    df.loc[0, "cap_hit"] = 0
    with pytest.raises(ValueError, match="positive"):
        compute_value_score(df)
