"""
All GitHub GraphQL access lives here: token/identity resolution, contribution
history (for the live stats block), the full repo listing (for scoring), and
per-repo detail fetches (README size + manifests, for stack detection).

Nothing in here decides *what* to showcase or *how* to score — that's
repo_scoring.py and stack_detection.py. This module only fetches and returns
plain data.
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

# The profile repo itself (owner/repo, e.g. "shabbir-369/shabbir-369"), so it
# can be excluded from its own showcase. Falls back to "<username>" when the
# env var isn't set (e.g. running locally).
PROFILE_REPO_NAME = os.environ.get("GITHUB_REPOSITORY", "").split("/")[-1] or GITHUB_USERNAME

API_URL = "https://api.github.com/graphql"
HEADERS = {"Authorization": f"bearer {TOKEN}"}


def run_query(query, variables):
    resp = requests.post(
        API_URL, json={"query": query, "variables": variables}, headers=HEADERS, timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


# ---- contributions / streaks -------------------------------------------------

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_all_days(login):
    """The API only returns 1 year per call, so walk back year by year to createdAt."""
    now = datetime.datetime.utcnow()
    first = run_query(
        CONTRIB_QUERY,
        {
            "login": login,
            "from": (now - datetime.timedelta(days=365)).isoformat() + "Z",
            "to": now.isoformat() + "Z",
        },
    )["user"]
    created_at = datetime.datetime.strptime(first["createdAt"][:19], "%Y-%m-%dT%H:%M:%S")

    all_days = {}
    total_contributions = 0
    cursor_end = now

    while cursor_end > created_at:
        cursor_start = max(created_at, cursor_end - datetime.timedelta(days=365))
        chunk = run_query(
            CONTRIB_QUERY,
            {
                "login": login,
                "from": cursor_start.isoformat() + "Z",
                "to": cursor_end.isoformat() + "Z",
            },
        )["user"]
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


# ---- repositories -------------------------------------------------------------

REPO_LIST_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 100, after: $after, ownerAffiliations: [OWNER], privacy: PUBLIC, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        description
        url
        isFork
        isArchived
        isDisabled
        diskUsage
        pushedAt
        stargazerCount
        forkCount
        repositoryTopics(first: 10) { nodes { topic { name } } }
      }
    }
  }
}
"""


def fetch_repositories(login):
    """All public, owned repos (paginated) with the metadata scoring needs."""
    repos = []
    after = None
    while True:
        data = run_query(REPO_LIST_QUERY, {"login": login, "after": after})["user"]["repositories"]
        repos.extend(data["nodes"])
        if not data["pageInfo"]["hasNextPage"]:
            break
        after = data["pageInfo"]["endCursor"]
    return repos


REPO_DETAIL_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    readmeUpper: object(expression: "HEAD:README.md") { ... on Blob { byteSize } }
    readmeLower: object(expression: "HEAD:readme.md") { ... on Blob { byteSize } }
    packageJson: object(expression: "HEAD:package.json") { ... on Blob { text } }
    requirementsTxt: object(expression: "HEAD:requirements.txt") { ... on Blob { text } }
    pyprojectToml: object(expression: "HEAD:pyproject.toml") { ... on Blob { text } }
    languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { node { name } } }
  }
}
"""


def fetch_repo_detail(owner, name):
    """README size + manifest contents + languages for one repo.

    Returns None on any error (e.g. a genuinely empty repo with no HEAD)
    rather than raising, since this is called in a loop over many repos and
    one odd repo shouldn't take down the whole run.
    """
    try:
        return run_query(REPO_DETAIL_QUERY, {"owner": owner, "name": name})["repository"]
    except Exception:
        return None


PINNED_QUERY = """
query($login: String!) {
  user(login: $login) {
    pinnedItems(first: 6, types: [REPOSITORY]) {
      nodes { ... on Repository { name } }
    }
  }
}
"""


def get_pinned_names(login):
    """Repo names currently pinned on the profile — used only as a small
    scoring bonus, never as the primary selection mechanism."""
    nodes = run_query(PINNED_QUERY, {"login": login})["user"]["pinnedItems"]["nodes"]
    return {n["name"] for n in nodes if n}
