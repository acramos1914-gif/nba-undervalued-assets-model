"""Benchmark the Production Score against established all-in-one metrics.

The Production Score is built entirely from stats.nba.com per-36 and
advanced/percentage stats. To check it isn't just an arbitrary weighted sum
that happens to look reasonable, we correlate it against three independent,
widely-used Basketball-Reference metrics it shares *no* inputs with:

  - Win Shares per 48 minutes (WS/48): a rate stat estimating a player's
    contribution to team wins per 48 minutes, built from a completely
    different formula (marginal offense/defense vs. league average).
  - Box Plus/Minus (BPM): a per-100-possessions estimate of a player's
    contribution relative to league average, from a box-score regression
    trained against play-by-play plus/minus data.
  - Value Over Replacement Player (VORP): BPM scaled by the share of team
    minutes played and translated to a "wins" scale -- the one benchmark
    metric here that is *not* purely rate-based (deliberately: this checks
    whether the composite's role-normalization approach still tracks a
    metric that partly rewards durability/minutes share, not just quality
    of play per minute).

Source: Basketball-Reference "Advanced" table, redistributed as CSV by the
sumitrodatta/bball-reference-datasets GitHub project (an actively
maintained scrape-to-CSV mirror of Basketball-Reference's season-by-season
tables). See README for the exact URL and season mapping.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import requests

from src.reconcile import dedupe_traded_players, normalize_name

ADVANCED_CSV_URL = (
    "https://raw.githubusercontent.com/sumitrodatta/"
    "bball-reference-datasets/master/Data/Advanced.csv"
)
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CACHE_PATH = RAW_DIR / "advanced_benchmark.csv"

BENCHMARK_METRICS = ["ws_48", "bpm", "vorp"]


def fetch_advanced_benchmark(season_end_year: int, timeout: int = 30) -> pd.DataFrame:
    """Download (or reuse a cached copy of) the Basketball-Reference Advanced table."""
    try:
        resp = requests.get(ADVANCED_CSV_URL, timeout=timeout)
        resp.raise_for_status()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_bytes(resp.content)
    except requests.RequestException as exc:
        if CACHE_PATH.exists():
            print(
                f"  [warn] live fetch of benchmark data failed ({exc}); "
                f"using cached copy at {CACHE_PATH}",
                file=sys.stderr,
            )
        else:
            raise RuntimeError(
                f"Failed to fetch benchmark advanced stats from {ADVANCED_CSV_URL} "
                f"and no cached copy exists at {CACHE_PATH}: {exc}"
            ) from exc

    df = pd.read_csv(CACHE_PATH)
    season_df = df[df["season"] == season_end_year].copy()
    if season_df.empty:
        raise RuntimeError(
            f"No rows found for season_end_year={season_end_year} in the benchmark "
            "advanced stats file. The source data may not have been updated yet "
            "for the season this pipeline is scoring."
        )
    return season_df.rename(columns={"player": "player", "team": "team"})


def correlate_with_benchmark(
    scored_df: pd.DataFrame, benchmark_df: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    """Merge scored players onto benchmark metrics and compute correlations.

    Returns the merged frame (for spot-checking) and a dict of
    {metric: {"pearson_r": ..., "n": ...}} for each of BENCHMARK_METRICS.
    """
    benchmark_df = dedupe_traded_players(benchmark_df, name_col="player", team_col="team")
    benchmark_df = benchmark_df.copy()
    benchmark_df["_name_key"] = benchmark_df["player"].map(normalize_name)
    benchmark_df = benchmark_df.drop_duplicates("_name_key", keep="first")

    scored_df = scored_df.copy()
    scored_df["_name_key"] = scored_df["player"].map(normalize_name)

    merged = scored_df.merge(
        benchmark_df[["_name_key", "ws", "ws_48", "bpm", "vorp"]],
        on="_name_key",
        how="inner",
    ).drop(columns="_name_key")

    results: dict[str, dict[str, float]] = {}
    for metric in BENCHMARK_METRICS:
        pair = merged[["production_score", metric]].dropna()
        r = pair["production_score"].corr(pair[metric], method="pearson")
        results[metric] = {"pearson_r": float(r), "n": int(len(pair))}

    return merged, results


def run(scored_df: pd.DataFrame, season_end_year: int) -> tuple[pd.DataFrame, dict]:
    benchmark_df = fetch_advanced_benchmark(season_end_year)
    return correlate_with_benchmark(scored_df, benchmark_df)
