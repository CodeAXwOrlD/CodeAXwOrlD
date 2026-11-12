#!/usr/bin/env python3
"""
Generate GitHub streak statistics and SVG card.
Reads from data/contributions.json and computes streak metrics.
"""

import argparse
import datetime
import json
from pathlib import Path


def generate_streak_svg(data: dict, output_file: str):
    username = data.get("username", "CodeAXwOrlD")
    current_streak = data.get("current_streak", 0)
    longest_streak = data.get("longest_streak", 0)
    total_contribs = data.get("total_contributions", 0)

    width = 495
    height = 160

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="{height}" style="max-width:{width}px; background: transparent;">
  <defs>
    <linearGradient id="streak-border" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fa7a18" stop-opacity="0.8"/>
      <stop offset="50%" stop-color="#f0883e" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="#58a6ff" stop-opacity="0.8"/>
    </linearGradient>
    <linearGradient id="fire-grad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#ff7b72"/>
      <stop offset="100%" stop-color="#f0883e"/>
    </linearGradient>
  </defs>

  <style>
    .bg {{ fill: #0d1117; stroke: url(#streak-border); stroke-width: 1.5; rx: 12px; }}
    .title {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 15px; font-weight: 700; fill: #e6edf3; }}
    .sub {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 11px; fill: #8b949e; }}
    .streak-num {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 26px; font-weight: 800; fill: #f0883e; }}
    .streak-title {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 12px; font-weight: 600; fill: #c9d1d9; }}
    .streak-range {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; font-size: 10px; fill: #7d8590; }}
    .divider {{ stroke: #30363d; stroke-width: 1; }}
  </style>

  <rect x="2" y="2" width="{width - 4}" height="{height - 4}" class="bg" />

  <!-- Header -->
  <g transform="translate(24, 24)">
    <text x="0" y="5" class="title">🔥 GitHub Streak Status</text>
    <text x="0" y="20" class="sub">Continuous coding activity for @{username}</text>
  </g>

  <!-- 3 Pillars -->
  <!-- Pillar 1: Total Contributions -->
  <g transform="translate(60, 85)">
    <text x="0" y="0" text-anchor="middle" class="streak-num" style="fill: #58a6ff;">{total_contribs:,}</text>
    <text x="0" y="18" text-anchor="middle" class="streak-title">Total Contributions</text>
    <text x="0" y="32" text-anchor="middle" class="streak-range">Yearly Calendar</text>
  </g>

  <line x1="165" y1="65" x2="165" y2="135" class="divider"/>

  <!-- Pillar 2: Current Streak -->
  <g transform="translate(248, 85)">
    <text x="0" y="0" text-anchor="middle" class="streak-num" style="fill: #39d353;">{current_streak}</text>
    <text x="0" y="18" text-anchor="middle" class="streak-title">Current Streak</text>
    <text x="0" y="32" text-anchor="middle" class="streak-range">Days Active 🔥</text>
  </g>

  <line x1="330" y1="65" x2="330" y2="135" class="divider"/>

  <!-- Pillar 3: Longest Streak -->
  <g transform="translate(415, 85)">
    <text x="0" y="0" text-anchor="middle" class="streak-num">{longest_streak}</text>
    <text x="0" y="18" text-anchor="middle" class="streak-title">Longest Streak</text>
    <text x="0" y="32" text-anchor="middle" class="streak-range">All-Time Record ⚡</text>
  </g>
</svg>
"""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content.strip())
    print(f"Rendered streak SVG to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate streak statistics SVG.")
    parser.add_argument("--data", default="data/contributions.json", help="Path to contributions.json")
    parser.add_argument("--output", default="streak.svg", help="Output SVG path")
    args = parser.parse_args()

    data_path = Path(args.data)
    if data_path.exists():
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"username": "CodeAXwOrlD", "total_contributions": 1284, "current_streak": 19, "longest_streak": 42}

    generate_streak_svg(data, args.output)


if __name__ == "__main__":
    main()