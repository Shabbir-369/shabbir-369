from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.request
from typing import Any

USERNAME = os.environ.get("USER_NAME", "Shabbir-369")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT = "assets/github-dashboard.svg"

WIDTH = 1120
HEIGHT = 696

BLACK = "#070a0c"
BG = "#0b0f12"
PANEL = "#0d1215"
PANEL_2 = "#0a0f11"
BORDER = "#2a3338"
TEXT = "#d7e0d9"
MUTED = "#7f8b82"
GREEN = "#7ee787"
GREEN_MID = "#45b864"
AMBER = "#ffb454"
CELL = ["#161c20", "#21402d", "#2d6a40", "#3f9b58", "#79d98a"]
LANG_BAR = ["#79d98a", "#4fb56a", "#3f9b58", "#2d6a40", "#21402d"]

# ---------------------------------------------------------------------------
# Layout constants. Everything below the title got a little more breathing
# room (for the new subtitle line) and the contribution panel's dead space
# now holds a "top languages" readout instead of sitting empty.
# ---------------------------------------------------------------------------
CONTENT_X = 18
CONTENT_W = 1084
STAT_Y = 162
STAT_H = 82
MAIN_Y = 258
MAIN_H = 372
MAIN_BOTTOM = MAIN_Y + MAIN_H  # 630
CONTENT_H = MAIN_BOTTOM + 47  # outer panel bottom edge sits just past the footer line


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "\u2026"


def request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

PROFILE_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      isFork: false
      privacy: PUBLIC
      orderBy: { field: PUSHED_AT, direction: DESC }
    ) {
      totalCount
      nodes {
        languages(first: 8, orderBy: { field: SIZE, direction: DESC }) {
          edges {
            size
            node { name }
          }
        }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_profile() -> dict[str, Any]:
    """One combined GraphQL round-trip for everything that needs auth."""
    end = dt.date.today()
    start = end - dt.timedelta(days=364)
    data = graphql(
        PROFILE_QUERY,
        {
            "login": USERNAME,
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{end.isoformat()}T23:59:59Z",
        },
    )
    user = data["user"]
    if user is None:
        raise RuntimeError(f"GitHub user '{USERNAME}' not found")

    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [
        (dt.date.fromisoformat(day["date"]), int(day["contributionCount"]))
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]

    lang_totals: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            lang_totals[name] = lang_totals.get(name, 0) + int(edge["size"])

    return {
        "days": days,
        "total_contributions": int(calendar["totalContributions"]),
        "followers": int(user["followers"]["totalCount"]),
        "public_repos": int(user["repositories"]["totalCount"]),
        "created_at": user["createdAt"],
        "languages": lang_totals,
    }


def streaks(days: list[tuple[dt.date, int]]) -> tuple[int, int]:
    by_day = {d: count for d, count in days}
    cursor = dt.date.today()
    current = 0
    if by_day.get(cursor, 0) == 0:
        cursor -= dt.timedelta(days=1)
    while by_day.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)

    longest = 0
    run = 0
    for d, _ in sorted(days):
        if by_day.get(d, 0) > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return current, longest


def account_uptime(created_at: str) -> str:
    created = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    delta_days = (dt.date.today() - created).days
    years, rest = divmod(delta_days, 365)
    if years > 0:
        return f"{years}y {rest}d"
    return f"{rest}d"


def top_languages(totals: dict[str, int], limit: int = 5) -> list[tuple[str, float]]:
    grand_total = sum(totals.values())
    if grand_total <= 0:
        return []
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [(name, size / grand_total) for name, size in ranked]


def activity() -> list[dict[str, str]]:
    try:
        events = request_json(
            f"https://api.github.com/users/{USERNAME}/events/public?per_page=15"
        )
    except Exception as exc:
        print(f"Activity API warning: {exc}")
        return []

    result: list[dict[str, str]] = []
    for ev in events:
        typ = ev.get("type", "Event")
        repo = ev.get("repo", {}).get("name", "unknown")
        payload = ev.get("payload", {})
        created = ev.get("created_at", "")
        stamp = created[:10] if created else ""

        icon = ">"
        action = typ.replace("Event", "")
        detail = repo

        if typ == "PushEvent":
            icon = "$"
            n = int(payload.get("size", 0))
            branch = payload.get("ref", "").split("/")[-1] or "branch"
            action = f"pushed {n} commit{'s' if n != 1 else ''} to"
            detail = f"{repo} \u00b7 {branch}"
        elif typ == "CreateEvent":
            icon = "+"
            action = "created"
            detail = f"{repo} \u00b7 {payload.get('ref_type', 'repository')}"
        elif typ == "PullRequestEvent":
            icon = "\u2197"
            action = payload.get("action", "updated")
            detail = f"{repo} \u00b7 pull request"
        elif typ == "IssuesEvent":
            icon = "#"
            action = payload.get("action", "updated")
            detail = f"{repo} \u00b7 issue"
        elif typ == "IssueCommentEvent":
            icon = "%"
            action = "commented in"
            detail = f"{repo} \u00b7 issue"
        elif typ == "ReleaseEvent":
            icon = "*"
            action = "released"
            detail = repo
        elif typ == "ForkEvent":
            icon = "\u2442"
            action = "forked"
            detail = repo
        elif typ == "WatchEvent":
            icon = "\u2605"
            action = "starred"
            detail = repo
        elif typ == "DeleteEvent":
            icon = "-"
            action = "deleted"
            detail = f"{repo} \u00b7 {payload.get('ref_type', 'ref')}"
        elif typ == "MemberEvent":
            icon = "&"
            action = "added a collaborator to"
            detail = repo
        elif typ == "PublicEvent":
            icon = "\u25cb"
            action = "open-sourced"
            detail = repo

        result.append({"icon": icon, "action": action, "detail": detail, "date": stamp})
        if len(result) == 5:
            break
    return result


def level(count: int, maximum: int) -> int:
    if count <= 0 or maximum <= 0:
        return 0
    ratio = count / maximum
    if ratio < 0.25:
        return 1
    if ratio < 0.50:
        return 2
    if ratio < 0.75:
        return 3
    return 4


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def build_svg(
    days: list[tuple[dt.date, int]],
    total: int,
    current: int,
    longest: int,
    events: list[dict[str, str]],
    followers: int | None,
    public_repos: int | None,
    uptime: str | None,
    languages: list[tuple[str, float]],
    stats_ok: bool,
) -> str:
    today = dt.date.today()
    data = {d: c for d, c in days}
    maximum = max(data.values() or [1])

    start = today - dt.timedelta(days=370)
    while start.weekday() != 6:
        start += dt.timedelta(days=1)

    columns: list[list[tuple[dt.date, int]]] = []
    cursor = start
    while cursor <= today:
        col = []
        for r in range(7):
            d = cursor + dt.timedelta(days=r)
            if d <= today:
                col.append((d, data.get(d, 0)))
        columns.append(col)
        cursor += dt.timedelta(days=7)
    columns = columns[-53:]

    out: list[str] = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">')
    out.append(f"""
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#0b0f12"/>
    <stop offset="1" stop-color="#070a0c"/>
  </linearGradient>
  <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
    <feGaussianBlur stdDeviation="2.2" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <filter id="softGlow" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur stdDeviation="6"/>
  </filter>
  <clipPath id="clip">
    <rect x="{CONTENT_X}" y="{CONTENT_X}" width="{CONTENT_W}" height="{CONTENT_H}" rx="10"/>
  </clipPath>
</defs>
""")
    out.append(f'<rect width="{WIDTH}" height="{HEIGHT}" rx="14" fill="{BLACK}"/>')
    out.append(f'<rect x="10" y="10" width="{WIDTH-20}" height="{HEIGHT-20}" rx="13" fill="url(#bg)" stroke="{BORDER}" stroke-width="2"/>')
    out.append(f'<rect x="{CONTENT_X}" y="{CONTENT_X}" width="{CONTENT_W}" height="{CONTENT_H}" rx="10" fill="url(#bg)" stroke="#20282d"/>')

    out.append(f'<g clip-path="url(#clip)" opacity=".11"><rect x="{CONTENT_X}" y="{CONTENT_X}" width="{CONTENT_W}" height="{CONTENT_H}" fill="{GREEN}" filter="url(#softGlow)" opacity=".20"/>')
    for y in range(72, CONTENT_X + CONTENT_H, 26):
        out.append(f'<line x1="{CONTENT_X}" y1="{y}" x2="{CONTENT_X+CONTENT_W}" y2="{y}" stroke="{GREEN}" stroke-width="1"/>')
    out.append(f'<rect x="{CONTENT_X}" y="-60" width="{CONTENT_W}" height="70" fill="#c9ffd3" opacity=".06"><animate attributeName="y" from="-60" to="{CONTENT_X+CONTENT_H}" dur="7s" repeatCount="indefinite"/></rect></g>')

    out.append(f'<rect x="{CONTENT_X}" y="{CONTENT_X}" width="{CONTENT_W}" height="48" fill="#0a0e10"/>')
    out += [
        '<circle cx="39" cy="42" r="5" fill="#7b3f32"/>',
        '<circle cx="56" cy="42" r="5" fill="#8a6a2d"/>',
        '<circle cx="73" cy="42" r="5" fill="#3f6f48"/>',
        f'<text x="94" y="47" font-family="monospace" font-size="16" fill="{TEXT}">shabbir@github:~$ ./activity --live</text>',
        f'<text x="1074" y="47" text-anchor="end" font-family="monospace" font-size="11" fill="{MUTED}">CRT / 24px scan</text>',
        f'<text x="38" y="96" font-family="monospace" font-size="12" fill="{MUTED}">$ status --summary</text>',
        f'<text x="38" y="126" font-family="monospace" font-size="26" font-weight="700" fill="{GREEN}">GitHub Analytics &amp; Activity</text>',
        f'<rect x="646" y="112" width="7" height="24" rx="1" fill="{AMBER}"><animate attributeName="opacity" values="1;0;1" dur="1.05s" repeatCount="indefinite"/></rect>',
    ]

    subtitle_bits = [f"@{USERNAME}"]
    if public_repos is not None:
        subtitle_bits.append(f"{public_repos} public repos")
    if followers is not None:
        subtitle_bits.append(f"{followers} followers")
    if uptime is not None:
        subtitle_bits.append(f"uptime {uptime}")
    if not stats_ok:
        subtitle_bits.append("(live stats unavailable \u2014 showing cached layout)")
    out.append(
        f'<text x="38" y="148" font-family="monospace" font-size="12.5" fill="{MUTED}">{esc(" \u00b7 ".join(subtitle_bits))}</text>'
    )

    stats = [
        (34, "TOTAL CONTRIBUTIONS", f"{total:,}" if stats_ok else "\u2014", "last 365d", AMBER),
        (365, "CURRENT STREAK", str(current) if stats_ok else "\u2014", "days", GREEN),
        (696, "LONGEST STREAK", str(longest) if stats_ok else "\u2014", "days", GREEN),
    ]
    for x, label, number, tail, fill in stats:
        out += [
            f'<rect x="{x}" y="{STAT_Y}" width="315" height="{STAT_H}" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
            f'<text x="{x+18}" y="{STAT_Y+25}" font-family="monospace" font-size="11" fill="{MUTED}">{label}</text>',
            f'<text x="{x+18}" y="{STAT_Y+59}" font-family="monospace" font-size="28" font-weight="700" fill="{fill}">{html.escape(number)}</text>',
            f'<text x="{x+297}" y="{STAT_Y+59}" text-anchor="end" font-family="monospace" font-size="11" fill="{MUTED}">{tail}</text>',
        ]

    # ---- Contribution matrix + top languages (shared left panel) ----
    left_x, left_w = 34, 686
    out += [
        f'<rect x="{left_x}" y="{MAIN_Y}" width="{left_w}" height="{MAIN_H}" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="{left_x+18}" y="{MAIN_Y+28}" font-family="monospace" font-size="12" fill="{MUTED}">CONTRIBUTION MATRIX</text>',
        f'<text x="{left_x+left_w-18}" y="{MAIN_Y+28}" text-anchor="end" font-family="monospace" font-size="10" fill="{MUTED}">rolling 365d</text>',
    ]

    cell = 11
    gap = 3
    x0 = left_x + 18
    y0 = MAIN_Y + 61

    last_month = None
    for i, col in enumerate(columns):
        x = x0 + i * (cell + gap)
        if col:
            month = col[0][0].strftime("%b")
            if month != last_month:
                out.append(f'<text x="{x}" y="{MAIN_Y+49}" font-family="monospace" font-size="9" fill="{MUTED}">{month}</text>')
                last_month = month
        for r, (date_value, count) in enumerate(col):
            y = y0 + r * (cell + gap)
            lvl = level(count, maximum)
            fill = CELL[lvl]
            delay = ((i * 7 + r * 11) % 23) / 10
            title = esc(f"{date_value.isoformat()} \u00b7 {count} contribution{'s' if count != 1 else ''}")
            out.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}" stroke="#0c1510" stroke-width=".7">'
                f'<title>{title}</title>'
                f'<animate attributeName="opacity" values=".72;1;.72" dur="3.7s" begin="{delay:.1f}s" repeatCount="indefinite"/>'
                f'</rect>'
            )

    grid_bottom = y0 + 7 * (cell + gap)  # bottom of the 7-row grid

    # Top languages, filling the space that used to sit empty under the grid
    lang_top = grid_bottom + 26
    out.append(f'<text x="{left_x+18}" y="{lang_top}" font-family="monospace" font-size="12" fill="{MUTED}">TOP LANGUAGES</text>')
    if languages:
        bar_x = left_x + 18
        bar_max_w = 300
        row_h = 20
        for idx, (name, share) in enumerate(languages):
            row_y = lang_top + 20 + idx * row_h
            bar_w = max(6, bar_max_w * share)
            color = LANG_BAR[idx % len(LANG_BAR)]
            label = truncate(name, 14)
            out += [
                f'<text x="{bar_x}" y="{row_y}" font-family="monospace" font-size="10.5" fill="{TEXT}">{esc(label)}</text>',
                f'<rect x="{bar_x+120}" y="{row_y-10}" width="{bar_max_w}" height="10" rx="2" fill="#161c20"/>',
                f'<rect x="{bar_x+120}" y="{row_y-10}" width="{bar_w:.1f}" height="10" rx="2" fill="{color}"/>',
                f'<text x="{bar_x+120+bar_max_w+14}" y="{row_y}" font-family="monospace" font-size="10" fill="{MUTED}">{share*100:.1f}%</text>',
            ]
    else:
        out.append(f'<text x="{left_x+18}" y="{lang_top+22}" font-family="monospace" font-size="10.5" fill="{MUTED}">no language data yet</text>')

    legend_y = MAIN_Y + MAIN_H - 32
    out += [
        f'<text x="{left_x+18}" y="{legend_y}" font-family="monospace" font-size="10" fill="{MUTED}">less</text>',
        f'<rect x="{left_x+48}" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="#161c20"/>',
        f'<rect x="{left_x+64}" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="#21402d"/>',
        f'<rect x="{left_x+80}" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="#2d6a40"/>',
        f'<rect x="{left_x+96}" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="#3f9b58"/>',
        f'<rect x="{left_x+112}" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="#79d98a"/>',
        f'<text x="{left_x+131}" y="{legend_y}" font-family="monospace" font-size="10" fill="{MUTED}">more</text>',
        f'<text x="{left_x+18}" y="{legend_y+22}" font-family="monospace" font-size="9.5" fill="#66736c">Cells softly pulse like an old CRT phosphor \u2014 no neon overload.</text>',
    ]

    # ---- Activity stream (right panel) ----
    right_x, right_w = 736, 275
    out += [
        f'<rect x="{right_x}" y="{MAIN_Y}" width="{right_w}" height="{MAIN_H}" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="{right_x+18}" y="{MAIN_Y+28}" font-family="monospace" font-size="12" fill="{MUTED}">ACTIVITY STREAM</text>',
        f'<text x="{right_x+right_w-18}" y="{MAIN_Y+28}" text-anchor="end" font-family="monospace" font-size="9.5" fill="{MUTED}">public events</text>',
    ]
    row_h = 51
    row0 = MAIN_Y + 69
    date_x = right_x + right_w - 18  # right-anchored date column
    date_reserved_w = 64  # width the right-anchored "YYYY-MM-DD" text itself occupies
    detail_max_w = date_x - date_reserved_w - (right_x + 42) - 14  # safety gap before the date
    detail_max_chars = max(8, int(detail_max_w / 7.0))  # conservative px/char for monospace at 9.5px
    for idx in range(5):
        y = row0 + idx * row_h
        if idx < len(events):
            e = events[idx]
            out += [
                f'<text x="{right_x+18}" y="{y}" font-family="monospace" font-size="15" font-weight="700" fill="{AMBER}">{esc(e["icon"])}</text>',
                f'<text x="{right_x+42}" y="{y}" font-family="monospace" font-size="10.5" fill="{TEXT}">{esc(truncate(e["action"], 26))}</text>',
                f'<text x="{right_x+42}" y="{y+16}" font-family="monospace" font-size="9.5" fill="{GREEN}">{esc(truncate(e["detail"], detail_max_chars))}</text>',
                f'<text x="{date_x}" y="{y+16}" text-anchor="end" font-family="monospace" font-size="8.5" fill="{MUTED}">{esc(e["date"])}</text>',
            ]
        else:
            out.append(f'<text x="{right_x+18}" y="{y}" font-family="monospace" font-size="10" fill="{MUTED}">{esc("waiting for public activity..." if idx == 0 else chr(0x2014))}</text>')

    divider_y = row0 + 5 * row_h - 9
    out += [
        f'<line x1="{right_x+18}" y1="{divider_y}" x2="{date_x}" y2="{divider_y}" stroke="#222b30"/>',
    ]

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status_y = divider_y + 23
    out += [
        f'<text x="{right_x+18}" y="{status_y}" font-family="monospace" font-size="9.5" fill="{MUTED}">$ updated: {esc(timestamp)}</text>',
        f'<text x="{right_x+18}" y="{status_y+22}" font-family="monospace" font-size="9.5" fill="{GREEN}">\u25cf dashboard online</text>',
        f'<rect x="{right_x+18}" y="{status_y+31}" width="5" height="9" fill="{AMBER}"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>',
        f'<text x="{right_x+30}" y="{status_y+40}" font-family="monospace" font-size="9.5" fill="{TEXT}">_</text>',
    ]

    footer_y = MAIN_BOTTOM + 27
    out += [
        f'<text x="38" y="{footer_y}" font-family="monospace" font-size="10" fill="#647078">shabbir@github:~$ echo "build quietly. keep shipping."</text>',
        f'<text x="1080" y="{footer_y}" text-anchor="end" font-family="monospace" font-size="10" fill="#647078">github actions :: auto refresh</text>',
        '</svg>',
    ]
    return "\n".join(out)


def main() -> None:
    stats_ok = True
    followers = public_repos = None
    uptime = None
    languages: list[tuple[str, float]] = []

    try:
        profile = fetch_profile()
        days = profile["days"]
        total = profile["total_contributions"]
        current, longest = streaks(days)
        followers = profile["followers"]
        public_repos = profile["public_repos"]
        uptime = account_uptime(profile["created_at"])
        languages = top_languages(profile["languages"])
    except Exception as exc:
        # Keep the dashboard rendering even if the API/token has a bad day --
        # show an honest "unavailable" state instead of a fake all-zero graph.
        print(f"Profile API warning: {exc}")
        stats_ok = False
        today = dt.date.today()
        days = [(today - dt.timedelta(days=i), 0) for i in range(365)]
        total, current, longest = 0, 0, 0

    events = activity()
    svg = build_svg(
        days, total, current, longest, events,
        followers, public_repos, uptime, languages, stats_ok,
    )
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
