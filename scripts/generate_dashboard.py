#!/usr/bin/env python3
"""Generate a compact GitHub profile dashboard SVG.

Reads contribution data through GitHub GraphQL and recent public activity through
GitHub REST API, then writes a single self-contained SVG for the profile README.
"""
from __future__ import annotations

import html
import os
import sys
from datetime import datetime, timezone, date
from typing import Any

import requests

USERNAME = os.getenv("USER_NAME", "Shabbir-369")
TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("ACCESS_TOKEN", "")
OUTPUT = os.getenv("OUTPUT", "assets/github-dashboard.svg")
GRAPHQL_URL = "https://api.github.com/graphql"
REST_BASE = "https://api.github.com"

GRAPHQL_QUERY = r"""
query($login: String!) {
  user(login: $login) {
    login
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC) {
      totalCount
      nodes { stargazerCount }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
            contributionLevel
          }
        }
      }
    }
  }
}
"""

SESSION = requests.Session()
SESSION.headers.update({
    "Accept": "application/vnd.github+json",
    "User-Agent": "shabbir-369-profile-dashboard",
})
if TOKEN:
    SESSION.headers["Authorization"] = f"Bearer {TOKEN}"


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def get_graphql_user() -> dict[str, Any]:
    if not TOKEN:
        fail("GITHUB_TOKEN is required")
    response = SESSION.post(
        GRAPHQL_URL,
        json={"query": GRAPHQL_QUERY, "variables": {"login": USERNAME}},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        fail(str(payload["errors"]))
    user = payload.get("data", {}).get("user")
    if not user:
        fail(f"GitHub user @{USERNAME} was not found")
    return user


def get_public_events(limit: int = 5) -> list[dict[str, Any]]:
    response = SESSION.get(
        f"{REST_BASE}/users/{USERNAME}/events/public",
        params={"per_page": 30},
        timeout=30,
    )
    if response.status_code == 404:
        return []
    response.raise_for_status()
    events = response.json()
    return events[:limit]


def flatten_days(user: dict[str, Any]) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in weeks:
        days.extend(week["contributionDays"])
    days.sort(key=lambda item: item["date"])
    return days


def streaks(days: list[dict[str, Any]]) -> tuple[int, int, str, str]:
    if not days:
        return 0, 0, "", ""

    active = {d["date"]: int(d["contributionCount"]) for d in days}
    latest = date.fromisoformat(max(active))

    current = 0
    cursor = latest
    while active.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor = date.fromordinal(cursor.toordinal() - 1)

    longest = 0
    run = 0
    start = end = ""
    run_start = None
    for day in days:
        if int(day["contributionCount"]) > 0:
            if run == 0:
                run_start = day["date"]
            run += 1
            if run > longest:
                longest = run
                start = run_start or day["date"]
                end = day["date"]
        else:
            run = 0
            run_start = None
    return current, longest, start, end


def fmt_num(value: int) -> str:
    return f"{value:,}"


def fmt_date(value: str) -> str:
    if not value:
        return "—"
    return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")


def fmt_event_time(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%b %d, %Y")
    except Exception:
        return "recent"


def contribution_color(level: str) -> str:
    return {
        "NONE": "#161b22",
        "FIRST_QUARTILE": "#0e4429",
        "SECOND_QUARTILE": "#006d32",
        "THIRD_QUARTILE": "#26a641",
        "FOURTH_QUARTILE": "#39d353",
    }.get(level, "#161b22")


def event_description(event: dict[str, Any]) -> tuple[str, str]:
    etype = event.get("type", "Event")
    repo = event.get("repo", {}).get("name", "GitHub")
    payload = event.get("payload") or {}
    action = payload.get("action")

    if etype == "PushEvent":
        size = payload.get("size") or len(payload.get("commits") or []) or 1
        commits = payload.get("commits") or []
        subject = ""
        if commits:
            subject = str(commits[-1].get("message", "")).splitlines()[0][:58]
        text = f"pushed {size} commit{'s' if int(size) != 1 else ''} to {repo}"
        return text, subject
    if etype == "PullRequestEvent":
        pr = payload.get("pull_request") or {}
        title = str(pr.get("title", "")).strip()[:58]
        text = f"{action or 'updated'} pull request in {repo}"
        return text, title
    if etype == "IssuesEvent":
        issue = payload.get("issue") or {}
        title = str(issue.get("title", "")).strip()[:58]
        text = f"{action or 'updated'} issue in {repo}"
        return text, title
    if etype == "IssueCommentEvent":
        issue = payload.get("issue") or {}
        title = str(issue.get("title", "")).strip()[:58]
        return f"commented on an issue in {repo}", title
    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "item")
        return f"created a {ref_type} in {repo}", ""
    if etype == "DeleteEvent":
        ref_type = payload.get("ref_type", "item")
        return f"deleted a {ref_type} in {repo}", ""
    if etype == "ReleaseEvent":
        release = payload.get("release") or {}
        tag = release.get("tag_name", "release")
        return f"published {tag} in {repo}", ""
    if etype == "WatchEvent":
        return f"starred {repo}", ""
    if etype == "ForkEvent":
        return f"forked {repo}", ""
    if etype == "CommitCommentEvent":
        return f"commented on a commit in {repo}", ""
    if etype == "PublicEvent":
        return f"made {repo} public", ""
    return f"{etype.replace('Event', '')} in {repo}", ""


def event_icon(event_type: str) -> str:
    return {
        "PushEvent": "↗",
        "PullRequestEvent": "⑂",
        "IssuesEvent": "#",
        "IssueCommentEvent": "✎",
        "CreateEvent": "+",
        "DeleteEvent": "−",
        "ReleaseEvent": "R",
        "WatchEvent": "★",
        "ForkEvent": "⑂",
        "CommitCommentEvent": "C",
    }.get(event_type, "•")


def build_svg(user: dict[str, Any], events: list[dict[str, Any]]) -> str:
    days = flatten_days(user)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    total = int(calendar["totalContributions"])
    current, longest, longest_start, longest_end = streaks(days)
    repos = int(user["repositories"]["totalCount"])
    followers = int(user["followers"]["totalCount"])
    stars = sum(int(repo["stargazerCount"]) for repo in user["repositories"]["nodes"])

    recent_days = days[-364:]
    width = 980
    height = 540
    cell = 11
    gap = 3
    start_x = 36
    start_y = 180

    # Contribution matrix: 52 weeks x 7 days.
    cells: list[str] = []
    for index, day in enumerate(recent_days):
        col = index // 7
        row = index % 7
        x = start_x + col * (cell + gap)
        y = start_y + row * (cell + gap)
        title = f"{day['date']}: {day['contributionCount']} contribution(s)"
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{contribution_color(day["contributionLevel"])}">'
            f'<title>{esc(title)}</title></rect>'
        )

    # Month labels based on first observed occurrence.
    month_labels: list[str] = []
    seen_months: set[str] = set()
    for index, day in enumerate(recent_days):
        month_key = day["date"][:7]
        if month_key in seen_months:
            continue
        seen_months.add(month_key)
        x = start_x + (index // 7) * (cell + gap)
        label = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%b")
        month_labels.append(
            f'<text x="{x}" y="168" fill="#8b949e" font-size="9">{esc(label)}</text>'
        )

    # Recent activity stream.
    activity_rows: list[str] = []
    base_y = 410
    visible_events = events[:5]
    if not visible_events:
        activity_rows.append(
            '<text x="36" y="438" fill="#8b949e" font-size="11">No recent public activity found.</text>'
        )
    else:
        for i, event in enumerate(visible_events):
            y = base_y + i * 24
            primary, secondary = event_description(event)
            icon = event_icon(event.get("type", ""))
            when = fmt_event_time(event.get("created_at", ""))
            repo = event.get("repo", {}).get("name", "GitHub")
            activity_rows.append(
                f'<circle cx="48" cy="{y-4}" r="9" fill="#21262d" stroke="#30363d"/>'
                f'<text x="48" y="{y}" text-anchor="middle" fill="#58a6ff" font-size="11" font-weight="700">{esc(icon)}</text>'
                f'<text x="66" y="{y-6}" fill="#f0f6fc" font-size="11">{esc(primary)}</text>'
                f'<text x="66" y="{y+8}" fill="#8b949e" font-size="9">{esc(secondary) if secondary else esc(repo)} · {esc(when)}</text>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" rx="12" fill="#0d1117" stroke="#30363d"/>
  <text x="24" y="31" fill="#f0f6fc" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="16" font-weight="700">📊 Live GitHub Analytics &amp; Activity Dashboard</text>
  <line x1="24" y1="46" x2="956" y2="46" stroke="#30363d"/>

  <g font-family="Inter,Segoe UI,Arial,sans-serif" text-anchor="middle">
    <text x="165" y="87" fill="#58a6ff" font-size="27" font-weight="700">{fmt_num(total)}</text>
    <text x="165" y="108" fill="#f78166" font-size="11">Total Contributions</text>
    <text x="165" y="124" fill="#8b949e" font-size="9">Last 12 months</text>

    <text x="490" y="87" fill="#bc8cff" font-size="27" font-weight="700">{current}</text>
    <text x="490" y="108" fill="#bc8cff" font-size="11">Current Streak</text>
    <text x="490" y="124" fill="#8b949e" font-size="9">As of {esc(fmt_date(days[-1]['date'] if days else ''))}</text>

    <text x="815" y="87" fill="#58a6ff" font-size="27" font-weight="700">{longest}</text>
    <text x="815" y="108" fill="#f78166" font-size="11">Longest Streak</text>
    <text x="815" y="124" fill="#8b949e" font-size="9">{esc(fmt_date(longest_start))} – {esc(fmt_date(longest_end))}</text>
  </g>

  <line x1="326" y1="62" x2="326" y2="132" stroke="#484f58"/>
  <line x1="652" y1="62" x2="652" y2="132" stroke="#484f58"/>

  <text x="24" y="153" fill="#f0f6fc" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="11" font-weight="600">Contribution Matrix</text>
  <g font-family="Inter,Segoe UI,Arial,sans-serif">{''.join(month_labels)}</g>
  <g>{''.join(cells)}</g>

  <line x1="24" y1="286" x2="956" y2="286" stroke="#30363d"/>
  <text x="24" y="311" fill="#f0f6fc" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="12" font-weight="700">Activity Stream</text>
  <text x="956" y="311" text-anchor="end" fill="#8b949e" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="9">Recent public activity</text>
  <g font-family="Inter,Segoe UI,Arial,sans-serif">{''.join(activity_rows)}</g>

  <line x1="24" y1="525" x2="956" y2="525" stroke="#30363d"/>
  <text x="24" y="517" fill="#8b949e" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="9">Public repos: {repos}</text>
  <text x="184" y="517" fill="#8b949e" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="9">Followers: {followers}</text>
  <text x="310" y="517" fill="#8b949e" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="9">Repo stars: {stars}</text>
  <text x="956" y="517" text-anchor="end" fill="#8b949e" font-family="Inter,Segoe UI,Arial,sans-serif" font-size="9">github.com/{esc(USERNAME)}</text>
</svg>'''


def main() -> None:
    user = get_graphql_user()
    events = get_public_events()
    svg = build_svg(user, events)
    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"Generated {OUTPUT} for @{USERNAME} with {len(events)} recent public events")


if __name__ == "__main__":
    main()
