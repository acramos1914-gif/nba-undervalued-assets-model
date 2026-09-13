"""Tests for name normalization and cross-source player reconciliation.

All fixture data is synthetic and small -- no live API calls.
"""
import pandas as pd

from src.reconcile import (
    dedupe_traded_players,
    normalize_name,
    reconcile_players,
)


def test_normalize_name_strips_accents_and_case():
    assert normalize_name("Nikola Jokić") == "nikola jokic"
    assert normalize_name("LUKA DONCIC") == "luka doncic"


def test_normalize_name_strips_suffixes():
    assert normalize_name("Jaren Jackson Jr.") == "jaren jackson"
    assert normalize_name("Kevin Knox II") == "kevin knox"
    assert normalize_name("Tim Hardaway III") == "tim hardaway"


def test_normalize_name_handles_punctuation_aliases():
    # "P.J. Washington" style punctuation collapses to the same key as the
    # manual alias target used for the plain "PJ Washington" spelling.
    assert normalize_name("PJ Washington") == normalize_name("P.J. Washington")


def test_normalize_name_handles_nickname_alias():
    # Real mismatch found in production data: stats.nba.com lists
    # "Ronald Holland II" while Basketball-Reference lists "Ron Holland".
    assert normalize_name("Ronald Holland II") == normalize_name("Ron Holland")


def test_normalize_name_collapses_whitespace():
    assert normalize_name("  Jayson   Tatum ") == "jayson tatum"


def test_dedupe_traded_players_keeps_combined_row():
    df = pd.DataFrame(
        {
            "player": ["Ochai Agbaji", "Ochai Agbaji", "Ochai Agbaji", "Bam Adebayo"],
            "team": ["2TM", "TOR", "BRK", "MIA"],
            "ws": [1.8, 1.2, 0.6, 6.4],
        }
    )
    deduped = dedupe_traded_players(df)
    assert len(deduped) == 2
    agbaji_row = deduped[deduped["player"] == "Ochai Agbaji"].iloc[0]
    assert agbaji_row["team"] == "2TM"


def test_dedupe_traded_players_leaves_single_team_rows_alone():
    df = pd.DataFrame({"player": ["Bam Adebayo"], "team": ["MIA"], "ws": [6.4]})
    deduped = dedupe_traded_players(df)
    assert len(deduped) == 1
    assert deduped.iloc[0]["team"] == "MIA"


def test_reconcile_players_matches_across_sources():
    stats_df = pd.DataFrame(
        {
            "player": ["Nikola Jokić", "Jaren Jackson Jr.", "Bam Adebayo"],
            "team": ["DEN", "MEM", "MIA"],
            "MIN": [2500, 2200, 2400],
        }
    )
    salary_df = pd.DataFrame(
        {
            "player": ["Nikola Jokic", "Jaren Jackson", "Some Unmatched Guy"],
            "team": ["DEN", "MEM", "XXX"],
            "cap_hit": [59_000_000, 24_000_000, 5_000_000],
        }
    )

    result = reconcile_players(stats_df, salary_df)

    assert len(result.merged) == 2
    matched_names = set(result.merged["player"])
    assert matched_names == {"Nikola Jokić", "Jaren Jackson Jr."}

    assert result.unmatched_stats == ["Bam Adebayo"]
    assert result.unmatched_salaries == ["Some Unmatched Guy"]


def test_reconcile_players_no_silent_drops(tmp_path):
    stats_df = pd.DataFrame({"player": ["Player A"], "team": ["AAA"], "MIN": [1000]})
    salary_df = pd.DataFrame({"player": ["Player B"], "team": ["BBB"], "cap_hit": [1_000_000]})

    result = reconcile_players(stats_df, salary_df)
    assert result.merged.empty
    assert result.unmatched_stats == ["Player A"]
    assert result.unmatched_salaries == ["Player B"]

    report_path = tmp_path / "report.md"
    result.write_report(str(report_path))
    content = report_path.read_text(encoding="utf-8")
    assert "Player A" in content
    assert "Player B" in content
