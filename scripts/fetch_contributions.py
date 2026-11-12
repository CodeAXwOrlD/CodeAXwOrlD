#!/usr/bin/env python3
"""
Fetch GitHub contribution history and user statistics for CodeAXwOrlD.
Uses GitHub GraphQL API when GITHUB_TOKEN is available.
Calculates verified streaks, active days, and saves data to data/contributions.json.
Gracefully preserves existing valid data on network errors without fabricating metrics.
"""

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

GRAPHQL_QUERY = """
query($username: String!) {
  user(login: $username) {
    name
    login
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
            color
          }
        }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes {
        stargazerCount
      }
    }
  }
}
"""


def fetch_graphql(username: str, token: str) -> dict:
    if not requests:
        raise RuntimeError("The 'requests' package is required.")

    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "CodeAXwOrlD-Profile-Art-Updater",
    }
    response = requests.post(
        url,
        json={"query": GRAPHQL_QUERY, "variables": {"username": username}},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise ValueError(f"GraphQL Errors: {data['errors']}")
    return data["data"]["user"]


def calculate_streaks(weeks: list) -> tuple[int, int]:
    """Calculate current and longest contribution streaks in days."""
    days = []
    for week in weeks:
        for day in week.get("contributionDays", []):
            days.append((day.get("date"), day.get("contributionCount", 0)))

    if not days:
        return 0, 0

    days.sort(key=lambda d: d[0])

    longest = 0
    current = 0
    temp_streak = 0

    for _, count in days:
        if count > 0:
            temp_streak += 1
            if temp_streak > longest:
                longest = temp_streak
        else:
            temp_streak = 0

    # Current streak counts backwards from latest recorded day
    for _, count in reversed(days):
        if count > 0:
            current += 1
        elif current == 0:
            # Allow skipping today if today has no commits yet
            continue
        else:
            break

    return current, longest


def main():
    parser = argparse.ArgumentParser(description="Fetch GitHub contributions.")
    parser.add_argument("--username", default="CodeAXwOrlD", help="GitHub username")
    parser.add_argument("--output", default="data/contributions.json", help="Output JSON path")
    parser.add_argument("--token", default=None, help="GitHub Personal Access Token")
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if token and requests:
        try:
            print(f"Fetching contribution data for {args.username} via GraphQL...")
            user_data = fetch_graphql(args.username, token)
            collection = user_data.get("contributionsCollection", {})
            calendar = collection.get("contributionCalendar", {})
            weeks = calendar.get("weeks", [])
            total_contribs = calendar.get("totalContributions", 0)

            repo_nodes = user_data.get("repositories", {}).get("nodes", [])
            total_stars = sum(r.get("stargazerCount", 0) for r in repo_nodes)

            current_streak, longest_streak = calculate_streaks(weeks)

            result_data = {
                "username": args.username,
                "name": user_data.get("name") or args.username,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "total_contributions": total_contribs,
                "current_streak": current_streak,
                "longest_streak": longest_streak,
                "stats": {
                    "total_commits": collection.get("totalCommitContributions", 0),
                    "pull_requests": collection.get("totalPullRequestContributions", 0),
                    "issues": collection.get("totalIssueContributions", 0),
                    "code_reviews": collection.get("totalPullRequestReviewContributions", 0),
                    "stars_earned": total_stars,
                },
                "weeks": weeks,
            }

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result_data, f, indent=2)

            print(f"Successfully fetched and saved {total_contribs} contributions to {output_path}")
            return
        except Exception as e:
            print(f"GraphQL fetch failed: {e}.", file=sys.stderr)
            if output_path.exists():
                print(f"Preserving existing valid data in {output_path}.")
                return
            else:
                print("Error: No existing data file found to fall back to.", file=sys.stderr)
                sys.exit(1)
    else:
        if output_path.exists():
            print(f"No GITHUB_TOKEN provided. Preserving verified data in {output_path}.")
            return
        else:
            print(f"Error: {output_path} does not exist and no GITHUB_TOKEN was provided.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
