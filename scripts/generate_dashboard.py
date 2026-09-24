from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import textwrap
import urllib.parse
import urllib.request
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter

USERNAME = os.environ.get("USER_NAME", "Shabbir-369")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SVG_OUTPUT = "assets/github-dashboard.svg"
GIF_OUTPUT = "assets/github-dashboard.gif"

WIDTH = 1180
HEIGHT = 720
FRAMES = 8

BLACK = "#050708"
BG = "#0a0e10"
PANEL = "#0d1316"
PANEL_2 = "#0a1012"
BORDER = "#253038"
BORDER_HI = "#344149"
TEXT = "#dce7df"
MUTED = "#738079"
DIM = "#4e5b56"
GREEN = "#7ee787"
GREEN_2 = "#4cc76a"
GREEN_3 = "#2a733e"
AMBER = "#ffb454"
RED = "#c97863"
CYAN = "#7ad8d1"

CELL = ["#11181b", "#193323", "#285c37", "#3e9654", "#72d887"]
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
]


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shabbir-profile-dashboard",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shabbir-profile-dashboard",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        payload = json.load(response)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def get_profile_data() -> dict[str, Any]:
    query = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        followers { totalCount }
        repositories(first:1, ownerAffiliations:OWNER, privacy:PUBLIC) { totalCount }
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
    end = dt.date.today()
    start = end - dt.timedelta(days=364)
    data = graphql(
        query,
        {
            "login": USERNAME,
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{end.isoformat()}T23:59:59Z",
        },
    )
    user = data["user"]
    calendar = user["contributionsCollection"]["contributionCalendar"]
    days = [
        (dt.date.fromisoformat(day["date"]), int(day["contributionCount"]))
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    ]
    return {
        "days": days,
        "total": int(calendar["totalContributions"]),
        "followers": int(user["followers"]["totalCount"]),
        "public_repos": int(user["repositories"]["totalCount"]),
    }


def get_profile_fallback() -> dict[str, Any]:
    # Used only if the API is temporarily unavailable. The workflow still remains healthy.
    today = dt.date.today()
    return {
        "days": [(today - dt.timedelta(days=i), 0) for i in range(365)],
        "total": 0,
        "followers": 0,
        "public_repos": 0,
    }


def get_events() -> list[dict[str, str]]:
    try:
        events = request_json(
            f"https://api.github.com/users/{urllib.parse.quote(USERNAME)}/events/public?per_page=10"
        )
    except Exception as exc:
        print(f"Activity API warning: {exc}")
        return []

    result: list[dict[str, str]] = []
    for event in events:
        kind = event.get("type", "Event")
        repo = event.get("repo", {}).get("name", "unknown/repository")
        payload = event.get("payload", {})
        created = event.get("created_at", "")
        date = created[:10] if created else ""

        icon = ">"
        action = "updated"
        detail = repo

        if kind == "PushEvent":
            icon = "$"
            size = int(payload.get("size", 0))
            action = f"pushed {size} commit" + ("" if size == 1 else "s")
            branch = payload.get("ref", "").split("/")[-1] or "branch"
            detail = f"{repo} / {branch}"
        elif kind == "CreateEvent":
            icon = "+"
            action = "created"
            detail = f"{repo} / {payload.get('ref_type', 'repository')}"
        elif kind == "PullRequestEvent":
            icon = "↗"
            action = payload.get("action", "updated") + " PR"
            detail = repo
        elif kind == "IssuesEvent":
            icon = "#"
            action = payload.get("action", "updated") + " issue"
            detail = repo
        elif kind == "IssueCommentEvent":
            icon = "%"
            action = "commented"
            detail = repo
        elif kind == "ReleaseEvent":
            icon = "*"
            action = "released"
            detail = repo
        elif kind == "ForkEvent":
            icon = "&"
            action = "forked"
            detail = repo
        elif kind == "WatchEvent":
            icon = "+"
            action = "starred"
            detail = repo
        elif kind == "DeleteEvent":
            icon = "-"
            action = "deleted"
            detail = f"{repo} / {payload.get('ref_type', 'ref')}"

        result.append(
            {
                "icon": icon,
                "action": action,
                "detail": detail,
                "date": date,
            }
        )
    return result[:5]


def streaks(days: list[tuple[dt.date, int]]) -> tuple[int, int]:
    by_day = {day: count for day, count in days}
    cursor = dt.date.today()
    current = 0
    if by_day.get(cursor, 0) == 0:
        cursor -= dt.timedelta(days=1)
    while by_day.get(cursor, 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)

    longest = 0
    run = 0
    for day, count in sorted(days):
        if count > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return current, longest


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


def load_font(size: int, bold: bool = False):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf",
        ] + FONT_CANDIDATES
    else:
        candidates = FONT_CANDIDATES
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def rgba(hex_color: str, alpha: int = 255):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def rounded_panel(draw: ImageDraw.ImageDraw, xy, fill=PANEL_2, outline=BORDER, radius=10, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def mono_text(draw, xy, text, size=12, fill=TEXT, bold=False, anchor=None):
    draw.text(
        xy,
        str(text),
        font=load_font(size, bold=bold),
        fill=fill,
        anchor=anchor,
    )


def truncate(text: str, max_chars: int) -> str:
    text = str(text)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def calendar_columns(days: list[tuple[dt.date, int]]):
    today = dt.date.today()
    data = {day: count for day, count in days}
    start = today - dt.timedelta(days=364)
    while start.weekday() != 6:
        start -= dt.timedelta(days=1)

    columns = []
    cursor = start
    while cursor <= today:
        column = []
        for row in range(7):
            day = cursor + dt.timedelta(days=row)
            if day <= today:
                column.append((day, data.get(day, 0)))
        columns.append(column)
        cursor += dt.timedelta(days=7)
    return columns[-53:]


def make_frame(
    days: list[tuple[dt.date, int]],
    total: int,
    current: int,
    longest: int,
    public_repos: int,
    events: list[dict[str, str]],
    frame_index: int,
):
    image = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
    draw = ImageDraw.Draw(image)

    # Ambient phosphor glow.
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((30, -120, 720, 600), fill=rgba(GREEN, 28))
    glow_draw.ellipse((610, 260, 1240, 760), fill=rgba(AMBER, 15))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(image)

    # Main chassis.
    draw.rounded_rectangle((10, 10, WIDTH - 10, HEIGHT - 10), radius=16, fill=BG, outline=BORDER, width=2)
    draw.rounded_rectangle((18, 18, WIDTH - 18, HEIGHT - 18), radius=12, outline="#172126", width=1)

    # CRT scanlines (static) + moving scan bar.
    for y in range(74, HEIGHT - 30, 18):
        draw.line((22, y, WIDTH - 22, y), fill=(17, 30, 27), width=1)
    scan_y = 78 + ((frame_index * 83) % (HEIGHT - 110))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((18, scan_y, WIDTH - 18, scan_y + 18), fill=rgba("#b9ffd0", 20))
    overlay = overlay.filter(ImageFilter.GaussianBlur(4))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    # Window titlebar.
    draw.rectangle((18, 18, WIDTH - 18, 66), fill="#080c0e")
    draw.line((18, 66, WIDTH - 18, 66), fill="#182127")
    for x, c in [(40, "#7b3f32"), (58, "#8b702e"), (76, "#3c774e")]:
        draw.ellipse((x - 5, 37, x + 5, 47), fill=c)
    mono_text(draw, (96, 42), "shabbir@github:~$ ./profile --live", size=15, fill=TEXT)
    mono_text(draw, (WIDTH - 38, 42), "CRT // PROFILE OS", size=10, fill=MUTED, anchor="ra")

    # Identity block.
    mono_text(draw, (38, 90), "$ whoami", size=11, fill=MUTED)
    mono_text(draw, (38, 123), "SHABBIR EZZY", size=29, fill=GREEN, bold=True)
    mono_text(draw, (38, 148), "FULL-STACK DEVELOPER  /  BUILDER  /  C++ + DSA", size=11, fill=TEXT)
    mono_text(draw, (38, 170), "Turning ideas into working products — one commit at a time.", size=10, fill=MUTED)

    # Focus chips.
    chips = [("BUILD", GREEN), ("LEARN", CYAN), ("SHIP", AMBER)]
    chip_x = 640
    for label, fill in chips:
        width = 94
        draw.rounded_rectangle((chip_x, 100, chip_x + width, 128), radius=8, fill="#0c1516", outline=BORDER_HI)
        mono_text(draw, (chip_x + width / 2, 114), label, size=10, fill=fill, bold=True, anchor="mm")
        chip_x += width + 10

    live_alpha = 255 if frame_index % 2 == 0 else 80
    draw.ellipse((1031, 102, 1040, 111), fill=rgba(GREEN, live_alpha))
    mono_text(draw, (1050, 110), "ONLINE", size=10, fill=GREEN, bold=True, anchor="lm")

    # Stats.
    stats = [
        (34, "CONTRIBUTIONS", f"{total:,}", "365 DAYS", AMBER),
        (316, "CURRENT STREAK", str(current), "DAYS", GREEN),
        (598, "LONGEST STREAK", str(longest), "DAYS", GREEN),
        (880, "PUBLIC REPOS", str(public_repos), "VISIBLE", CYAN),
    ]
    for x, label, value, tail, color in stats:
        rounded_panel(draw, (x, 193, x + 266, 258), fill=PANEL_2, outline=BORDER)
        mono_text(draw, (x + 16, 213), label, size=9.5, fill=MUTED)
        mono_text(draw, (x + 16, 244), value, size=26, fill=color, bold=True)
        mono_text(draw, (x + 250, 244), tail, size=8.5, fill=DIM, anchor="ra")

    # Contribution matrix panel.
    rounded_panel(draw, (34, 276, 770, 682), fill=PANEL_2, outline=BORDER)
    mono_text(draw, (54, 300), "CONTRIBUTION MATRIX", size=11, fill=MUTED)
    mono_text(draw, (750, 300), "ROLLING 365D", size=9, fill=DIM, anchor="ra")

    cols = calendar_columns(days)
    cell = 10
    gap = 3
    x0 = 54
    y0 = 334
    maximum = max((count for _, count in days), default=1)
    last_month = None

    for i, column in enumerate(cols):
        x = x0 + i * (cell + gap)
        if column:
            month = column[0][0].strftime("%b").upper()
            if month != last_month:
                mono_text(draw, (x, 319), month, size=8, fill=MUTED)
                last_month = month
        for row, (date_value, count) in enumerate(column):
            y = y0 + row * (cell + gap)
            color = CELL[level(count, maximum)]
            # Per-cell phase creates a natural shimmer across the grid.
            pulse = 0.0 if count == 0 else (0.12 + 0.12 * math.sin((frame_index * 0.9) + i * 0.35 + row * 0.75))
            if pulse > 0 and count > 0:
                base = tuple(int(color[j:j+2], 16) for j in (1,3,5))
                mix = tuple(min(255, int(v + 255 * pulse * 0.12)) for v in base)
                color = "#" + "".join(f"{v:02x}" for v in mix)
            draw.rounded_rectangle(
                (x, y, x + cell, y + cell),
                radius=2,
                fill=color,
                outline="#0c1214",
                width=1,
            )

    # Lower telemetry strip fills the quiet area under the 7-row calendar.
    rounded_panel(draw, (54, 500, 750, 628), fill="#081012", outline="#1b282d", radius=8)
    mono_text(draw, (70, 522), "BUILD QUEUE", size=9.5, fill=MUTED)
    mono_text(draw, (744, 522), "CURRENT FOCUS", size=8.5, fill=DIM, anchor="ra")
    queue = [
        ("01", "C++ / DSA", "ACTIVE", GREEN),
        ("02", "FULL-STACK", "SHIPPING", CYAN),
        ("03", "AI + IoT", "EXPLORING", AMBER),
    ]
    qx = 70
    for num, label, status, color in queue:
        draw.line((qx, 543, qx, 607), fill="#1d2a2f", width=1)
        mono_text(draw, (qx + 14, 553), num, size=8, fill=DIM)
        mono_text(draw, (qx + 36, 553), label, size=9.5, fill=TEXT, bold=True)
        mono_text(draw, (qx + 36, 574), status, size=8.5, fill=color)
        draw.line((qx + 36, 594, qx + 178, 594), fill="#162126", width=4)
        draw.line((qx + 36, 594, qx + 36 + (94 if num == "01" else 70 if num == "02" else 52), 594), fill=color, width=4)
        qx += 218

    # Legend and callout.
    mono_text(draw, (54, 657), "LESS", size=8.5, fill=MUTED)
    for idx, color in enumerate(CELL):
        x = 93 + idx * 16
        draw.rounded_rectangle((x, 648, x + 10, 658), radius=2, fill=color)
    mono_text(draw, (184, 657), "MORE", size=8.5, fill=MUTED)
    mono_text(draw, (750, 657), f"PEAK / DAY  {maximum}", size=8.5, fill=DIM, anchor="ra")

    # Activity stream panel.
    rounded_panel(draw, (822, 276, WIDTH - 34, 682), fill=PANEL_2, outline=BORDER)
    mono_text(draw, (844, 300), "ACTIVITY STREAM", size=11, fill=MUTED)
    mono_text(draw, (WIDTH - 54, 300), "PUBLIC EVENTS", size=8.5, fill=DIM, anchor="ra")
    draw.line((844, 311, WIDTH - 54, 311), fill="#1e292e")

    if not events:
        mono_text(draw, (844, 344), "no public events returned", size=10, fill=MUTED)
        mono_text(draw, (844, 365), "api may be rate-limited", size=9, fill=DIM)
    else:
        ys = [339, 397, 455, 513, 571]
        for idx, (event, y) in enumerate(zip(events, ys)):
            active = idx == (frame_index // 2) % len(events)
            marker_color = AMBER if active else DIM
            draw.rounded_rectangle((842, y - 15, 848, y + 19), radius=3, fill=marker_color)
            mono_text(draw, (860, y), event["icon"], size=13, fill=AMBER if active else GREEN, bold=True, anchor="lm")
            mono_text(draw, (882, y - 5), truncate(event["action"], 23), size=9.5, fill=TEXT, bold=active)
            mono_text(draw, (882, y + 14), truncate(event["detail"], 30), size=8.5, fill=GREEN)
            pretty_date = event["date"][5:] if len(event["date"]) == 10 else "--"
            mono_text(draw, (WIDTH - 54, y + 14), pretty_date, size=8, fill=DIM, anchor="ra")

    draw.line((844, 628, WIDTH - 54, 628), fill="#1e292e")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mono_text(draw, (844, 646), "$ sync", size=8.5, fill=MUTED)
    mono_text(draw, (886, 646), stamp, size=8.5, fill=DIM)
    mono_text(draw, (WIDTH - 54, 646), "github actions", size=8.5, fill=GREEN, anchor="ra")

    # Footer terminal line.
    mono_text(draw, (38, 703), 'shabbir@github:~$ echo "build quietly. keep shipping."', size=9.5, fill="#5f6e67")
    cursor_alpha = 255 if frame_index % 2 == 0 else 50
    draw.rectangle((369, 693, 374, 705), fill=rgba(AMBER, cursor_alpha))

    return image


def build_static_svg(
    days: list[tuple[dt.date, int]],
    total: int,
    current: int,
    longest: int,
    public_repos: int,
    events: list[dict[str, str]],
) -> str:
    cols = calendar_columns(days)
    maximum = max((count for _, count in days), default=1)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        '<defs>',
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">',
        '<stop offset="0" stop-color="#0a0e10"/>',
        '<stop offset="1" stop-color="#050708"/>',
        '</linearGradient>',
        '</defs>',
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="16" fill="{BLACK}"/>',
        f'<rect x="10" y="10" width="{WIDTH-20}" height="{HEIGHT-20}" rx="16" fill="url(#bg)" stroke="{BORDER}" stroke-width="2"/>',
        f'<rect x="18" y="18" width="{WIDTH-36}" height="{HEIGHT-36}" rx="12" fill="url(#bg)" stroke="#172126"/>',
        f'<rect x="18" y="18" width="{WIDTH-36}" height="48" fill="#080c0e"/>',
        '<circle cx="40" cy="42" r="5" fill="#7b3f32"/><circle cx="58" cy="42" r="5" fill="#8b702e"/><circle cx="76" cy="42" r="5" fill="#3c774e"/>',
        f'<text x="96" y="47" font-family="monospace" font-size="15" fill="{TEXT}">shabbir@github:~$ ./profile --live</text>',
        f'<text x="{WIDTH-38}" y="47" text-anchor="end" font-family="monospace" font-size="10" fill="{MUTED}">CRT // PROFILE OS</text>',
        f'<text x="38" y="90" font-family="monospace" font-size="11" fill="{MUTED}">$ whoami</text>',
        f'<text x="38" y="123" font-family="monospace" font-size="29" font-weight="700" fill="{GREEN}">SHABBIR EZZY</text>',
        f'<text x="38" y="148" font-family="monospace" font-size="11" fill="{TEXT}">FULL-STACK DEVELOPER  /  BUILDER  /  C++ + DSA</text>',
        f'<text x="38" y="170" font-family="monospace" font-size="10" fill="{MUTED}">Turning ideas into working products — one commit at a time.</text>',
    ]
    chip_x = 640
    for label, fill in [("BUILD", GREEN), ("LEARN", CYAN), ("SHIP", AMBER)]:
        out.append(f'<rect x="{chip_x}" y="100" width="94" height="28" rx="8" fill="#0c1516" stroke="{BORDER_HI}"/>')
        out.append(f'<text x="{chip_x+47}" y="118" text-anchor="middle" font-family="monospace" font-size="10" font-weight="700" fill="{fill}">{label}</text>')
        chip_x += 104
    out.append(f'<circle cx="1036" cy="106" r="4.5" fill="{GREEN}"/>')
    out.append(f'<text x="1050" y="110" font-family="monospace" font-size="10" font-weight="700" fill="{GREEN}">ONLINE</text>')

    stats = [
        (34, "CONTRIBUTIONS", f"{total:,}", "365 DAYS", AMBER),
        (316, "CURRENT STREAK", str(current), "DAYS", GREEN),
        (598, "LONGEST STREAK", str(longest), "DAYS", GREEN),
        (880, "PUBLIC REPOS", str(public_repos), "VISIBLE", CYAN),
    ]
    for x, label, value, tail, fill in stats:
        out.extend([
            f'<rect x="{x}" y="193" width="266" height="65" rx="10" fill="{PANEL_2}" stroke="{BORDER}"/>',
            f'<text x="{x+16}" y="213" font-family="monospace" font-size="9.5" fill="{MUTED}">{label}</text>',
            f'<text x="{x+16}" y="244" font-family="monospace" font-size="26" font-weight="700" fill="{fill}">{esc(value)}</text>',
            f'<text x="{x+250}" y="244" text-anchor="end" font-family="monospace" font-size="8.5" fill="{DIM}">{tail}</text>',
        ])

    out += [
        f'<rect x="34" y="276" width="736" height="406" rx="10" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="54" y="300" font-family="monospace" font-size="11" fill="{MUTED}">CONTRIBUTION MATRIX</text>',
        f'<text x="750" y="300" text-anchor="end" font-family="monospace" font-size="9" fill="{DIM}">ROLLING 365D</text>',
    ]
    x0, y0, cell, gap = 54, 334, 10, 3
    last_month = None
    for i, col in enumerate(cols):
        x = x0 + i * (cell + gap)
        if col:
            month = col[0][0].strftime("%b").upper()
            if month != last_month:
                out.append(f'<text x="{x}" y="319" font-family="monospace" font-size="8" fill="{MUTED}">{month}</text>')
                last_month = month
        for row, (day, count) in enumerate(col):
            y = y0 + row * (cell + gap)
            fill = CELL[level(count, maximum)]
            out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{fill}" stroke="#0c1214" stroke-width="1"><title>{esc(day.isoformat())} · {count} contributions</title></rect>')
    out.extend([
        f'<rect x="54" y="500" width="696" height="128" rx="8" fill="#081012" stroke="#1b282d"/>',
        f'<text x="70" y="522" font-family="monospace" font-size="9.5" fill="{MUTED}">BUILD QUEUE</text>',
        f'<text x="744" y="522" text-anchor="end" font-family="monospace" font-size="8.5" fill="{DIM}">CURRENT FOCUS</text>',
        f'<line x1="70" y1="543" x2="70" y2="607" stroke="#1d2a2f"/>',
        f'<text x="84" y="556" font-family="monospace" font-size="8" fill="{DIM}">01</text>',
        f'<text x="106" y="556" font-family="monospace" font-size="9.5" font-weight="700" fill="{TEXT}">C++ / DSA</text>',
        f'<text x="106" y="577" font-family="monospace" font-size="8.5" fill="{GREEN}">ACTIVE</text>',
        f'<line x1="106" y1="594" x2="284" y2="594" stroke="#162126" stroke-width="4"/>',
        f'<line x1="106" y1="594" x2="200" y2="594" stroke="{GREEN}" stroke-width="4"/>',
        f'<line x1="288" y1="543" x2="288" y2="607" stroke="#1d2a2f"/>',
        f'<text x="302" y="556" font-family="monospace" font-size="8" fill="{DIM}">02</text>',
        f'<text x="324" y="556" font-family="monospace" font-size="9.5" font-weight="700" fill="{TEXT}">FULL-STACK</text>',
        f'<text x="324" y="577" font-family="monospace" font-size="8.5" fill="{CYAN}">SHIPPING</text>',
        f'<line x1="324" y1="594" x2="502" y2="594" stroke="#162126" stroke-width="4"/>',
        f'<line x1="324" y1="594" x2="394" y2="594" stroke="{CYAN}" stroke-width="4"/>',
        f'<line x1="506" y1="543" x2="506" y2="607" stroke="#1d2a2f"/>',
        f'<text x="520" y="556" font-family="monospace" font-size="8" fill="{DIM}">03</text>',
        f'<text x="542" y="556" font-family="monospace" font-size="9.5" font-weight="700" fill="{TEXT}">AI + IOT</text>',
        f'<text x="542" y="577" font-family="monospace" font-size="8.5" fill="{AMBER}">EXPLORING</text>',
        f'<line x1="542" y1="594" x2="720" y2="594" stroke="#162126" stroke-width="4"/>',
        f'<line x1="542" y1="594" x2="594" y2="594" stroke="{AMBER}" stroke-width="4"/>',
        f'<text x="54" y="657" font-family="monospace" font-size="8.5" fill="{MUTED}">LESS</text>',
        *[
            f'<rect x="{93 + i*16}" y="648" width="10" height="10" rx="2" fill="{c}"/>'
            for i, c in enumerate(CELL)
        ],
        f'<text x="184" y="657" font-family="monospace" font-size="8.5" fill="{MUTED}">MORE</text>',
        f'<text x="750" y="657" text-anchor="end" font-family="monospace" font-size="8.5" fill="{DIM}">PEAK / DAY {maximum}</text>',
        f'<rect x="822" y="276" width="{WIDTH-856}" height="406" rx="10" fill="{PANEL_2}" stroke="{BORDER}"/>',
        f'<text x="844" y="300" font-family="monospace" font-size="11" fill="{MUTED}">ACTIVITY STREAM</text>',
        f'<text x="{WIDTH-54}" y="300" text-anchor="end" font-family="monospace" font-size="8.5" fill="{DIM}">PUBLIC EVENTS</text>',
        f'<line x1="844" y1="311" x2="{WIDTH-54}" y2="311" stroke="#1e292e"/>',
    ])

    ys = [339, 397, 455, 513, 571]
    if not events:
        out.append(f'<text x="844" y="344" font-family="monospace" font-size="10" fill="{MUTED}">no public events returned</text>')
        out.append(f'<text x="844" y="365" font-family="monospace" font-size="9" fill="{DIM}">api may be rate-limited</text>')
    else:
        for event, y in zip(events, ys):
            out.extend([
                f'<rect x="842" y="{y-15}" width="6" height="34" rx="3" fill="{DIM}"/>',
                f'<text x="860" y="{y+4}" font-family="monospace" font-size="13" font-weight="700" fill="{GREEN}">{esc(event["icon"])}</text>',
                f'<text x="882" y="{y}" font-family="monospace" font-size="9.5" fill="{TEXT}">{esc(truncate(event["action"], 23))}</text>',
                f'<text x="882" y="{y+19}" font-family="monospace" font-size="8.5" fill="{GREEN}">{esc(truncate(event["detail"], 30))}</text>',
                f'<text x="{WIDTH-54}" y="{y+19}" text-anchor="end" font-family="monospace" font-size="8" fill="{DIM}">{esc(event["date"][5:] if len(event["date"]) == 10 else "--")}</text>',
            ])
    out += [
        f'<line x1="844" y1="628" x2="{WIDTH-54}" y2="628" stroke="#1e292e"/>',
        f'<text x="844" y="646" font-family="monospace" font-size="8.5" fill="{MUTED}">$ sync</text>',
        f'<text x="886" y="646" font-family="monospace" font-size="8.5" fill="{DIM}">{esc(dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}</text>',
        f'<text x="{WIDTH-54}" y="646" text-anchor="end" font-family="monospace" font-size="8.5" fill="{GREEN}">github actions</text>',
        f'<text x="38" y="703" font-family="monospace" font-size="9.5" fill="#5f6e67">shabbir@github:~$ echo "build quietly. keep shipping."</text>',
        '</svg>',
    ]
    return "\n".join(out)


def main() -> None:
    try:
        profile = get_profile_data()
        print(
            f"Fetched GitHub data: {profile['total']} contributions, "
            f"{profile['public_repos']} public repos"
        )
    except Exception as exc:
        print(f"Contribution API warning: {exc}")
        profile = get_profile_fallback()

    days = profile["days"]
    total = profile["total"]
    current, longest = streaks(days)
    events = get_events()

    os.makedirs("assets", exist_ok=True)

    # Static fallback: GitHub renders SVG, but does not run SVG animation.
    with open(SVG_OUTPUT, "w", encoding="utf-8") as handle:
        handle.write(
            build_static_svg(days, total, current, longest, profile["public_repos"], events)
        )

    frames = [
        make_frame(
            days,
            total,
            current,
            longest,
            profile["public_repos"],
            events,
            frame_index,
        )
        for frame_index in range(FRAMES)
    ]
    frames[0].save(
        GIF_OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=450,
        loop=0,
        optimize=True,
        disposal=2,
    )

    print(f"Wrote {SVG_OUTPUT}")
    print(f"Wrote {GIF_OUTPUT}")


if __name__ == "__main__":
    main()
