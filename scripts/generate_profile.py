from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import requests

USERNAME = os.environ.get("GH_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER") or "Shabbir-369"
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
API_URL = "https://api.github.com/graphql"
FONT = "Consolas, Monaco, 'Courier New', monospace"
OUT_DIR = Path("assets")

THEMES = {
    "dark": {
        "bg": "#050706", "panel": "#0a100e", "panel2": "#0d1512", "border": "#20382c",
        "text": "#d7ffe5", "muted": "#6a8978", "soft": "#98bca7", "green": "#42ff8b",
        "green2": "#1bbf67", "cyan": "#6ee7d1", "amber": "#ffc857", "danger": "#ff6b6b",
        "grid": "#10231a", "level": ["#0c1511", "#12311f", "#1a6b3b", "#2ebf68", "#42ff8b"],
    },
    "light": {
        "bg": "#f7f9f7", "panel": "#ffffff", "panel2": "#f1f5f2", "border": "#cbd7cf",
        "text": "#183125", "muted": "#6a7d73", "soft": "#40594d", "green": "#137a45",
        "green2": "#1d9a58", "cyan": "#22746a", "amber": "#8d5d00", "danger": "#b33a3a",
        "grid": "#e3ebe6", "level": ["#eef3ef", "#d7eadc", "#a8d6b5", "#65b47f", "#25824d"],
    },
}

PROFILE = {
    "name": "Shabbir Ezzy",
    "headline": "BTech IT student · Full-stack builder · C++ / DSA · AI / IoT",
    "status": "BUILDING · LEARNING · SHIPPING",
    "about": [
        "I like taking an idea from a blank file to something real.",
        "Mostly full-stack, sometimes embedded, always curious about what is underneath.",
    ],
    "focus": ["C++ + DSA", "CS fundamentals", "Full-stack systems", "AI / IoT"],
    "links": [
        ("github", "https://github.com/Shabbir-369"),
        ("linkedin", "https://www.linkedin.com/in/shabbir-ezzy/"),
        ("email", "mailto:codewithshabbir@gmail.com"),
    ],
}

FEATURED = [
    ("project-pulse-ai", "Project Pulse AI", "AI execution intelligence for infrastructure projects.", "React · Node.js · AI · Graph/CPM"),
    ("agrisense", "AgriSense", "IoT + AI agriculture monitoring and prediction platform.", "ESP32 · React · Node.js · AI"),
    ("practice-ledger", "Practice Ledger", "Focused DSA tracker with curriculum, sessions and immutable logs.", "React · Firebase · JavaScript"),
    ("ezzy-hardware", "Ezzy Hardware", "Modern product discovery and WhatsApp checkout flow for a hardware business.", "React · Node.js · JavaScript"),
]

CONTRIB_QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    followers { totalCount }
    following { totalCount }
    repositories(first:100, ownerAffiliations:[OWNER], privacy:PUBLIC, isFork:false) {
      totalCount
      nodes {
        name
        stargazerCount
        isArchived
        primaryLanguage { name }
        languages(first:8, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name } }
        }
      }
    }
    contributionsCollection(from:$from, to:$to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def xml_text(value: object) -> str:
    return esc(value).replace("\u2014", "-").replace("\u2013", "-")


def iso_utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def query_github(from_ts: str, to_ts: str, token: str) -> dict:
    response = requests.post(
        API_URL,
        json={"query": CONTRIB_QUERY, "variables": {"login": USERNAME, "from": from_ts, "to": to_ts}},
        headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    user = payload.get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub returned no user data.")
    return user


def collect_live_data(token: str) -> dict:
    end = iso_utc_now()
    start = end - dt.timedelta(days=365)
    user = query_github(start.isoformat(), end.isoformat(), token)
    calendar = user["contributionsCollection"]["contributionCalendar"]
    day_map = {}
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            day_map[day["date"]] = int(day["contributionCount"])

    repos = [r for r in user["repositories"]["nodes"] if r and not r.get("isArchived")]
    language_bytes = Counter()
    for repo in repos:
        for edge in repo.get("languages", {}).get("edges", []):
            name = edge["node"]["name"]
            language_bytes[name] += int(edge.get("size", 0))

    latest = sorted(day_map.items())[-31:]
    active_31 = [(d, n) for d, n in latest if n]
    total_31 = sum(n for _, n in latest)
    total_7 = sum(n for _, n in latest[-7:])
    peak = max(latest, key=lambda x: x[1]) if latest else ("-", 0)

    return {
        "sync_utc": end.strftime("%Y-%m-%d %H:%M UTC"),
        "year_start": start.strftime("%Y-%m-%d"),
        "year_end": end.strftime("%Y-%m-%d"),
        "contributions": int(calendar["totalContributions"]),
        "days": day_map,
        "followers": int(user["followers"]["totalCount"]),
        "following": int(user["following"]["totalCount"]),
        "repos": int(user["repositories"]["totalCount"]),
        "stars": sum(int(r.get("stargazerCount", 0)) for r in repos),
        "commits": int(user["contributionsCollection"]["totalCommitContributions"]),
        "issues": int(user["contributionsCollection"]["totalIssueContributions"]),
        "prs": int(user["contributionsCollection"]["totalPullRequestContributions"]),
        "reviews": int(user["contributionsCollection"]["totalPullRequestReviewContributions"]),
        "active_31": len(active_31),
        "sum_31": total_31,
        "sum_7": total_7,
        "peak_day": peak,
        "languages": [name for name, _ in language_bytes.most_common(8)],
    }


def bootstrap_data() -> dict:
    today = iso_utc_now().date()
    days = {}
    for i in range(365):
        d = today - dt.timedelta(days=364 - i)
        days[d.isoformat()] = 0
    return {
        "sync_utc": "WAITING FOR FIRST LIVE SYNC",
        "year_start": (today - dt.timedelta(days=364)).isoformat(),
        "year_end": today.isoformat(),
        "contributions": None, "days": days,
        "followers": None, "following": None, "repos": None, "stars": None,
        "commits": None, "issues": None, "prs": None, "reviews": None,
        "active_31": None, "sum_31": None, "sum_7": None,
        "peak_day": ("--", 0), "languages": [],
    }


def demo_data() -> dict:
    today = iso_utc_now().date()
    days = {}
    for i in range(365):
        d = today - dt.timedelta(days=364 - i)
        # A deterministic visual demo, replaced on the first real workflow run.
        n = ((i * 17 + 3) % 19) if (i % 9 not in {0, 1, 2}) else 0
        if i % 37 == 0:
            n = 11
        days[d.isoformat()] = n
    return {
        "sync_utc": "DEMO PREVIEW - first workflow run replaces this",
        "year_start": (today - dt.timedelta(days=364)).isoformat(),
        "year_end": today.isoformat(),
        "contributions": sum(days.values()), "days": days,
        "followers": 1, "following": 2, "repos": 6, "stars": 0,
        "commits": sum(days.values()), "issues": 0, "prs": 0, "reviews": 0,
        "active_31": sum(1 for n in list(days.values())[-31:] if n),
        "sum_31": sum(list(days.values())[-31:]), "sum_7": sum(list(days.values())[-7:]),
        "peak_day": max(days.items(), key=lambda x: x[1]),
        "languages": ["JavaScript", "C++", "Python", "TypeScript", "HTML", "CSS"],
    }


def compute_streaks(days: dict[str, int]) -> tuple[int, int, str | None, str | None]:
    today = iso_utc_now().date()
    current = 0
    cursor = today
    if days.get(cursor.isoformat(), 0) == 0:
        cursor -= dt.timedelta(days=1)
    while days.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)

    longest = 0
    run = 0
    best_start = best_end = None
    prev = None
    for date_str in sorted(days):
        d = dt.date.fromisoformat(date_str)
        if days[date_str] > 0 and prev is not None and (d - prev).days == 1:
            run += 1
        elif days[date_str] > 0:
            run = 1
            run_start = d
        else:
            run = 0
            run_start = None
        if run > longest:
            longest = run
            best_start, best_end = run_start, d
        prev = d if days[date_str] > 0 else None
    return current, longest, best_start.isoformat() if best_start else None, best_end.isoformat() if best_end else None


def canvas(theme: dict, width: int, height: int, title: str) -> list[str]:
    out = []
    out.append(f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">')
    out.append('<defs>')
    out.append(f'<filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
    out.append(f'<pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="{theme["green"]}" opacity="0.045"/></pattern>')
    out.append('</defs>')
    out.append(f'<rect width="{width}" height="{height}" rx="12" fill="{theme["bg"]}"/>')
    out.append(f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="11" fill="none" stroke="{theme["border"]}"/>')
    out.append(f'<rect width="{width}" height="40" rx="12" fill="{theme["panel"]}"/>')
    out.append(f'<rect y="28" width="{width}" height="12" fill="{theme["panel"]}"/>')
    out.append('<circle cx="18" cy="20" r="5" fill="#ff5f56"/><circle cx="36" cy="20" r="5" fill="#ffbd2e"/><circle cx="54" cy="20" r="5" fill="#27c93f"/>')
    out.append(f'<text x="76" y="25" font-family="{FONT}" font-size="12" fill="{theme["muted"]}">{xml_text(title)}</text>')
    out.append(f'<line x1="0" y1="40" x2="{width}" y2="40" stroke="{theme["border"]}"/>')
    return out


def txt(x: float, y: float, text: str, color: str, size: int = 12, weight: str = "400", anchor: str = "start", opacity: float = 1) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-family="{FONT}" font-size="{size}px" font-weight="{weight}" fill="{color}" opacity="{opacity}">{xml_text(text)}</text>'


def rect(x, y, w, h, fill, rx=2, stroke=None, sw=1, opacity=1):
    extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" opacity="{opacity}"{extra}/>'


def display(value, fallback="--"):
    return fallback if value is None else f"{value:,}" if isinstance(value, int) else str(value)


def render_terminal(theme_name: str, d: dict) -> str:
    t = THEMES[theme_name]; w, h = 1000, 620; p = canvas(t, w, h, "shabbir-369@github:~$ ./profile --mode=live")
    p += [txt(28, 72, "$ whoami", t["soft"], 13), txt(28, 101, PROFILE["name"], t["green"], 22, "700"),
          txt(250, 100, PROFILE["headline"], t["text"], 12), txt(28, 127, PROFILE["status"], t["amber"], 10, "700")]
    p += [txt(28, 157, "$ cat about.md", t["soft"], 13), txt(28, 183, PROFILE["about"][0], t["muted"], 12), txt(28, 204, PROFILE["about"][1], t["muted"], 12)]

    p += [txt(28, 242, "$ uptime --live", t["soft"], 13)]
    stats = [
        (display(d["contributions"]), "contrib / 365d", t["green"]),
        (display(d["current_streak"]), "current streak", t["amber"]),
        (display(d["repos"]), "public repos", t["cyan"]),
        (display(d["followers"]), "followers", t["green"]),
        (display(d["prs"]), "pull requests", t["cyan"]),
    ]
    sx = 28; sy = 263; cw = 184
    for i, (val, label, color) in enumerate(stats):
        x = sx + i * cw
        p.append(rect(x, sy, cw - 10, 86, t["panel2"], 7, t["border"]))
        p.append(txt(x + 12, sy + 34, val, color, 25, "700"))
        p.append(txt(x + 12, sy + 56, label, t["soft"], 10))
        p.append(txt(x + 12, sy + 73, "LIVE", t["muted"], 8, "700"))

    p += [txt(28, 381, "$ focus --now", t["soft"], 13)]
    for i, item in enumerate(PROFILE["focus"]):
        x = 28 + i * 235
        p.append(rect(x, 399, 215, 34, t["panel2"], 6, t["border"]))
        p.append(txt(x + 12, 421, f"[{i+1:02d}] {item}", t["green" if i == 0 else "text"], 11, "700" if i == 0 else "400"))

    p += [txt(28, 471, "$ sync --status", t["soft"], 13)]
    p += [txt(28, 495, "[ OK ]", t["green"], 11, "700"), txt(82, 495, "GitHub GraphQL source configured", t["text"], 11),
          txt(28, 518, "[ OK ]", t["green"], 11, "700"), txt(82, 518, "theme-aware light / dark render", t["text"], 11),
          txt(28, 541, "[ OK ]", t["green"], 11, "700"), txt(82, 541, "refresh interval: 15 minutes", t["text"], 11)]
    p += [txt(28, 577, f"last_sync: {d['sync_utc']}", t["muted"], 10), txt(760, 577, "guest@shabbir-369:~$ _", t["soft"], 12)]
    p += [f'<rect width="{w}" height="{h}" fill="url(#scan)"/>', '</svg>']
    return "\n".join(p)


def build_grid(days: dict[str, int]) -> tuple[list[list[tuple[str,int]]], dt.date, dt.date]:
    keys = sorted(days)
    first = dt.date.fromisoformat(keys[0]); last = dt.date.fromisoformat(keys[-1])
    # Sunday-start grid, matching GitHub's calendar orientation.
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    end = last + dt.timedelta(days=(6 - ((last.weekday() + 1) % 7)))
    weeks = []
    cur = start
    while cur <= end:
        week = []
        for offset in range(7):
            day = cur + dt.timedelta(days=offset)
            week.append((day.isoformat(), days.get(day.isoformat(), 0)))
        weeks.append(week)
        cur += dt.timedelta(days=7)
    return weeks, start, end


def level_for(n: int, max_n: int) -> int:
    if n <= 0: return 0
    if max_n <= 4: return min(4, n)
    if n >= max_n: return 4
    q = n / max_n
    return 1 if q <= .25 else 2 if q <= .5 else 3


def render_contrib(theme_name: str, d: dict) -> str:
    t = THEMES[theme_name]; w, h = 1000, 310; p = canvas(t, w, h, f"shabbir-369@github:~$ git log --calendar --365d")
    weeks, start, end = build_grid(d["days"])
    max_n = max(d["days"].values() or [1])
    cell = 12; gap = 3; left = 58; top = 86
    # weekday labels
    for label, row in [("Mon",1),("Wed",3),("Fri",5)]: p.append(txt(28, top + row*(cell+gap)+10, label, t["muted"], 9))
    # month labels based on first visible occurrence
    seen = set()
    for i, week in enumerate(weeks):
        x = left + i*(cell+gap)
        for date_str, _ in week:
            d0 = dt.date.fromisoformat(date_str)
            if d0.day <= 7:
                key = (d0.year, d0.month)
                if key not in seen:
                    seen.add(key); p.append(txt(x, top - 10, d0.strftime("%b").upper(), t["muted"], 9, "700"))
                break
        for row, (date_str, count) in enumerate(week):
            y = top + row*(cell+gap)
            lev = level_for(count, max_n)
            tooltip = f"{count} contribution{'s' if count != 1 else ''} on {date_str}"
            # title element for native hover tooltip in SVG viewers
            p.append(f'<g>{rect(x,y,cell,cell,t["level"][lev],3, t["border"], .4)}<title>{esc(tooltip)}</title></g>')
    # legend
    ly = 192 + 76
    p.append(txt(left, ly, "LESS", t["muted"], 9, "700"))
    for i, color in enumerate(t["level"]): p.append(rect(left+35+i*17, ly-9, 12, 12, color, 2, t["border"], .4))
    p.append(txt(left+130, ly, "MORE", t["muted"], 9, "700"))
    p += [txt(28, 253, "$ summary --year", t["soft"], 12)]
    total_label = display(d["contributions"]) if d["contributions"] is not None else "waiting for live sync"
    p += [txt(28, 276, f"{total_label} total contributions" if d["contributions"] is not None else total_label, t["green"], 13, "700"),
          txt(248, 276, f"peak day: {d['peak_day'][0]} · {d['peak_day'][1]}", t["text"], 11),
          txt(560, 276, f"range: {d['year_start']} → {d['year_end']}", t["muted"], 10)]
    p += ['<rect x="0" y="0" width="1000" height="310" fill="url(#scan)"/>', '</svg>']
    return "\n".join(p)


def render_activity(theme_name: str, d: dict) -> str:
    t = THEMES[theme_name]; w,h = 1000, 360; p = canvas(t,w,h,f"shabbir-369@github:~$ git log --pulse --last=31d")
    latest = sorted(d["days"].items())[-31:]
    values = [n for _, n in latest]; max_n = max(values or [1])
    chart_x, chart_y, chart_w, chart_h = 48, 86, 710, 190
    # grid
    for i in range(5):
        yy = chart_y + i*(chart_h/4)
        p.append(f'<line x1="{chart_x}" y1="{yy:.1f}" x2="{chart_x+chart_w}" y2="{yy:.1f}" stroke="{t["grid"]}" stroke-width="1"/>')
    p.append(txt(chart_x, 68, f"{sum(values)} contributions across the last 31 days" if d["sum_31"] is not None else "waiting for live contribution data", t["soft"], 11))
    points=[]
    bw = chart_w / 31
    for i, (date_str, val) in enumerate(latest):
        x = chart_x + i*bw + 2
        bh = (val/max_n)*chart_h if max_n else 0
        y = chart_y + chart_h - bh
        color = t["level"][level_for(val,max_n)]
        p.append(rect(x,y,max(7,bw-4),bh,color,3, t["border"], .4))
        px = chart_x + i*bw + bw/2; py = chart_y + chart_h - ((val/max_n)*chart_h if max_n else 0)
        points.append((px,py))
        if i in {0,6,13,20,27,30}: p.append(txt(px, chart_y+chart_h+20, dt.date.fromisoformat(date_str).strftime("%d %b"), t["muted"], 8, "700", "middle"))
    if points:
        path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x,y in points)
        p.append(f'<path d="{path}" fill="none" stroke="{t["green"]}" stroke-width="2" opacity=".9"/>')
        for x,y in points[::4]: p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="{t["green"]}"/>')

    rx=786; p.append(rect(rx,86,184,190,t["panel2"],8,t["border"]))
    p += [txt(rx+16,112,"TELEMETRY",t["muted"],9,"700"), txt(rx+16,143,display(d["sum_7"]),t["green"],24,"700"), txt(rx+16,160,"last 7 days",t["soft"],9),
          txt(rx+16,192,display(d["sum_31"]),t["cyan"],24,"700"), txt(rx+16,209,"last 31 days",t["soft"],9),
          txt(rx+16,241,str(d["peak_day"][1]),t["amber"],18,"700"), txt(rx+65,241,"peak/day",t["soft"],9)]
    status = "status: LIVE DATA" if d["sum_31"] is not None else "status: WAITING FOR FIRST SYNC"
    p += [txt(28,329,"$ activity --source=github",t["muted"],10), txt(760,329,status,t["green" if d["sum_31"] is not None else "amber"],10,"700")]
    p += ['<rect x="0" y="0" width="1000" height="360" fill="url(#scan)"/>','</svg>']
    return "\n".join(p)


def render_projects(theme_name: str, d: dict) -> str:
    t = THEMES[theme_name]; w,h = 1000, 470; p = canvas(t,w,h,f"shabbir-369@github:~$ ls -la ~/projects && cat stack.txt")
    p += [txt(28,72,"$ ls -la ~/projects",t["soft"],13)]
    y=100
    for i,(slug,name,desc,stack) in enumerate(FEATURED):
        p.append(rect(28,y-18,944,61,t["panel2"],7,t["border"]))
        p.append(txt(44,y, f"{i+1:02d}", t["muted"], 10,"700"))
        p.append(txt(82,y,name,t["green"],12,"700"))
        p.append(txt(295,y,desc,t["text"],10))
        p.append(txt(82,y+20,stack,t["muted"],9))
        p.append(txt(900,y+20,"FEATURED",t["cyan"],8,"700","end"))
        y += 69
    p += [txt(28,397,"$ stack --top",t["soft"],13)]
    langs = d["languages"][:8] or ["waiting-for-live-sync"]
    for i,name in enumerate(langs):
        col=i%4; row=i//4; x=28+col*235; yy=417+row*22
        p.append(rect(x,yy-13,215,18,t["panel2"],5,t["border"]))
        p.append(txt(x+10,yy,name.lower(),t["soft"],9,"700"))
    p += ['<rect x="0" y="0" width="1000" height="470" fill="url(#scan)"/>','</svg>']
    return "\n".join(p)


def write_assets(data: dict):
    OUT_DIR.mkdir(exist_ok=True)
    for theme in THEMES:
        (OUT_DIR/f"profile-{theme}.svg").write_text(render_terminal(theme,data), encoding="utf-8")
        (OUT_DIR/f"contributions-{theme}.svg").write_text(render_contrib(theme,data), encoding="utf-8")
        (OUT_DIR/f"activity-{theme}.svg").write_text(render_activity(theme,data), encoding="utf-8")
        (OUT_DIR/f"projects-{theme}.svg").write_text(render_projects(theme,data), encoding="utf-8")
    (OUT_DIR/"profile-data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="Generate local preview without GitHub access.")
    ap.add_argument("--bootstrap", action="store_true", help="Generate honest empty assets before the first live sync.")
    args = ap.parse_args()
    if args.demo:
        data = demo_data()
    elif args.bootstrap:
        data = bootstrap_data()
    else:
        if not TOKEN:
            sys.exit("No GitHub token available. Use --demo locally or provide GITHUB_TOKEN/ACCESS_TOKEN in Actions.")
        data = collect_live_data(TOKEN)
    current, longest, longest_start, longest_end = compute_streaks(data["days"])
    data["current_streak"] = current
    data["longest_streak"] = longest
    data["longest_range"] = f"{longest_start} → {longest_end}" if longest_start else "-"
    write_assets(data)
    print(json.dumps({"contributions": data["contributions"], "current_streak": current, "longest_streak": longest, "repos": data["repos"], "sync_utc": data["sync_utc"]}, indent=2))


if __name__ == "__main__":
    main()
