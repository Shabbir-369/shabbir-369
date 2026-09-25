"""
Generates assets/dashboard-dark.svg and assets/dashboard-light.svg from live
GitHub contribution data, styled as a retro terminal / CRT panel.

Run by .github/workflows/dashboard.yml on a daily schedule. Needs a token
with read access to public data — the Action's default GITHUB_TOKEN works;
if it doesn't for your account, add a classic Personal Access Token (no
scopes required) as a repo secret named ACCESS_TOKEN and it'll be preferred.
"""

import datetime
import os
import sys

import requests

GITHUB_USERNAME = os.environ.get("GH_USERNAME") or os.environ.get("GITHUB_REPOSITORY_OWNER")
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")

if not GITHUB_USERNAME:
    sys.exit("GH_USERNAME is not set")
if not TOKEN:
    sys.exit("No GitHub token available (set ACCESS_TOKEN or GITHUB_TOKEN)")

API_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"bearer {TOKEN}"}

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
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


def run_query(login, start, end):
    variables = {"login": login, "from": start, "to": end}
    resp = requests.post(
        API_URL, json={"query": QUERY, "variables": variables}, headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]["user"]


def fetch_all_days(login):
    """The API only returns 1 year per call, so walk back year by year to createdAt."""
    now = datetime.datetime.utcnow()
    first = run_query(
        login,
        (now - datetime.timedelta(days=365)).isoformat() + "Z",
        now.isoformat() + "Z",
    )
    created_at = datetime.datetime.strptime(first["createdAt"][:19], "%Y-%m-%dT%H:%M:%S")

    all_days = {}
    total_contributions = 0
    cursor_end = now

    while cursor_end > created_at:
        cursor_start = max(created_at, cursor_end - datetime.timedelta(days=365))
        chunk = run_query(login, cursor_start.isoformat() + "Z", cursor_end.isoformat() + "Z")
        calendar = chunk["contributionsCollection"]["contributionCalendar"]
        total_contributions += calendar["totalContributions"]
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                all_days[day["date"]] = day["contributionCount"]
        cursor_end = cursor_start - datetime.timedelta(days=1)

    return total_contributions, all_days, created_at


def compute_streaks(all_days):
    dates_sorted = sorted(all_days.keys())
    today = datetime.date.today()

    current_streak = 0
    d = today
    while all_days.get(d.isoformat(), 0) > 0:
        current_streak += 1
        d -= datetime.timedelta(days=1)

    longest_streak, longest_start, longest_end = 0, None, None
    run_len, run_start, prev_date = 0, None, None

    for date_str in dates_sorted:
        count = all_days[date_str]
        d_obj = datetime.date.fromisoformat(date_str)
        if count > 0:
            if prev_date is not None and (d_obj - prev_date).days == 1:
                run_len += 1
            else:
                run_len = 1
                run_start = d_obj
            if run_len > longest_streak:
                longest_streak, longest_start, longest_end = run_len, run_start, d_obj
            prev_date = d_obj
        else:
            prev_date = None
            run_len = 0

    return current_streak, longest_streak, longest_start, longest_end


def fmt(d):
    return d.strftime("%b %d, %Y") if d else "-"


# ---- terminal / CRT styling ------------------------------------------------

THEMES = {
    "dark": dict(
        bg="#050a08",
        chrome_bg="#0a1210",
        border="#1c3a2c",
        text_dim="#4f7a63",
        text_mid="#8fd8ab",
        green="#39ff88",
        amber="#ffb454",
        scan="rgba(120,255,170,0.05)",
        vignette=0.4,
        glow=3.2,
    ),
    "light": dict(
        bg="#f6f8fa",
        chrome_bg="#eaeef2",
        border="#c9d1d9",
        text_dim="#6e7781",
        text_mid="#3d4b42",
        green="#166e34",
        amber="#8a5a00",
        scan="rgba(27,31,36,0.035)",
        vignette=0.08,
        glow=1.2,
    ),
}

SVG_TEMPLATE = """<svg width="760" height="224" viewBox="0 0 760 224" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="{glow}" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    <pattern id="scan" width="3" height="3" patternUnits="userSpaceOnUse">
      <rect width="3" height="1" fill="{scan}" />
    </pattern>
    <radialGradient id="vignette" cx="50%" cy="45%" r="75%">
      <stop offset="55%" stop-color="#000000" stop-opacity="0" />
      <stop offset="100%" stop-color="#000000" stop-opacity="{vignette}" />
    </radialGradient>
    <clipPath id="card-clip">
      <rect x="0.5" y="0.5" width="759" height="223" rx="10" />
    </clipPath>
  </defs>

  <g clip-path="url(#card-clip)">
    <rect x="0" y="0" width="760" height="224" fill="{bg}" />

    <!-- title bar -->
    <rect x="0" y="0" width="760" height="32" fill="{chrome_bg}" />
    <circle cx="18" cy="16" r="5" fill="#ff5f56" />
    <circle cx="36" cy="16" r="5" fill="#ffbd2e" />
    <circle cx="54" cy="16" r="5" fill="#27c93f" />
    <text x="78" y="20" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="12" fill="{text_dim}">{user}@github:~$ ./analytics.sh --live</text>
    <line x1="0" y1="32" x2="760" y2="32" stroke="{border}" stroke-width="1" />

    <!-- stats -->
    <text x="130" y="86" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-weight="700" font-size="32" fill="{green}" filter="url(#glow)">{total}</text>
    <text x="130" y="110" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="11" fill="{text_mid}"># total_contributions</text>
    <text x="130" y="128" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="10" fill="{text_dim}">{range_start} -&gt; now</text>

    <line x1="253" y1="46" x2="253" y2="146" stroke="{border}" stroke-width="1" />

    <text x="380" y="86" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-weight="700" font-size="32" fill="{amber}" filter="url(#glow)">{current}</text>
    <text x="380" y="110" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="11" fill="{text_mid}"># current_streak</text>
    <text x="380" y="128" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="10" fill="{text_dim}">as of {today}</text>

    <line x1="507" y1="46" x2="507" y2="146" stroke="{border}" stroke-width="1" />

    <text x="630" y="86" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-weight="700" font-size="32" fill="{green}" filter="url(#glow)">{longest}</text>
    <text x="630" y="110" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="11" fill="{text_mid}"># longest_streak</text>
    <text x="630" y="128" text-anchor="middle" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="10" fill="{text_dim}">{longest_range}</text>

    <line x1="0" y1="160" x2="760" y2="160" stroke="{border}" stroke-width="1" />

    <!-- prompt -->
    <text x="20" y="190" font-family="Consolas, Monaco, 'Courier New', monospace" font-size="13" fill="{text_mid}">guest@shabbir-369:~$ <tspan fill="{text_dim}">_</tspan></text>
    <rect x="182" y="178" width="8" height="14" fill="{green}">
      <animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" dur="1.1s" repeatCount="indefinite" />
    </rect>

    <!-- CRT texture -->
    <rect x="0" y="0" width="760" height="224" fill="url(#scan)" />
    <rect x="0" y="0" width="760" height="224" fill="url(#vignette)" />
  </g>

  <rect x="0.5" y="0.5" width="759" height="223" rx="10" fill="none" stroke="{border}" stroke-width="1" />
</svg>
"""


def build_svg(theme_name, username, total, current, longest, range_start, longest_start, longest_end):
    t = THEMES[theme_name]
    return SVG_TEMPLATE.format(
        user=username,
        total=f"{total:,}",
        range_start=range_start,
        current=current,
        today=datetime.date.today().strftime("%b %d"),
        longest=longest,
        longest_range=f"{fmt(longest_start)} - {fmt(longest_end)}" if longest_start else "-",
        **t,
    )


def main():
    total, all_days, created_at = fetch_all_days(GITHUB_USERNAME)
    current, longest, longest_start, longest_end = compute_streaks(all_days)
    range_start = created_at.strftime("%b %Y")

    os.makedirs("assets", exist_ok=True)
    for theme_name in ("dark", "light"):
        svg = build_svg(
            theme_name, GITHUB_USERNAME, total, current, longest,
            range_start, longest_start, longest_end,
        )
        with open(f"assets/dashboard-{theme_name}.svg", "w") as f:
            f.write(svg)

    print(f"total={total} current_streak={current} longest_streak={longest}")


if __name__ == "__main__":
    main()
