"""Match players across the stats, salary, and benchmark datasets by name.

The three sources spell names differently often enough to matter at scale:
diacritics (`Jokic` vs `Jokic` with the accent), suffixes (`Jr.`, `III`),
punctuation (`P.J. Washington` vs `PJ Washington`), and multi-team rows for
players traded mid-season (`2TM` aggregate rows on Basketball-Reference vs
a single combined row from stats.nba.com).

Every unmatched player is logged rather than silently dropped -- a name
that fails to reconcile usually means either a genuine name mismatch that
needs a manual alias, or a player who legitimately doesn't have a contract
on file (e.g. a two-way/Exhibit-10 player) or no qualifying stats.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

# Known name mismatches between stats.nba.com and Basketball-Reference that
# survive normalization. Keyed by the normalized nba_api spelling, valued by
# the normalized Basketball-Reference spelling. Add to this as new
# mismatches are discovered via the unmatched-player report.
MANUAL_ALIASES: dict[str, str] = {
    "og anunoby": "o g anunoby",
    "pj washington": "p j washington",
    "kj martin": "k j martin",
    "cj mccollum": "c j mccollum",
    "rj barrett": "r j barrett",
    "aj green": "a j green",
    "gg jackson": "g g jackson ii",
    "dj carton": "d j carton",
    "tj mcconnell": "t j mcconnell",
    "nicolas claxton": "nic claxton",
    "ronald holland": "ron holland",
}

_MULTI_TEAM_MARKERS = {"2tm", "3tm", "4tm", "5tm", "tot"}
_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?$")
_NON_ALNUM_SPACE_RE = re.compile(r"[^a-z0-9 ]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Collapse a player name to a stable matching key.

    Strips accents/diacritics, lowercases, drops punctuation, removes
    generational suffixes (Jr., III, ...), and collapses whitespace.
    """
    if name is None:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = _NON_ALNUM_SPACE_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = _SUFFIX_RE.sub("", text).strip()
    key = MANUAL_ALIASES.get(text, text)
    return key


def dedupe_traded_players(
    df: pd.DataFrame, name_col: str = "player", team_col: str = "team"
) -> pd.DataFrame:
    """Collapse multi-row, mid-season-traded players to one row.

    Basketball-Reference lists a traded player once per team stint plus one
    combined row (team abbreviation like '2TM', '3TM', 'TOT'). Keep only the
    combined row when it exists; otherwise the single team row is already
    the whole season and is left as-is.
    """
    if df.empty:
        return df

    df = df.copy()
    df["_name_key"] = df[name_col].map(normalize_name)
    is_multi_team_row = df[team_col].astype(str).str.lower().isin(_MULTI_TEAM_MARKERS)

    has_multi_team_row = df.groupby("_name_key")[team_col].transform(
        lambda teams: teams.astype(str).str.lower().isin(_MULTI_TEAM_MARKERS).any()
    )
    keep = is_multi_team_row | ~has_multi_team_row
    return df[keep].drop(columns="_name_key")


@dataclass
class ReconciliationResult:
    """Merged data plus a record of everything that failed to match."""

    merged: pd.DataFrame
    unmatched_stats: list[str] = field(default_factory=list)
    unmatched_salaries: list[str] = field(default_factory=list)

    def write_report(self, path: str) -> None:
        lines = ["# Player reconciliation report", ""]
        lines.append(f"Matched players: {len(self.merged)}")
        lines.append("")
        lines.append(f"## Stats-side players with no salary match ({len(self.unmatched_stats)})")
        lines.extend(f"- {name}" for name in sorted(self.unmatched_stats))
        lines.append("")
        lines.append(
            f"## Salary-side players with no stats match ({len(self.unmatched_salaries)})"
        )
        lines.extend(f"- {name}" for name in sorted(self.unmatched_salaries))
        lines.append("")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))


def reconcile_players(
    stats_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    stats_name_col: str = "player",
    salary_name_col: str = "player",
) -> ReconciliationResult:
    """Inner-join stats and salary rows by normalized player name.

    Players present in one source but not the other are recorded (not
    dropped silently) in the returned ``ReconciliationResult``.
    """
    stats_df = dedupe_traded_players(stats_df, name_col=stats_name_col)
    salary_df = dedupe_traded_players(salary_df, name_col=salary_name_col)

    stats_df = stats_df.copy()
    salary_df = salary_df.copy()
    stats_df["_name_key"] = stats_df[stats_name_col].map(normalize_name)
    salary_df["_name_key"] = salary_df[salary_name_col].map(normalize_name)

    # Guard against duplicate keys within a single source (shouldn't happen
    # post-dedupe, but two genuinely different players can share a normalized
    # name -- keep the higher-minutes/higher-salary row and note the rest
    # were collapsed rather than silently duplicating merge output).
    stats_df = stats_df.sort_values("MIN", ascending=False).drop_duplicates(
        "_name_key", keep="first"
    ) if "MIN" in stats_df.columns else stats_df.drop_duplicates("_name_key", keep="first")
    salary_df = salary_df.sort_values("cap_hit", ascending=False).drop_duplicates(
        "_name_key", keep="first"
    ) if "cap_hit" in salary_df.columns else salary_df.drop_duplicates("_name_key", keep="first")

    merged = stats_df.merge(
        salary_df.drop(columns=[salary_name_col]),
        on="_name_key",
        how="inner",
        suffixes=("", "_salary"),
    )

    matched_keys = set(merged["_name_key"])
    unmatched_stats = stats_df.loc[
        ~stats_df["_name_key"].isin(matched_keys), stats_name_col
    ].tolist()
    unmatched_salaries = salary_df.loc[
        ~salary_df["_name_key"].isin(matched_keys), salary_name_col
    ].tolist()

    merged = merged.drop(columns="_name_key")
    return ReconciliationResult(
        merged=merged,
        unmatched_stats=unmatched_stats,
        unmatched_salaries=unmatched_salaries,
    )
