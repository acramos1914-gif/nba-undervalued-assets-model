"""CLI orchestrator: fetch -> reconcile -> score -> benchmark -> report.

Usage:
    python -m src.pipeline run
    python -m src.pipeline run --skip-fetch   # reuse existing data/raw/*.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.fetch_salaries import fetch_salaries  # noqa: E402
from data.fetch_stats import fetch_player_stats  # noqa: E402
from src import benchmark, production_score, report, value_model  # noqa: E402
from src.reconcile import reconcile_players  # noqa: E402

RAW_DIR = ROOT / "data" / "raw"
STATS_CSV = RAW_DIR / "player_stats.csv"
SALARIES_CSV = RAW_DIR / "salaries.csv"
REPORTS_DIR = ROOT / "reports"
RECONCILIATION_REPORT = REPORTS_DIR / "reconciliation_report.md"
BENCHMARK_JSON = REPORTS_DIR / "benchmark_correlations.json"


@click.group()
def cli() -> None:
    """NBA Undervalued Assets Model pipeline."""


@cli.command()
@click.option("--skip-fetch", is_flag=True, help="Reuse existing data/raw/*.csv instead of hitting live APIs.")
@click.option("--config-path", default=str(ROOT / "config.yaml"), help="Path to config.yaml")
def run(skip_fetch: bool, config_path: str) -> None:
    """Run the full pipeline end to end."""
    config = production_score.load_config(Path(config_path))
    season = config["season"]["stats_season"]
    salary_year_column = config["season"]["salary_year_column"]
    advanced_season_end_year = config["season"]["advanced_season_end_year"]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # --- 1. Fetch ---
    if skip_fetch and STATS_CSV.exists():
        click.echo(f"[1/5] Skipping stats fetch, reusing {STATS_CSV}")
        stats_df = pd.read_csv(STATS_CSV)
    else:
        click.echo(f"[1/5] Fetching player stats for {season}...")
        stats_df = fetch_player_stats(season)
        stats_df.to_csv(STATS_CSV, index=False)

    if skip_fetch and SALARIES_CSV.exists():
        click.echo(f"      Skipping salary fetch, reusing {SALARIES_CSV}")
        salary_df = pd.read_csv(SALARIES_CSV)
    else:
        click.echo(f"      Fetching salaries ({salary_year_column} cap hits)...")
        salary_df = fetch_salaries(salary_year_column)
        salary_df.to_csv(SALARIES_CSV, index=False)

    # --- 2. Reconcile ---
    click.echo("[2/5] Reconciling players across stats and salary sources...")
    reconciliation = reconcile_players(stats_df, salary_df)
    reconciliation.write_report(str(RECONCILIATION_REPORT))
    click.echo(
        f"      Matched {len(reconciliation.merged)} players | "
        f"{len(reconciliation.unmatched_stats)} unmatched from stats | "
        f"{len(reconciliation.unmatched_salaries)} unmatched from salaries "
        f"(see {RECONCILIATION_REPORT})"
    )

    # --- 3. Score ---
    click.echo("[3/5] Computing Production Score and Value Score...")
    scored_df = production_score.run(reconciliation.merged, config)
    valued_df = value_model.compute_value_score(scored_df)
    click.echo(f"      Scored {len(valued_df)} qualified players.")

    # --- 4. Benchmark ---
    click.echo("[4/5] Benchmarking Production Score against WS/48, BPM, VORP...")
    benchmark_merged = None
    correlations = None
    try:
        benchmark_merged, correlations = benchmark.run(valued_df, advanced_season_end_year)
        with open(BENCHMARK_JSON, "w", encoding="utf-8") as fh:
            json.dump(correlations, fh, indent=2)
        for metric, stats in correlations.items():
            click.echo(f"      {metric}: r={stats['pearson_r']:.3f} (n={stats['n']})")
    except RuntimeError as exc:
        click.echo(f"      [warn] benchmark step failed: {exc}", err=True)

    # --- 5. Report ---
    click.echo("[5/5] Writing leaderboard and chart...")
    top_n = config["output"]["top_n"]
    bottom_n = config["output"]["bottom_n"]
    leaderboard = report.generate_report(
        valued_df,
        top_n=top_n,
        bottom_n=bottom_n,
        benchmark_df=benchmark_merged,
        benchmark_correlations=correlations,
    )
    click.echo(f"      Wrote {len(leaderboard)}-row leaderboard to {report.LEADERBOARD_CSV}")
    click.echo(f"      Wrote charts to {report.REPORTS_DIR}")

    click.echo("\nTop 5 most undervalued:")
    click.echo(leaderboard.head(5).to_string(index=False))
    click.echo("\nBottom 5 most overpaid:")
    click.echo(leaderboard.tail(5).to_string(index=False))


if __name__ == "__main__":
    cli()
