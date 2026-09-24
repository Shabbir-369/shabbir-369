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
HEIGHT = 680

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

def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)

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

def get_contributions() -> list[tuple[dt.date, int]]:
    end = dt.date.today()
    start = end - dt.timedelta(days=364)
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from,to:$to) {
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
    data = graphql(
        query,
        {
            "login": USERNAME,
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{end.isoformat()}T23:59:59Z",
        },
    )
    weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [
        (dt.date.fromisoformat(day["date"]), int(day["contributionCount"]))
        for week in weeks
        for day in week["contributionDays"]
    ]

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

def activity() -> list[dict[str, str]]:
    try:
        events = request_json(
            f"https://api.github.com/users/{USERNAME}/events/public?per_page=12"
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
            detail = f"{repo} · {branch}"
        elif typ == "CreateEvent":
            icon = "+"
            action = "created"
            detail = f"{repo} · {payload.get('ref_type', 'repository')}"
        elif typ == "PullRequestEvent":
            icon = "↗"
            action = payload.get("action", "updated")
            detail = f"{repo} · pull request"
        elif typ == "IssuesEvent":
            icon = "#"
            action = payload.get("action", "updated")
            detail = f"{repo} · issue"
        elif typ == "IssueCommentEvent":
            icon = "%"
            action = "commented in"
            detail = f"{repo} · issue"
        elif typ == "ReleaseEvent":
            icon = "*"
            action = "released"
            detail = repo
        elif typ == "ForkEvent":
            icon = "⑂"
            action = "forked"
            detail = repo
        elif typ == "WatchEvent":
            icon = "★"
            action = "starred"
            detail = repo
        elif typ == "DeleteEvent":
            icon = "-"
            action = "deleted"
            detail = f"{repo} · {payload.get('ref_type', 'ref')}"

        result.append({"icon": icon, "action": action, "detail": detail, "date": stamp})
    return result[:5]

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

def build_svg(days: list[tuple[dt.date, int]], total: int, current: int, longest: int, events: list[dict[str, str]]) -> str:
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
    out.append("""
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
    <rect x="18" y="18" width="1084" height="644" rx="10"/>
  </clipPath>
</defs>
""")
    out.append(f'<rect width="{WIDTH}" height="{HEIGHT}" rx="14" fill="{BLACK}"/>')
    out.append(f'<rect x="10" y="10" width="{WIDTH-20}" height="{HEIGHT-20}" rx="13" fill="url(#bg)" stroke="{BORDER}" stroke-width="2"/>')
    out.append(f'<rect x="18" y="18" width="1084" height="644" rx="10" fill="url(#bg)" stroke="#20282d"/>')

    out.append(f'<g clip-path="url(#clip)" opacity=".11"><rect x="18" y="18" width="1084" height="644" fill="{GREEN}" filter="url(#softGlow)" opacity=".20"/>')
    for y in range(72, 642, 26):
        out.append(f'<line x1="18" y1="{y}" x2="1102" y2="{y}" stroke="{GREEN}" stroke-width="1"/>')
    out.append('<rect x="18" y="-60" width="1084" height="70" fill="#c9ffd3" opacity=".06"><animate attributeName="y" from="-60" to="660" dur="7s" repeatCount="indefinite"/></rect></g>')

    out.append('<rect x="18" y="18" width="1084" height="48" fill="#0a0e10"/>')
    out += [
        '<circle cx="39" cy="42" r="5" fill="#7b3f32"/>',
        '<circle cx="56" cy="42" r="5" fill="#8a6a2d"/>',
        '<circle cx="73" cy="42" r="5" fill="#3f6f48"/>',
        f'<text x="94" y="47" font-family="monospace" font-size="16" fill="{TEXT}">shabbir@github:~$ ./activity --live</text>',
        f'<text x="1074" y="47" text-anchor="end" font-family="monospace" font-size="11" fill="{MUTED}">CRT / 24px scan</text>',
        f'<text x="38" y="96" font-family="monospace" font-size="12" fill="{MUTED}">$ status --summary</text>',
        f'<text x="38" y="126" font-family="monospace" font-size="26" font-weight="700" fill="{GREEN}">GitHub Analytics &amp; Activity</text>',
        f'<rect x="646" y="108" width="7" height="24" rx="1" fill="{AMBER}"><animate attributeName="opacity" values="1;0;1" dur="1.05s" repeatCount="indefinite"/></rect>',
    ]

    stats = [
        (34, "TOTAL CONTRIBUTIONS", f"{total:,}", "last 365d", AMBER),
        (365, "CURRENT STREAK", str(current), "days", GREEN),
        (696, "LONGEST STREAK", str(longest), "days", GREEN),
    ]
    for x, label, number, tail, fill in stats:
        out += [
            f'<rect x="{x}" y="146" width="315" height="82" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
            f'<text x="{x+18}" y="171" font-family="monospace" font-size="11" fill="{MUTED}">{label}</text>',
            f'<text x="{x+18}" y="205" font-family="monospace" font-size="28" font-weight="700" fill="{fill}">{html.escape(number)}</text>',
            f'<text x="{x+297}" y="205" text-anchor="end" font-family="monospace" font-size="11" fill="{MUTED}">{tail}</text>',
        ]

    out += [
        f'<rect x="34" y="245" width="686" height="372" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="52" y="273" font-family="monospace" font-size="12" fill="{MUTED}">CONTRIBUTION MATRIX</text>',
        f'<text x="700" y="273" text-anchor="end" font-family="monospace" font-size="10" fill="{MUTED}">rolling 365d</text>',
    ]

    cell = 11
    gap = 3
    x0 = 52
    y0 = 306

    last_month = None
    for i, col in enumerate(columns):
        x = x0 + i * (cell + gap)
        if col:
            month = col[0][0].strftime("%b")
            if month != last_month:
                out.append(f'<text x="{x}" y="294" font-family="monospace" font-size="9" fill="{MUTED}">{month}</text>')
                last_month = month
        for r, (date_value, count) in enumerate(col):
            y = y0 + r * (cell + gap)
            lvl = level(count, maximum)
            fill = CELL[lvl]
            delay = ((i * 7 + r * 11) % 23) / 10
            title = esc(f"{date_value.isoformat()} · {count} contribution{'s' if count != 1 else ''}")
            out.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}" stroke="#0c1510" stroke-width=".7">'
                f'<title>{title}</title>'
                f'<animate attributeName="opacity" values=".72;1;.72" dur="3.7s" begin="{delay:.1f}s" repeatCount="indefinite"/>'
                f'</rect>'
            )

    out += [
        f'<text x="52" y="584" font-family="monospace" font-size="10" fill="{MUTED}">less</text>',
        '<rect x="82" y="575" width="11" height="11" rx="2.5" fill="#161c20"/>',
        '<rect x="98" y="575" width="11" height="11" rx="2.5" fill="#21402d"/>',
        '<rect x="114" y="575" width="11" height="11" rx="2.5" fill="#2d6a40"/>',
        '<rect x="130" y="575" width="11" height="11" rx="2.5" fill="#3f9b58"/>',
        '<rect x="146" y="575" width="11" height="11" rx="2.5" fill="#79d98a"/>',
        f'<text x="165" y="584" font-family="monospace" font-size="10" fill="{MUTED}">more</text>',
        f'<text x="52" y="606" font-family="monospace" font-size="9.5" fill="#66736c">Cells softly pulse like an old CRT phosphor — no neon overload.</text>',
    ]

    out += [
        f'<rect x="736" y="245" width="275" height="372" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="754" y="273" font-family="monospace" font-size="12" fill="{MUTED}">ACTIVITY STREAM</text>',
        f'<text x="993" y="273" text-anchor="end" font-family="monospace" font-size="9.5" fill="{MUTED}">public events</text>',
    ]
    ys = [314, 365, 416, 467, 518]
    for idx, y in enumerate(ys):
        if idx < len(events):
            e = events[idx]
            out += [
                f'<text x="754" y="{y}" font-family="monospace" font-size="15" font-weight="700" fill="{AMBER}">{esc(e["icon"])}</text>',
                f'<text x="778" y="{y}" font-family="monospace" font-size="10.5" fill="{TEXT}">{esc(e["action"])}</text>',
                f'<text x="778" y="{y+16}" font-family="monospace" font-size="9.5" fill="{GREEN}">{esc(e["detail"])}</text>',
                f'<text x="993" y="{y+16}" text-anchor="end" font-family="monospace" font-size="8.5" fill="{MUTED}">{esc(e["date"])}</text>',
            ]
        else:
            out.append(f'<text x="754" y="{y}" font-family="monospace" font-size="10" fill="{MUTED}">{esc("waiting for public activity..." if idx == 0 else "—")}</text>')

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out += [
        '<line x1="754" y1="553" x2="993" y2="553" stroke="#222b30"/>',
        f'<text x="754" y="576" font-family="monospace" font-size="9.5" fill="{MUTED}">$ updated: {esc(timestamp)}</text>',
        f'<text x="754" y="598" font-family="monospace" font-size="9.5" fill="{GREEN}">● dashboard online</text>',
        f'<rect x="754" y="607" width="5" height="9" fill="{AMBER}"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>',
        f'<text x="766" y="616" font-family="monospace" font-size="9.5" fill="{TEXT}">_</text>',
        f'<text x="38" y="645" font-family="monospace" font-size="10" fill="#647078">shabbir@github:~$ echo "build quietly. keep shipping."</text>',
        f'<text x="1080" y="645" text-anchor="end" font-family="monospace" font-size="10" fill="#647078">github actions :: auto refresh</text>',
        '</svg>',
    ]
    return "\n".join(out)

def main() -> None:
    try:
        days = get_contributions()
        total = sum(count for _, count in days)
        current, longest = streaks(days)
    except Exception as exc:
        print(f"Contribution API warning: {exc}")
        today = dt.date.today()
        days = [(today - dt.timedelta(days=i), 0) for i in range(365)]
        total, current, longest = 0, 0, 0

    events = activity()
    svg = build_svg(days, total, current, longest, events)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()
