"""Generate the final ranked leaderboard, plus four supporting charts:

  - value_chart.png:        top/bottom-N horizontal bar chart
  - value_scatter.png:      whole-league Production Score vs. cap hit
  - benchmark_scatter.png:  Production Score vs. WS/48, BPM, VORP (visual
                             proof of the section-4 correlation numbers)
  - team_value.png:         average Value Score by team

Color choices are pinned to a validated diverging pair (blue = undervalued,
red = overpaid, gray = fair value at the value_score=50 midpoint) so a
color always means the same thing everywhere in the project: blue is never
"good defense" in one chart and "high usage" in another. Blue/red also
appear in the benchmark scatter as a single accent hue with no polarity
meaning attached, since a benchmark scatter has no over/underpaid axis.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe backend for CI/servers
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
LEADERBOARD_CSV = REPORTS_DIR / "leaderboard.csv"
CHART_PNG = REPORTS_DIR / "value_chart.png"
SCATTER_PNG = REPORTS_DIR / "value_scatter.png"
BENCHMARK_SCATTER_PNG = REPORTS_DIR / "benchmark_scatter.png"
TEAM_CHART_PNG = REPORTS_DIR / "team_value.png"

LEADERBOARD_COLS = [
    "player",
    "team",
    "cap_hit",
    "production_score",
    "value_score",
    "value_ratio",
]

# Validated palette (see the dataviz skill's references/palette.md). Diverging
# blue<->red around a neutral gray midpoint; chart chrome (ink/gridlines) from
# the same reference so every chart in the project shares one visual system.
BLUE = "#2a78d6"       # undervalued / diverging cold pole
RED = "#e34948"        # overpaid / diverging warm pole
NEUTRAL_MID = "#c3c2b7"  # value_score == 50 midpoint (kept visible on white, unlike the near-white ref midpoint)
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

DIVERGING_CMAP = LinearSegmentedColormap.from_list(
    "value_diverging", [RED, NEUTRAL_MID, BLUE], N=256
)


def _style_axes(ax: plt.Axes) -> None:
    """Shared chrome: recessive gridlines/spines, muted ticks."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(GRIDLINE)
    ax.tick_params(colors=MUTED_INK, labelsize=9)
    ax.xaxis.label.set_color(SECONDARY_INK)
    ax.yaxis.label.set_color(SECONDARY_INK)


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

    colors = combined["group"].map({"Most undervalued": BLUE, "Most overpaid": RED})

    fig, ax = plt.subplots(figsize=(9, max(6, 0.35 * len(combined))), facecolor=SURFACE)
    _style_axes(ax)
    labels = combined["player"] + " (" + combined["team"] + ")"
    ax.barh(labels, combined["value_score"], color=colors, height=0.7, zorder=3)
    ax.set_xlabel("Value Score (0-100 percentile of Production Score per $M cap hit)")
    ax.set_title(
        f"Top {top_n} Most Undervalued vs. Bottom {bottom_n} Most Overpaid Contracts",
        color=PRIMARY_INK,
        fontsize=13,
        loc="left",
    )
    ax.axvline(50, color=MUTED_INK, linewidth=1, linestyle="--", zorder=2)

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=BLUE),
        plt.Rectangle((0, 0), 1, 1, color=RED),
    ]
    legend = ax.legend(handles, ["Most undervalued", "Most overpaid"], loc="lower right", frameon=False)
    for text in legend.get_texts():
        text.set_color(SECONDARY_INK)
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_value_scatter(leaderboard: pd.DataFrame, out_path: Path) -> None:
    """Whole-league scatter: Production Score vs. cap hit, colored by Value Score.

    Cap hit uses a log axis -- salaries span roughly $1M to $65M, and a linear
    axis would crush every minimum-salary player into a single vertical sliver.
    Color is a diverging blue/red scale centered on value_score=50 ("fair
    value" for this league-year), so at a glance blue points sit above the
    market-price trend and red points sit below it.
    """
    df = leaderboard.copy()
    df["cap_hit_m"] = df["cap_hit"] / 1_000_000.0

    fig, ax = plt.subplots(figsize=(10, 7), facecolor=SURFACE)
    _style_axes(ax)
    ax.set_xscale("log")

    norm = TwoSlopeNorm(vmin=0, vcenter=50, vmax=100)
    scatter = ax.scatter(
        df["cap_hit_m"],
        df["production_score"],
        c=df["value_score"],
        cmap=DIVERGING_CMAP,
        norm=norm,
        s=36,
        alpha=0.85,
        edgecolors="white",
        linewidths=0.4,
        zorder=3,
    )

    cbar = fig.colorbar(scatter, ax=ax, pad=0.015)
    cbar.set_label("Value Score", color=SECONDARY_INK)
    cbar.ax.tick_params(colors=MUTED_INK, labelsize=8)
    cbar.outline.set_visible(False)

    # Direct-label a small, curated set of outliers rather than every point.
    highlight_names = set(
        list(df.sort_values("value_score", ascending=False).head(1)["player"])
        + list(df.sort_values("value_score", ascending=True).head(1)["player"])
        + list(df.sort_values("production_score", ascending=False).head(1)["player"])
    )
    cap_hit_median = df["cap_hit_m"].median()
    for _, row in df[df["player"].isin(highlight_names)].iterrows():
        near_right_edge = row["cap_hit_m"] > cap_hit_median
        ax.annotate(
            row["player"],
            (row["cap_hit_m"], row["production_score"]),
            textcoords="offset points",
            xytext=(-8, 6) if near_right_edge else (8, 6),
            ha="right" if near_right_edge else "left",
            fontsize=8.5,
            color=PRIMARY_INK,
        )

    ax.set_xlabel("2026-27 Cap Hit ($M, log scale)")
    ax.set_ylabel("Production Score")
    ax.set_title(
        "Production vs. Pay: the Whole Qualified League",
        color=PRIMARY_INK,
        fontsize=13,
        loc="left",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_benchmark_scatter(benchmark_df: pd.DataFrame, correlations: dict, out_path: Path) -> None:
    """Production Score vs. each of WS/48, BPM, VORP, with a fitted trend line.

    This is the visual counterpart of the correlation table in the README --
    a reader can see the same relationship the reported Pearson r summarizes,
    rather than taking the number on faith.
    """
    metrics = [
        ("ws_48", "Win Shares / 48 min"),
        ("bpm", "Box Plus/Minus"),
        ("vorp", "VORP"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor=SURFACE)

    for ax, (col, label) in zip(axes, metrics):
        pair = benchmark_df[["production_score", col]].dropna()
        _style_axes(ax)
        ax.scatter(
            pair["production_score"],
            pair[col],
            color=BLUE,
            s=22,
            alpha=0.55,
            edgecolors="none",
            zorder=3,
        )
        slope, intercept = np.polyfit(pair["production_score"], pair[col], 1)
        x_line = np.array([pair["production_score"].min(), pair["production_score"].max()])
        ax.plot(x_line, slope * x_line + intercept, color=SECONDARY_INK, linewidth=1.5, linestyle="--", zorder=4)

        r = correlations.get(col, {}).get("pearson_r")
        n = correlations.get(col, {}).get("n")
        if r is not None:
            ax.text(
                0.04,
                0.94,
                f"r = {r:.3f}  (n={n})",
                transform=ax.transAxes,
                fontsize=10,
                color=PRIMARY_INK,
                va="top",
            )

        ax.set_xlabel("Production Score")
        ax.set_ylabel(label)

    fig.suptitle(
        "Production Score vs. Independent Basketball-Reference Metrics",
        color=PRIMARY_INK,
        fontsize=13,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_team_value(leaderboard: pd.DataFrame, out_path: Path) -> None:
    """Average Value Score by team -- which front offices spend most efficiently."""
    team_avg = (
        leaderboard.groupby("team")["value_score"]
        .mean()
        .sort_values(ascending=False)
        .reset_index()
    )

    norm = TwoSlopeNorm(vmin=0, vcenter=50, vmax=100)
    colors = DIVERGING_CMAP(norm(team_avg["value_score"]))

    fig, ax = plt.subplots(figsize=(9, 10), facecolor=SURFACE)
    _style_axes(ax)
    ax.barh(team_avg["team"][::-1], team_avg["value_score"][::-1], color=colors[::-1], height=0.7, zorder=3)
    ax.axvline(50, color=MUTED_INK, linewidth=1, linestyle="--", zorder=2)
    ax.set_xlabel("Average Value Score (qualified roster players)")
    ax.set_title(
        "Team Payroll Efficiency: Average Value Score by Roster",
        color=PRIMARY_INK,
        fontsize=13,
        loc="left",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def generate_report(
    df: pd.DataFrame,
    top_n: int = 15,
    bottom_n: int = 15,
    csv_path: Path = LEADERBOARD_CSV,
    chart_path: Path = CHART_PNG,
    scatter_path: Path = SCATTER_PNG,
    team_chart_path: Path = TEAM_CHART_PNG,
    benchmark_df: pd.DataFrame | None = None,
    benchmark_correlations: dict | None = None,
    benchmark_chart_path: Path = BENCHMARK_SCATTER_PNG,
) -> pd.DataFrame:
    leaderboard = build_leaderboard(df)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    leaderboard.to_csv(csv_path, index=False)

    plot_top_bottom(leaderboard, top_n, bottom_n, chart_path)
    plot_value_scatter(leaderboard, scatter_path)
    plot_team_value(leaderboard, team_chart_path)

    if benchmark_df is not None and benchmark_correlations:
        plot_benchmark_scatter(benchmark_df, benchmark_correlations, benchmark_chart_path)

    return leaderboard
