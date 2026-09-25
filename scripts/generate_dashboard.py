from __future__ import annotations

import datetime as dt
import html
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

USERNAME = os.environ.get("USER_NAME", "Shabbir-369")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUTPUT = "assets/github-dashboard.svg"

UA = f"{USERNAME}-profile-dashboard (+https://github.com/{USERNAME})"
REST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": UA,
}
GRAPHQL_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": UA,
}

WIDTH = 1120

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
LANG_BAR = ["#79d98a", "#5fc077", "#45a865", "#ffb454", "#e0954a"]


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1].rstrip() + "…"


def _open(req: urllib.request.Request, timeout: int = 25, retries: int = 3) -> Any:
    """Fetch a request, retrying transient failures a couple of times.

    GitHub occasionally throws transient 502/503s or brief connection resets;
    a short retry keeps a flaky moment from zeroing out a whole dashboard.
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            # Don't retry hard failures like 401/403/404 — they won't heal themselves.
            if exc.code not in (500, 502, 503, 504):
                raise
        except Exception as exc:  # noqa: BLE001 - want to retry any transient error
            last_exc = exc
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def request_json(url: str) -> Any:
    headers = dict(REST_HEADERS)
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return _open(urllib.request.Request(url, headers=headers))


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    headers = dict(GRAPHQL_HEADERS)
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    payload = _open(
        urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            method="POST",
            headers=headers,
        )
    )
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


def get_profile() -> dict[str, int] | None:
    """Followers + public repo count. Returns None if the API is unavailable."""
    try:
        data = request_json(f"https://api.github.com/users/{USERNAME}")
        return {
            "followers": int(data.get("followers", 0)),
            "public_repos": int(data.get("public_repos", 0)),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"Profile API warning: {exc}")
        return None


def get_languages_and_stars() -> tuple[list[tuple[str, float]], int]:
    """Total stars across owned, non-fork repos + top 5 languages by byte size.

    Returns ([], 0) on any failure so callers can render without this data
    instead of crashing the whole build.
    """
    query = """
    query($login:String!, $after:String) {
      user(login:$login) {
        repositories(first:100, after:$after, isFork:false, privacy:PUBLIC, ownerAffiliations:[OWNER]) {
          pageInfo { hasNextPage endCursor }
          nodes {
            stargazerCount
            languages(first:5, orderBy:{field:SIZE, direction:DESC}) {
              edges { size node { name } }
            }
          }
        }
      }
    }
    """
    lang_bytes: dict[str, int] = {}
    stars = 0
    after: str | None = None
    try:
        for _ in range(10):  # hard cap so a pathological account can't loop forever
            data = graphql(query, {"login": USERNAME, "after": after})
            repos = data["user"]["repositories"]
            for node in repos["nodes"]:
                stars += int(node.get("stargazerCount", 0))
                for edge in node.get("languages", {}).get("edges", []):
                    name = edge["node"]["name"]
                    lang_bytes[name] = lang_bytes.get(name, 0) + int(edge["size"])
            if repos["pageInfo"]["hasNextPage"]:
                after = repos["pageInfo"]["endCursor"]
            else:
                break
    except Exception as exc:  # noqa: BLE001
        print(f"Languages API warning: {exc}")
        return [], 0

    total = sum(lang_bytes.values())
    if total == 0:
        return [], stars
    ranked = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[:5]
    return [(name, size / total * 100) for name, size in ranked], stars


def activity() -> list[dict[str, str]]:
    try:
        events = request_json(
            f"https://api.github.com/users/{USERNAME}/events/public?per_page=12"
        )
    except Exception as exc:  # noqa: BLE001
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


def build_svg(
    days: list[tuple[dt.date, int]],
    total: int,
    current: int,
    longest: int,
    events: list[dict[str, str]],
    profile: dict[str, int] | None,
    languages: list[tuple[str, float]],
    stars: int,
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

    # Layout is computed top-down from a handful of constants rather than
    # hardcoded pixel numbers, so the canvas always ends up tall enough to
    # hold whatever the two side panels actually render.
    STATS_Y = 172
    STATS_H = 82
    PANEL_Y = STATS_Y + STATS_H + 17  # gap below the stat cards
    PANEL_H = 452  # tall enough for 5 activity rows + footer, and for the
    # contribution grid + legend + top-languages block on the left
    FOOTER_GAP = 32  # space between panel bottom and the closing terminal line
    BOTTOM_MARGIN = 25  # space between that line and the card's edge
    CARD_BOTTOM = PANEL_Y + PANEL_H + FOOTER_GAP + BOTTOM_MARGIN
    HEIGHT = CARD_BOTTOM + 18  # matches the 18px top margin

    out: list[str] = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img">')
    out.append(f'<title>GitHub analytics and activity dashboard for {esc(USERNAME)}</title>')
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
    <rect x="18" y="18" width="1084" height="{card_h}" rx="10"/>
  </clipPath>
</defs>
""".replace("{card_h}", str(HEIGHT - 36)))
    out.append(f'<rect width="{WIDTH}" height="{HEIGHT}" rx="14" fill="{BLACK}"/>')
    out.append(f'<rect x="10" y="10" width="{WIDTH-20}" height="{HEIGHT-20}" rx="13" fill="url(#bg)" stroke="{BORDER}" stroke-width="2"/>')
    out.append(f'<rect x="18" y="18" width="1084" height="{HEIGHT-36}" rx="10" fill="url(#bg)" stroke="#20282d"/>')

    out.append(f'<g clip-path="url(#clip)" opacity=".11"><rect x="18" y="18" width="1084" height="{HEIGHT-36}" fill="{GREEN}" filter="url(#softGlow)" opacity=".20"/>')
    for y in range(72, HEIGHT - 38, 26):
        out.append(f'<line x1="18" y1="{y}" x2="1102" y2="{y}" stroke="{GREEN}" stroke-width="1"/>')
    out.append(f'<rect x="18" y="-60" width="1084" height="70" fill="#c9ffd3" opacity=".06"><animate attributeName="y" from="-60" to="{HEIGHT-20}" dur="7s" repeatCount="indefinite"/></rect></g>')

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

    profile_bits = [f"@{USERNAME}"]
    if profile is not None:
        profile_bits.append(f"{profile['followers']:,} followers")
        profile_bits.append(f"{profile['public_repos']:,} public repos")
    if stars:
        profile_bits.append(f"{stars:,} \u2605 stars earned")
    out.append(
        f'<text x="38" y="150" font-family="monospace" font-size="11.5" fill="{MUTED}">{esc("  ·  ".join(profile_bits))}</text>'
    )

    stats = [
        (34, "TOTAL CONTRIBUTIONS", f"{total:,}", "last 365d", AMBER),
        (365, "CURRENT STREAK", str(current), "days", GREEN),
        (696, "LONGEST STREAK", str(longest), "days", GREEN),
    ]
    for x, label, number, tail, fill in stats:
        out += [
            f'<rect x="{x}" y="{STATS_Y}" width="315" height="82" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
            f'<text x="{x+18}" y="{STATS_Y+25}" font-family="monospace" font-size="11" fill="{MUTED}">{label}</text>',
            f'<text x="{x+18}" y="{STATS_Y+59}" font-family="monospace" font-size="28" font-weight="700" fill="{fill}">{html.escape(number)}</text>',
            f'<text x="{x+297}" y="{STATS_Y+59}" text-anchor="end" font-family="monospace" font-size="11" fill="{MUTED}">{tail}</text>',
        ]

    out += [
        f'<rect x="34" y="{PANEL_Y}" width="686" height="{PANEL_H}" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="52" y="{PANEL_Y+28}" font-family="monospace" font-size="12" fill="{MUTED}">CONTRIBUTION MATRIX</text>',
        f'<text x="700" y="{PANEL_Y+28}" text-anchor="end" font-family="monospace" font-size="10" fill="{MUTED}">rolling 365d</text>',
    ]

    cell = 11
    gap = 3
    x0 = 52
    y0 = PANEL_Y + 61

    last_month = None
    for i, col in enumerate(columns):
        x = x0 + i * (cell + gap)
        if col:
            month = col[0][0].strftime("%b")
            if month != last_month:
                out.append(f'<text x="{x}" y="{y0-12}" font-family="monospace" font-size="9" fill="{MUTED}">{month}</text>')
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

    legend_y = y0 + 7 * (cell + gap) + 21
    out += [
        f'<text x="52" y="{legend_y}" font-family="monospace" font-size="10" fill="{MUTED}">less</text>',
        f'<rect x="82" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="{CELL[0]}"/>',
        f'<rect x="98" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="{CELL[1]}"/>',
        f'<rect x="114" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="{CELL[2]}"/>',
        f'<rect x="130" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="{CELL[3]}"/>',
        f'<rect x="146" y="{legend_y-9}" width="11" height="11" rx="2.5" fill="{CELL[4]}"/>',
        f'<text x="165" y="{legend_y}" font-family="monospace" font-size="10" fill="{MUTED}">more</text>',
    ]

    # Top languages — fills the space below the contribution grid with real,
    # live data instead of leaving it empty.
    lang_y = legend_y + 30
    out.append(f'<line x1="52" y1="{lang_y}" x2="700" y2="{lang_y}" stroke="#222b30"/>')
    lang_y += 26
    out.append(f'<text x="52" y="{lang_y}" font-family="monospace" font-size="12" fill="{MUTED}">TOP LANGUAGES</text>')
    if languages:
        bar_x = 52
        bar_top = lang_y + 16
        bar_w = 648
        row_h = 26
        for idx, (name, pct) in enumerate(languages):
            ry = bar_top + idx * row_h
            fill = LANG_BAR[idx % len(LANG_BAR)]
            label_w = 150
            track_x = bar_x + label_w
            track_w = bar_w - label_w - 52
            filled_w = max(4, track_w * (pct / 100))
            out += [
                f'<text x="{bar_x}" y="{ry+9}" font-family="monospace" font-size="10.5" fill="{TEXT}">{esc(truncate(name, 16))}</text>',
                f'<rect x="{track_x}" y="{ry}" width="{track_w}" height="10" rx="3" fill="#161c20"/>',
                f'<rect x="{track_x}" y="{ry}" width="{filled_w:.1f}" height="10" rx="3" fill="{fill}"/>',
                f'<text x="{bar_x+bar_w-2}" y="{ry+9}" text-anchor="end" font-family="monospace" font-size="9.5" fill="{MUTED}">{pct:.1f}%</text>',
            ]
    else:
        out.append(f'<text x="52" y="{lang_y+22}" font-family="monospace" font-size="9.5" fill="#66736c">no public repository data available right now</text>')

    out.append(f'<text x="52" y="{PANEL_Y+PANEL_H-13}" font-family="monospace" font-size="9.5" fill="#66736c">Cells softly pulse like an old CRT phosphor — no neon overload.</text>')

    out += [
        f'<rect x="736" y="{PANEL_Y}" width="275" height="{PANEL_H}" rx="8" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="754" y="{PANEL_Y+28}" font-family="monospace" font-size="12" fill="{MUTED}">ACTIVITY STREAM</text>',
        f'<text x="993" y="{PANEL_Y+28}" text-anchor="end" font-family="monospace" font-size="9.5" fill="{MUTED}">public events</text>',
    ]

    row_h = 58
    first_y = PANEL_Y + 68
    ys = [first_y + i * row_h for i in range(5)]
    for idx, y in enumerate(ys):
        if idx < len(events):
            e = events[idx]
            action_text = truncate(e["action"], 26)
            detail_text = truncate(e["detail"], 30)
            out += [
                f'<text x="754" y="{y}" font-family="monospace" font-size="15" font-weight="700" fill="{AMBER}">{esc(e["icon"])}</text>',
                f'<text x="778" y="{y}" font-family="monospace" font-size="10.5" fill="{TEXT}">{esc(action_text)}</text>',
                f'<text x="993" y="{y}" text-anchor="end" font-family="monospace" font-size="8.5" fill="{MUTED}">{esc(e["date"])}</text>',
                f'<text x="778" y="{y+18}" font-family="monospace" font-size="9.5" fill="{GREEN}">{esc(detail_text)}</text>',
            ]
            if idx < len(events) - 1:
                out.append(f'<line x1="754" y1="{y+32}" x2="993" y2="{y+32}" stroke="#181f23"/>')
        else:
            out.append(f'<text x="754" y="{y}" font-family="monospace" font-size="10" fill="{MUTED}">{esc("waiting for public activity..." if idx == 0 else "—")}</text>')

    footer_y = PANEL_Y + PANEL_H - 66
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out += [
        f'<line x1="754" y1="{footer_y}" x2="993" y2="{footer_y}" stroke="#222b30"/>',
        f'<text x="754" y="{footer_y+23}" font-family="monospace" font-size="9.5" fill="{MUTED}">$ updated: {esc(timestamp)}</text>',
        f'<text x="754" y="{footer_y+45}" font-family="monospace" font-size="9.5" fill="{GREEN}">\u25cf dashboard online</text>',
        f'<rect x="754" y="{footer_y+54}" width="5" height="9" fill="{AMBER}"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>',
        f'<text x="766" y="{footer_y+63}" font-family="monospace" font-size="9.5" fill="{TEXT}">_</text>',
        f'<text x="38" y="{HEIGHT-35}" font-family="monospace" font-size="10" fill="#647078">shabbir@github:~$ echo "build quietly. keep shipping."</text>',
        f'<text x="1080" y="{HEIGHT-35}" text-anchor="end" font-family="monospace" font-size="10" fill="#647078">github actions :: auto refresh</text>',
        '</svg>',
    ]
    return "\n".join(out)


def main() -> None:
    try:
        days = get_contributions()
        total = sum(count for _, count in days)
        current, longest = streaks(days)
    except Exception as exc:  # noqa: BLE001
        print(f"Contribution API warning: {exc}")
        today = dt.date.today()
        days = [(today - dt.timedelta(days=i), 0) for i in range(365)]
        total, current, longest = 0, 0, 0

    events = activity()
    profile = get_profile()
    languages, stars = get_languages_and_stars()

    svg = build_svg(days, total, current, longest, events, profile, languages, stars)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(svg)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
