"""Pull current-season NBA player production stats via nba_api.

Combines three stats.nba.com pulls into a single per-player row:
  - Totals (Base):   real total MIN and GP, used only for the minutes/games
                      qualification filter (rate stats below already
                      normalize for playing time, so raw totals must not
                      leak into the score itself).
  - Per36 (Base):     role-normalized counting stats (PTS, REB, AST, STL,
                      BLK, TOV per 36 minutes).
  - Advanced (PerGame): efficiency/impact rates (TS%, USG%, AST%, REB%,
                      team TOV%, PIE) that are already possession- or
                      minute-share normalized by stats.nba.com.

Output: data/raw/player_stats.csv
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent / "raw"
OUTPUT_PATH = RAW_DIR / "player_stats.csv"

ID_COLS = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"]

TOTALS_COLS = ID_COLS + ["GP", "MIN"]
PER36_COLS = ID_COLS + ["PTS", "REB", "AST", "STL", "BLK", "TOV"]
ADVANCED_COLS = ID_COLS + [
    "TS_PCT",
    "USG_PCT",
    "AST_PCT",
    "REB_PCT",
    "TM_TOV_PCT",
    "PIE",
    "NET_RATING",
]

PER36_RENAME = {
    "PTS": "PTS_PER36",
    "REB": "REB_PER36",
    "AST": "AST_PER36",
    "STL": "STL_PER36",
    "BLK": "BLK_PER36",
    "TOV": "TOV_PER36",
}
ADVANCED_RENAME = {"TM_TOV_PCT": "TOV_PCT"}


def _pull(
    season: str,
    per_mode: str,
    measure_type: str,
    max_retries: int = 3,
    timeout: int = 60,
) -> pd.DataFrame:
    """Call LeagueDashPlayerStats with retries and a clear failure message."""
    from nba_api.stats.endpoints import leaguedashplayerstats

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                season_type_all_star="Regular Season",
                per_mode_detailed=per_mode,
                measure_type_detailed_defense=measure_type,
                timeout=timeout,
            )
            return resp.get_data_frames()[0]
        except Exception as exc:  # nba_api raises plain Exception on bad JSON/timeouts
            last_error = exc
            wait = 2 * attempt
            print(
                f"  [warn] {measure_type}/{per_mode} pull failed "
                f"(attempt {attempt}/{max_retries}): {exc}. Retrying in {wait}s...",
                file=sys.stderr,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"Failed to fetch {measure_type}/{per_mode} stats for season {season} "
        f"from stats.nba.com after {max_retries} attempts. "
        "This usually means the NBA stats API is rate-limiting or blocking this "
        "IP/host, or the season string is invalid. Last error: "
        f"{last_error!r}"
    ) from last_error


def fetch_player_stats(season: str) -> pd.DataFrame:
    """Fetch and merge Totals/Per36/Advanced pulls for one season."""
    print(f"Fetching Totals (Base) for {season}...")
    totals = _pull(season, "Totals", "Base")[TOTALS_COLS]

    print(f"Fetching Per36 (Base) for {season}...")
    per36 = _pull(season, "Per36", "Base")[PER36_COLS].rename(columns=PER36_RENAME)

    print(f"Fetching PerGame (Advanced) for {season}...")
    advanced = _pull(season, "PerGame", "Advanced")[ADVANCED_COLS].rename(columns=ADVANCED_RENAME)

    merged = totals.merge(
        per36.drop(columns=["PLAYER_NAME", "TEAM_ABBREVIATION"]),
        on="PLAYER_ID",
        how="inner",
    ).merge(
        advanced.drop(columns=["PLAYER_NAME", "TEAM_ABBREVIATION"]),
        on="PLAYER_ID",
        how="inner",
    )

    if len(merged) != len(totals):
        print(
            f"  [warn] merged row count ({len(merged)}) does not match Totals "
            f"row count ({len(totals)}); some players may be missing advanced "
            "or per-36 splits (usually due to 0-possession edge cases).",
            file=sys.stderr,
        )

    merged = merged.rename(columns={"PLAYER_NAME": "player", "TEAM_ABBREVIATION": "team"})
    merged["season"] = season
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--season",
        default="2025-26",
        help="nba_api season string, e.g. '2025-26' (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help="Output CSV path (default: %(default)s)",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df = fetch_player_stats(args.season)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} player rows to {out_path}")


if __name__ == "__main__":
    main()
