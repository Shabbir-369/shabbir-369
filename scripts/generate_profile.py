"""
Generates assets/profile-dark.svg and assets/profile-light.svg — the whole
profile rendered as one scrolling terminal session.

This module only does two things: (1) call the other modules to get real
data, (2) render that data into the terminal-styled SVG. It doesn't decide
which repos are good (repo_scoring.py) or what stack you actually use
(stack_detection.py) — see those files, or config.py for tuning without
touching any logic.

Run by .github/workflows/dashboard.yml on a daily schedule. Needs a token
with read access to public data — the Action's default GITHUB_TOKEN works;
if it doesn't for your account, add a classic Personal Access Token (no
scopes required) as a repo secret named ACCESS_TOKEN and it'll be preferred.

Edit NAME / TAGLINE / ABOUT_LINES / STATUS_LINES / CONTACT below for your own
identity copy. Projects and stack are never hand-typed here — see config.py.
"""

import datetime
import os

import github_api
import repo_scoring
import stack_detection
from utils import fmt_date

# ---- identity copy: edit this section for your own bio ----------------------

NAME = "Shabbir Ezzy"
TAGLINE = "Full-stack developer · C++ & DSA · AI / IoT · builder"

STATUS_LINES = [
    "I build things I wish existed.",
    "I like figuring things out by building them.",
    "Alone or with a great team - same energy.",
]

ABOUT_LINES = [
    "What I love most is putting my head down and building - with people who care",
    "about the craft, or on my own. Taking an idea, figuring it out, and turning it",
    "into something that actually works.",
]

CONTACT = "github.com/{user}  |  linkedin.com/in/shabbir-ezzy  |  codewithshabbir@gmail.com"

# ---- terminal / CRT rendering (unchanged) ------------------------------------

FONT = "Consolas, Monaco, 'Courier New', monospace"

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
        glow=3.0,
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
        glow=1.1,
    ),
}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Card:
    def __init__(self, theme, username, width=760):
        self.t = THEMES[theme]
        self.username = username
        self.width = width
        self.left = 24
        self.y = 54
        self.body = []

    def prompt(self, cmd):
        self.body.append(
            f'<text x="{self.left}" y="{self.y}" font-family="{FONT}" font-size="13" '
            f'fill="{self.t["text_mid"]}">$ {esc(cmd)}</text>'
        )
        self.y += 24

    def line(self, text, color=None, size=12, indent=0):
        color = color or self.t["text_dim"]
        self.body.append(
            f'<text x="{self.left + indent}" y="{self.y}" font-family="{FONT}" '
            f'font-size="{size}" fill="{color}">{esc(text)}</text>'
        )
        self.y += 20

    def gap(self, px=10):
        self.y += px

    def divider(self):
        self.gap(4)
        self.body.append(
            f'<line x1="0" y1="{self.y}" x2="{self.width}" y2="{self.y}" '
            f'stroke="{self.t["border"]}" stroke-width="1" />'
        )
        self.gap(18)

    def stats(self, items):
        col = self.width / len(items)
        top = self.y
        for i, (value, label, sub, color) in enumerate(items):
            cx = col * i + col / 2
            self.body.append(
                f'<text x="{cx:.1f}" y="{top + 38}" text-anchor="middle" font-family="{FONT}" '
                f'font-weight="700" font-size="28" fill="{color}" filter="url(#glow)">{esc(value)}</text>'
            )
            self.body.append(
                f'<text x="{cx:.1f}" y="{top + 60}" text-anchor="middle" font-family="{FONT}" '
                f'font-size="11" fill="{self.t["text_mid"]}">{esc(label)}</text>'
            )
            self.body.append(
                f'<text x="{cx:.1f}" y="{top + 77}" text-anchor="middle" font-family="{FONT}" '
                f'font-size="10" fill="{self.t["text_dim"]}">{esc(sub)}</text>'
            )
            if i > 0:
                self.body.append(
                    f'<line x1="{col * i:.1f}" y1="{top + 6}" x2="{col * i:.1f}" y2="{top + 90}" '
                    f'stroke="{self.t["border"]}" stroke-width="1" />'
                )
        self.y = top + 100

    def project(self, name, desc, tags):
        self.body.append(
            f'<text x="{self.left}" y="{self.y}" font-family="{FONT}" font-size="11" '
            f'fill="{self.t["text_dim"]}">drwxr-xr-x</text>'
        )
        self.body.append(
            f'<text x="{self.left + 108}" y="{self.y}" font-family="{FONT}" font-weight="700" '
            f'font-size="12" fill="{self.t["green"]}">{esc(name)}/</text>'
        )
        self.body.append(
            f'<text x="{self.left + 250}" y="{self.y}" font-family="{FONT}" font-size="11" '
            f'fill="{self.t["text_mid"]}">{esc(desc)}</text>'
        )
        self.y += 17
        self.body.append(
            f'<text x="{self.left + 250}" y="{self.y}" font-family="{FONT}" font-size="10" '
            f'fill="{self.t["text_dim"]}">{esc(tags)}</text>'
        )
        self.y += 24

    def cycling_status(self, lines, total_dur=9):
        seg = total_dur / len(lines)
        for i, text in enumerate(lines):
            start = (i * seg) / total_dur
            end = ((i + 1) * seg) / total_dur
            key_times = f"0;{start:.4f};{start:.4f};{end:.4f};{end:.4f};1"
            base_opacity = 1 if i == 0 else 0
            self.body.append(
                f'<text x="{self.left}" y="{self.y}" font-family="{FONT}" font-size="12" '
                f'fill="{self.t["green"]}" opacity="{base_opacity}">&gt; {esc(text)}'
                f'<animate attributeName="opacity" values="0;0;1;1;0;0" '
                f'keyTimes="{key_times}" dur="{total_dur}s" repeatCount="indefinite" /></text>'
            )
        self.y += 22

    def cursor_prompt(self, text):
        self.body.append(
            f'<text x="{self.left}" y="{self.y}" font-family="{FONT}" font-size="13" '
            f'fill="{self.t["text_mid"]}">{esc(text)}</text>'
        )
        cx = self.left + len(text) * 7.4
        self.body.append(
            f'<rect x="{cx:.1f}" y="{self.y - 12}" width="8" height="14" fill="{self.t["green"]}">'
            f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" '
            f'dur="1.1s" repeatCount="indefinite" /></rect>'
        )
        self.y += 20

    def render(self):
        height = self.y + 24
        t = self.t
        body = "\n    ".join(self.body)
        return f'''<svg width="{self.width}" height="{height}" viewBox="0 0 {self.width} {height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="{t["glow"]}" result="blur" />
      <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
    </filter>
    <pattern id="scan" width="3" height="3" patternUnits="userSpaceOnUse">
      <rect width="3" height="1" fill="{t["scan"]}" />
    </pattern>
    <radialGradient id="vignette" cx="50%" cy="40%" r="80%">
      <stop offset="55%" stop-color="#000000" stop-opacity="0" />
      <stop offset="100%" stop-color="#000000" stop-opacity="{t["vignette"]}" />
    </radialGradient>
    <clipPath id="clip"><rect x="0.5" y="0.5" width="{self.width - 1}" height="{height - 1}" rx="10" /></clipPath>
  </defs>
  <g clip-path="url(#clip)">
    <rect x="0" y="0" width="{self.width}" height="{height}" fill="{t["bg"]}" />
    <rect x="0" y="0" width="{self.width}" height="32" fill="{t["chrome_bg"]}" />
    <circle cx="18" cy="16" r="5" fill="#ff5f56" />
    <circle cx="36" cy="16" r="5" fill="#ffbd2e" />
    <circle cx="54" cy="16" r="5" fill="#27c93f" />
    <text x="78" y="20" font-family="{FONT}" font-size="12" fill="{t["text_dim"]}">{esc(self.username)}@github:~$ ./profile.sh</text>
    <line x1="0" y1="32" x2="{self.width}" y2="32" stroke="{t["border"]}" stroke-width="1" />
    {body}
    <rect x="0" y="0" width="{self.width}" height="{height}" fill="url(#scan)" />
    <rect x="0" y="0" width="{self.width}" height="{height}" fill="url(#vignette)" />
  </g>
  <rect x="0.5" y="0.5" width="{self.width - 1}" height="{height - 1}" rx="10" fill="none" stroke="{t["border"]}" stroke-width="1" />
</svg>
'''


def build_profile(theme, username, total, current, longest, range_start, longest_start, longest_end, projects, stack):
    t = THEMES[theme]
    c = Card(theme, username)

    c.prompt("whoami")
    c.line(f"{NAME} - {TAGLINE}", color=t["green"], size=13)
    c.gap(8)
    c.cycling_status(STATUS_LINES)
    c.gap(4)

    c.prompt("cat about.md")
    for l in ABOUT_LINES:
        c.line(l)
    c.divider()

    c.prompt("./analytics.sh --live")
    c.gap(6)
    longest_range = f"{fmt_date(longest_start)} - {fmt_date(longest_end)}" if longest_start else "-"
    c.stats(
        [
            (f"{total:,}", "# total_contributions", f"{range_start} to now", t["green"]),
            (str(current), "# current_streak", f"as of {datetime.date.today().strftime('%b %d')}", t["amber"]),
            (str(longest), "# longest_streak", longest_range, t["green"]),
        ]
    )
    c.divider()

    c.prompt("ls -la ~/projects")
    c.gap(6)
    for name, desc, tags in projects:
        c.project(name, desc, tags)
    c.divider()

    c.prompt("cat stack.txt")
    c.line(", ".join(stack))
    c.divider()

    c.prompt("cat contact.txt")
    c.line(CONTACT.format(user=username))
    c.gap(14)

    c.cursor_prompt(f"guest@{username}:~$ ")

    return c.render()


def main():
    total, all_days, created_at = github_api.fetch_all_days(github_api.GITHUB_USERNAME)
    current, longest, longest_start, longest_end = github_api.compute_streaks(all_days)
    range_start = created_at.strftime("%b %Y")

    projects, techs_by_project = repo_scoring.select_showcase(
        github_api.GITHUB_USERNAME, github_api.PROFILE_REPO_NAME
    )
    stack = stack_detection.aggregate_stack(techs_by_project)
    if not stack:
        stack = ["-"]

    os.makedirs("assets", exist_ok=True)
    for theme in ("dark", "light"):
        svg = build_profile(
            theme, github_api.GITHUB_USERNAME, total, current, longest,
            range_start, longest_start, longest_end, projects, stack,
        )
        with open(f"assets/profile-{theme}.svg", "w") as f:
            f.write(svg)

    print(f"total={total} current_streak={current} longest_streak={longest}")
    print(f"projects={[p[0] for p in projects]}")
    print(f"stack={stack}")


if __name__ == "__main__":
    main()
