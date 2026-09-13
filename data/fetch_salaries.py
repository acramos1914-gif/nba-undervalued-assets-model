"""Pull current NBA player salary/cap data from Basketball-Reference.

Source: https://www.basketball-reference.com/contracts/players.html
Basketball-Reference publishes this table on a rolling basis throughout the
season (it credits Spotrac as the original compiler of contract terms) and
lists every player currently under an NBA contract, with salary figures for
the current and each future contract year plus a guaranteed-money total.

We use it instead of scraping a dedicated contract-tracking site (Spotrac,
HoopsHype, etc.) directly: it is a single, low-request-volume, well
structured table on a general sports-reference site the project already
pulls from for the benchmark advanced stats, rather than a bespoke scrape
of a commercial salary site.

We take the earliest not-yet-started contract year as "current cap hit."
As of this writing that is the 2026-27 column, because the pipeline scores
just-completed 2025-26 production against the salary the player is
currently committed to for the season about to start -- both numbers are
settled, and it answers "is this player's current paycheck justified by
what he just did on the floor?"

Output: data/raw/salaries.csv
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parent / "raw"
OUTPUT_PATH = RAW_DIR / "salaries.csv"
CONTRACTS_URL = "https://www.basketball-reference.com/contracts/players.html"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "nba-undervalued-assets-model/1.0 (portfolio project; polite single-request fetch)"
)


def _fetch_html(url: str, max_retries: int = 3, timeout: int = 20) -> str:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            return resp.text
        except requests.RequestException as exc:
            last_error = exc
            wait = 2 * attempt
            print(
                f"  [warn] fetch failed (attempt {attempt}/{max_retries}): {exc}. "
                f"Retrying in {wait}s...",
                file=sys.stderr,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"Failed to fetch {url} after {max_retries} attempts. "
        "Basketball-Reference may be rate-limiting this host, or the page "
        f"structure changed. Last error: {last_error!r}"
    ) from last_error


def _money_to_float(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text in {"-", "nan"}:
        return None
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fetch_salaries(salary_year_column: str = "2026-27") -> pd.DataFrame:
    """Fetch and parse the Basketball-Reference contracts table."""
    print(f"Fetching contracts table from {CONTRACTS_URL} ...")
    html = _fetch_html(CONTRACTS_URL)

    tables = pd.read_html(StringIO(html))
    if not tables:
        raise RuntimeError(
            "No tables found on the Basketball-Reference contracts page. "
            "The page structure may have changed."
        )
    raw = tables[0]

    # The table has a two-level header (season years span a "Salary" group);
    # flatten it to plain column names we control.
    salary_year_cols = [c for c in raw.columns if isinstance(c, tuple) and c[0] == "Salary"]
    year_labels = [c[1] for c in salary_year_cols]

    flat_cols = []
    for col in raw.columns:
        if isinstance(col, tuple):
            flat_cols.append(col[1])
        else:
            flat_cols.append(col)
    raw.columns = flat_cols

    if salary_year_column not in year_labels:
        raise RuntimeError(
            f"Expected salary year column '{salary_year_column}' not found on the "
            f"contracts page. Available year columns: {year_labels}. "
            "Update config.yaml's season.salary_year_column to match."
        )

    df = raw[raw["Player"] != "Player"].copy()  # drop repeated header rows
    df = df.rename(
        columns={
            "Player": "player",
            "Tm": "team",
            salary_year_column: "cap_hit_raw",
            "Guaranteed": "guaranteed_raw",
        }
    )
    df["cap_hit"] = df["cap_hit_raw"].apply(_money_to_float)
    df["guaranteed"] = df["guaranteed_raw"].apply(_money_to_float)

    before = len(df)
    df = df.dropna(subset=["player", "cap_hit"])
    dropped = before - len(df)
    if dropped:
        print(
            f"  [info] dropped {dropped} rows with no {salary_year_column} salary "
            "figure (contract already expired, two-way/non-guaranteed slot with no "
            "listed number, etc.)"
        )

    df = df[["player", "team", "cap_hit", "guaranteed"]].reset_index(drop=True)
    df["salary_year"] = salary_year_column
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--salary-year-column",
        default="2026-27",
        help="Which contract-year column to treat as the current cap hit (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help="Output CSV path (default: %(default)s)",
    )
    args = parser.parse_args()

    try:
        df = fetch_salaries(args.salary_year_column)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} salary rows to {out_path}")


if __name__ == "__main__":
    main()
