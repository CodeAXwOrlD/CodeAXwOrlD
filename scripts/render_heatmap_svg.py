#!/usr/bin/env python3
"""
Render an animated, dark-themed GitHub contribution heatmap SVG.
Fixes vertical alignment, eliminates header-month collision, ensures
all month labels (Jan-Dec) appear cleanly spaced, and animates cells
with a smooth diagonal cascade.
Reads from data/contributions.json and outputs to contrib-heatmap.svg.
"""

import argparse
import json
import sys
from pathlib import Path

COLOR_MAP = {
    "NONE": "#161b22",
    "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32",
    "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}

LEVEL_ORDER = ["NONE", "FIRST_QUARTILE", "SECOND_QUARTILE", "THIRD_QUARTILE", "FOURTH_QUARTILE"]


def get_cell_color(day: dict) -> str:
    level = day.get("contributionLevel", "NONE")
    if level in COLOR_MAP:
        return COLOR_MAP[level]
    count = day.get("contributionCount", 0)
    if count == 0:
        return COLOR_MAP["NONE"]
    elif count <= 2:
        return COLOR_MAP["FIRST_QUARTILE"]
    elif count <= 5:
        return COLOR_MAP["SECOND_QUARTILE"]
    elif count <= 8:
        return COLOR_MAP["THIRD_QUARTILE"]
    return COLOR_MAP["FOURTH_QUARTILE"]


def render_heatmap_svg(data: dict, output_file: str):
    weeks = data.get("weeks", [])
    total_contribs = data.get("total_contributions", 0)
    current_streak = data.get("current_streak", 0)
    longest_streak = data.get("longest_streak", 0)
    username = data.get("username", "CodeAXwOrlD")

    # Calculate active days
    active_days = sum(
        1 for w in weeks for d in w.get("contributionDays", []) if d.get("contributionCount", 0) > 0
    )

    # Grid geometry
    cell_size = 11
    cell_gap = 3
    left_margin = 42
    top_margin = 86  # Generous top margin to prevent ANY overlap with header
    corner_radius = 2.5

    num_weeks = max(len(weeks), 52)
    grid_width = num_weeks * (cell_size + cell_gap)
    width = grid_width + left_margin + 34
    height = 228

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="{height}" style="max-width:{width}px; background: transparent;">',
        '  <defs>',
        '    <linearGradient id="heat-border" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" stop-color="#388bfd" stop-opacity="0.8"/>',
        '      <stop offset="50%" stop-color="#238636" stop-opacity="0.6"/>',
        '      <stop offset="100%" stop-color="#8957e5" stop-opacity="0.8"/>',
        '    </linearGradient>',
        '  </defs>',
        '  <style>',
        '    .heat-bg { fill: #0d1117; stroke: url(#heat-border); stroke-width: 1.5; rx: 10px; }',
        '    .title { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; font-size: 14px; font-weight: 700; fill: #58a6ff; }',
        '    .subtitle { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11px; fill: #8b949e; }',
        '    .stat-badge { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; fill: #39d353; font-weight: 600; }',
        '    .label { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 9.5px; fill: #7d8590; }',
        '    .cell { rx: 2.5px; opacity: 0; animation: cellCascade 0.35s ease-out forwards; transform-origin: center; transform-box: fill-box; }',
        '    .cell:hover { stroke: #58a6ff; stroke-width: 1.5px; }',
        '    @keyframes cellCascade {',
        '      0% { opacity: 0; transform: scale(0.3); }',
        '      70% { opacity: 1; transform: scale(1.15); }',
        '      100% { opacity: 1; transform: scale(1); }',
        '    }',
        '    @media (prefers-reduced-motion: reduce) {',
        '      .cell { opacity: 1 !important; animation: none !important; }',
        '    }',
        '  </style>',
        f'  <rect width="{width - 4}" height="{height - 4}" x="2" y="2" class="heat-bg" />',
        # Cleanly positioned Header
        '  <g transform="translate(24, 26)">',
        f'    <text x="0" y="0" class="title">⚡ @{username} // Contribution Heatmap</text>',
        f'    <text x="0" y="20" class="subtitle"><tspan class="stat-badge">{total_contribs:,}</tspan> contributions in the last year • <tspan class="stat-badge">{active_days}</tspan> active days • Streak: <tspan class="stat-badge">{current_streak}d</tspan> (max <tspan class="stat-badge">{longest_streak}d</tspan>)</text>',
        '  </g>',
    ]

    # Weekday labels (Mon, Wed, Fri) aligned to cells
    days_labels = [("Mon", 1), ("Wed", 3), ("Fri", 5)]
    for name, day_idx in days_labels:
        y_pos = top_margin + day_idx * (cell_size + cell_gap) + 9
        svg_parts.append(f'  <text x="14" y="{y_pos}" class="label">{name}</text>')

    # Month labels calculation (positioned at y = 73, safely below header and above grid)
    last_month = None
    last_month_x = -100

    for w_idx, week in enumerate(weeks):
        days = week.get("contributionDays", [])
        if days:
            date_str = days[0].get("date", "")
            if date_str:
                try:
                    month_num = int(date_str.split("-")[1])
                    m_x = left_margin + w_idx * (cell_size + cell_gap)
                    # Ensure consecutive months have at least 32px separation
                    if month_num != last_month and (m_x - last_month_x >= 32) and w_idx < num_weeks - 2:
                        last_month = month_num
                        last_month_x = m_x
                        svg_parts.append(
                            f'  <text x="{m_x}" y="73" class="label">{month_names[month_num - 1]}</text>'
                        )
                except Exception:
                    pass

    # Contribution cells with diagonal cascading animation
    for w_idx, week in enumerate(weeks):
        x = left_margin + w_idx * (cell_size + cell_gap)
        for d_idx, day in enumerate(week.get("contributionDays", [])):
            y = top_margin + d_idx * (cell_size + cell_gap)
            color = get_cell_color(day)
            count = day.get("contributionCount", 0)
            date_val = day.get("date", "")
            diag_idx = w_idx + d_idx
            anim_delay = round(0.10 + diag_idx * 0.015, 3)
            title_text = f"{count} contributions on {date_val}"
            svg_parts.append(
                f'  <rect class="cell" x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="{color}" style="animation-delay: {anim_delay}s;">'
                f'<title>{title_text}</title></rect>'
            )

    # Footer / Legend cleanly placed at bottom right
    legend_y = height - 20
    legend_right = width - 34
    svg_parts.append(f'  <text x="{legend_right - 126}" y="{legend_y + 9}" class="label">Less</text>')

    for i, lvl in enumerate(LEVEL_ORDER):
        box_x = legend_right - 98 + i * (cell_size + 3)
        svg_parts.append(f'  <rect class="cell" x="{box_x}" y="{legend_y}" width="{cell_size}" height="{cell_size}" fill="{COLOR_MAP[lvl]}" style="animation-delay: 1.1s;" />')

    svg_parts.append(f'  <text x="{legend_right - 20}" y="{legend_y + 9}" class="label">More</text>')
    svg_parts.append('</svg>')

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_parts))

    print(f"Rendered aligned contribution heatmap to {output_path} ({width}x{height})")


def main():
    parser = argparse.ArgumentParser(description="Render animated contribution heatmap SVG.")
    parser.add_argument("--data", default="data/contributions.json", help="Path to contributions.json")
    parser.add_argument("--output", default="contrib-heatmap.svg", help="Output SVG path")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Error: {data_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    render_heatmap_svg(data, args.output)


if __name__ == "__main__":
    main()
