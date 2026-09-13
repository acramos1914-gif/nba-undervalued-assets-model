"""Generate the final ranked leaderboard: CSV + a top/bottom value chart."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe backend for CI/servers
import matplotlib.pyplot as plt
import pandas as pd

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
LEADERBOARD_CSV = REPORTS_DIR / "leaderboard.csv"
CHART_PNG = REPORTS_DIR / "value_chart.png"

LEADERBOARD_COLS = [
    "player",
    "team",
    "cap_hit",
    "production_score",
    "value_score",
    "value_ratio",
]


def build_leaderboard(df: pd.DataFrame) -> pd.DataFrame:
    """Return the full ranked leaderboard sorted by value_score descending."""
    leaderboard = df[LEADERBOARD_COLS].copy()
    leaderboard = leaderboard.sort_values("value_score", ascending=False).reset_index(drop=True)
    leaderboard.insert(0, "rank", leaderboard.index + 1)
    return leaderboard


def plot_top_bottom(leaderboard: pd.DataFrame, top_n: int, bottom_n: int, out_path: Path) -> None:
    """Horizontal bar chart: most undervalued (top) vs. most overpaid (bottom)."""
    top = leaderboard.head(top_n).copy()
    bottom = leaderboard.tail(bottom_n).copy()

    top["group"] = "Most undervalued"
    bottom["group"] = "Most overpaid"
    combined = pd.concat([top, bottom]).iloc[::-1]  # reverse so top-of-chart = best

    colors = combined["group"].map({"Most undervalued": "#2a9d8f", "Most overpaid": "#e76f51"})

    fig, ax = plt.subplots(figsize=(9, max(6, 0.35 * len(combined))))
    labels = combined["player"] + " (" + combined["team"] + ")"
    ax.barh(labels, combined["value_score"], color=colors)
    ax.set_xlabel("Value Score (0-100 percentile of Production Score per $M cap hit)")
    ax.set_title(f"Top {top_n} Most Undervalued vs. Bottom {bottom_n} Most Overpaid Contracts")
    ax.axvline(50, color="grey", linewidth=0.8, linestyle="--")

    handles = [
        plt.Rectangle((0, 0), 1, 1, color="#2a9d8f"),
        plt.Rectangle((0, 0), 1, 1, color="#e76f51"),
    ]
    ax.legend(handles, ["Most undervalued", "Most overpaid"], loc="lower right")
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def generate_report(
    df: pd.DataFrame,
    top_n: int = 15,
    bottom_n: int = 15,
    csv_path: Path = LEADERBOARD_CSV,
    chart_path: Path = CHART_PNG,
) -> pd.DataFrame:
    leaderboard = build_leaderboard(df)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(csv_path, index=False)

    plot_top_bottom(leaderboard, top_n, bottom_n, chart_path)

    return leaderboard
