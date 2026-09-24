#!/usr/bin/env python3
"""Generate a compact GitHub profile analytics SVG for shabbir-369.

The script uses GitHub GraphQL to read the contribution calendar and account
statistics, then renders a self-contained SVG for README.md.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from typing import Any

import requests

API_URL = "https://api.github.com/graphql"
USERNAME = os.getenv("USER_NAME", "shabbir-369")
TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("ACCESS_TOKEN")
OUT = os.getenv("OUTPUT", "assets/analytics.svg")

QUERY = r"""
query($login: String!) {
  user(login: $login) {
    login
    createdAt
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
      totalCount
      nodes {
        stargazerCount
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            color
            contributionLevel
          }
        }
      }
    }
  }
}
"""


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def github_data() -> dict[str, Any]:
    if not TOKEN:
        fail("GITHUB_TOKEN or ACCESS_TOKEN is required")
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    response = requests.post(API_URL, json={"query": QUERY, "variables": {"login": USERNAME}}, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        fail(str(payload["errors"]))
    return payload["data"]["user"]


def flatten_days(user: dict[str, Any]) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    for week in user["contributionsCollection"]["contributionCalendar"]["weeks"]:
        days.extend(week["contributionDays"])
    days.sort(key=lambda x: x["date"])
    return days


def streaks(days: list[dict[str, Any]]) -> tuple[int, int, str, str]:
    if not days:
        return 0, 0, "", ""

    active = {d["date"]: d["contributionCount"] for d in days}
    today = max(active)
    cursor = date.fromisoformat(today)

    current = 0
    while active.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor = cursor.fromordinal(cursor.toordinal() - 1)

    best = 0
    best_start = best_end = ""
    run = 0
    run_start = None
    for d in days:
        if d["contributionCount"] > 0:
            if run == 0:
                run_start = d["date"]
            run += 1
            if run > best:
                best = run
                best_start = run_start or d["date"]
                best_end = d["date"]
        else:
            run = 0
            run_start = None

    return current, best, best_start, best_end


def esc(value: Any) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fmt_number(n: int) -> str:
    return f"{n:,}"


def short_date(iso: str) -> str:
    if not iso:
        return "—"
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%b %d, %Y")


def level_color(level: str) -> str:
    # GitHub-like neutral palette; colors are embedded in the generated SVG.
    return {
        "NONE": "#161b22",
        "FIRST_QUARTILE": "#0e4429",
        "SECOND_QUARTILE": "#006d32",
        "THIRD_QUARTILE": "#26a641",
        "FOURTH_QUARTILE": "#39d353",
    }.get(level, "#161b22")


def build_svg(user: dict[str, Any]) -> str:
    days = flatten_days(user)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    total = calendar["totalContributions"]
    current, longest, longest_start, longest_end = streaks(days)
    repos = user["repositories"]["totalCount"]
    followers = user["followers"]["totalCount"]
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])

    # Last 52 weeks. GitHub returns 53 weeks around leap/calendar boundaries.
    recent = days[-364:]
    cells = []
    start_x, start_y = 48, 154
    cell, gap = 11, 3
    for idx, day in enumerate(recent):
        col = idx // 7
        row = idx % 7
        x = start_x + col * (cell + gap)
        y = start_y + row * (cell + gap)
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{level_color(day["contributionLevel"])}">'
            f'<title>{esc(day["date"])}: {day["contributionCount"]} contributions</title></rect>'
        )

    width = 920
    height = 270
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" rx="10" fill="#0d1117" stroke="#30363d"/>
  <text x="24" y="34" fill="#f0f6fc" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="17" font-weight="700">📊 Live GitHub Analytics &amp; Activity Dashboard</text>
  <line x1="24" y1="48" x2="896" y2="48" stroke="#30363d"/>

  <g font-family="Inter,Segoe UI,Arial,sans-serif" text-anchor="middle">
    <text x="170" y="96" fill="#58a6ff" font-size="25" font-weight="700">{fmt_number(total)}</text>
    <text x="170" y="119" fill="#f78166" font-size="12">Total Contributions</text>
    <text x="170" y="138" fill="#8b949e" font-size="10">Last 12 months</text>

    <text x="460" y="96" fill="#bc8cff" font-size="25" font-weight="700">{current}</text>
    <text x="460" y="119" fill="#bc8cff" font-size="12">Current Streak</text>
    <text x="460" y="138" fill="#8b949e" font-size="10">As of {esc(short_date(days[-1]["date"] if days else ""))}</text>

    <text x="750" y="96" fill="#58a6ff" font-size="25" font-weight="700">{longest}</text>
    <text x="750" y="119" fill="#f78166" font-size="12">Longest Streak</text>
    <text x="750" y="138" fill="#8b949e" font-size="10">{esc(short_date(longest_start))} – {esc(short_date(longest_end))}</text>
  </g>

  <line x1="307" y1="62" x2="307" y2="143" stroke="#484f58"/>
  <line x1="613" y1="62" x2="613" y2="143" stroke="#484f58"/>

  <text x="24" y="178" fill="#f0f6fc" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="12" font-weight="600">Contribution Matrix &amp; Activity Stream</text>
  <g>{''.join(cells)}</g>

  <g font-family="Inter,Segoe UI,Arial,sans-serif" font-size="10" fill="#8b949e">
    <text x="48" y="251">Public repos: {repos}</text>
    <text x="210" y="251">Followers: {followers}</text>
    <text x="360" y="251">Stars: {stars}</text>
    <text x="760" y="251">github.com/{esc(USERNAME)}</text>
  </g>
</svg>'''


def main() -> None:
    user = github_data()
    svg = build_svg(user)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Generated {OUT} for @{USERNAME}")


if __name__ == "__main__":
    main()
