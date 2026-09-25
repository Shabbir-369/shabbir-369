"""
Decides which repos get showcased.

Pipeline: hard filter (fork/archived/disabled/empty/self/excluded) -> pull out
anything forced (config.FORCE_PROJECTS, the "showcase" topic) -> score
everything else -> diversity pass so near-identical repos don't crowd out
variety -> fill remaining slots -> config.EXCLUDE_PROJECTS has the final word
regardless of how something got in.

Only repo_scoring and generate_profile call into stack_detection and
github_api; config is the only thing you should need to edit for tuning.
"""

import datetime
import math
import re

import config
import github_api
import stack_detection
from utils import truncate

_NAME_PENALTY_RE = re.compile(
    "|".join(re.escape(p) for p in config.THROWAWAY_NAME_PATTERNS), re.IGNORECASE
)


def is_throwaway_name(name):
    return bool(_NAME_PENALTY_RE.search(name))


def has_topic(repo, topic):
    return topic in {t["topic"]["name"] for t in repo["repositoryTopics"]["nodes"]}


def hard_filter(repos, profile_repo_name):
    exclude_lower = {n.lower() for n in config.EXCLUDE_PROJECTS}
    out = []
    for r in repos:
        if r["isFork"] or r["isArchived"] or r["isDisabled"]:
            continue
        if not r["diskUsage"]:
            continue
        if r["name"].lower() == profile_repo_name.lower():
            continue
        if r["name"].lower() in exclude_lower:
            continue
        if has_topic(r, config.HIDE_TOPIC):
            continue
        out.append(r)
    return out


def recency_score(pushed_at_str):
    pushed = datetime.datetime.strptime(pushed_at_str[:19], "%Y-%m-%dT%H:%M:%S")
    days = (datetime.datetime.utcnow() - pushed).days
    # Exponential decay, half-life from config — recent work scores higher,
    # but nothing falls off a cliff (a finished project from months ago can
    # still outrank a half-built one updated yesterday).
    return 0.5 ** (days / config.RECENCY_HALF_LIFE_DAYS)


def community_score(repo):
    # Log-scaled so one lucky repo doesn't dominate the whole ranking.
    return math.log1p(repo["stargazerCount"] * 2 + repo["forkCount"])


def preliminary_score(repo, pinned_names):
    """Cheap, metadata-only score used purely to shortlist which repos are
    worth a full detail scan (README + manifests cost an API call each)."""
    score = 0.0
    score += community_score(repo) * config.WEIGHTS["community"]
    score += recency_score(repo["pushedAt"]) * config.WEIGHTS["recency"]
    score += 5 if repo["description"] else 0
    score += min(len(repo["repositoryTopics"]["nodes"]), 5)
    if repo["name"] in pinned_names:
        score += config.PINNED_BONUS
    if is_throwaway_name(repo["name"]):
        score *= config.THROWAWAY_NAME_PENALTY
    return score


def completeness_score(detail):
    if not detail:
        return 0
    readme_size = 0
    if detail.get("readmeUpper"):
        readme_size = max(readme_size, detail["readmeUpper"]["byteSize"])
    if detail.get("readmeLower"):
        readme_size = max(readme_size, detail["readmeLower"]["byteSize"])
    ratio = min(readme_size / config.README_MIN_BYTES_FOR_FULL_SCORE, 1.0) if readme_size else 0
    return ratio * config.WEIGHTS["completeness"]


def final_score(repo, detail, stack_depth, pinned_names):
    score = 0.0
    score += community_score(repo) * config.WEIGHTS["community"]
    score += recency_score(repo["pushedAt"]) * config.WEIGHTS["recency"]
    score += completeness_score(detail)
    score += min(stack_depth, 6) / 6 * config.WEIGHTS["stack_depth"]
    if repo["name"] in pinned_names:
        score += config.PINNED_BONUS
    if is_throwaway_name(repo["name"]):
        score *= config.THROWAWAY_NAME_PENALTY
    return score


def category_of(techs):
    """A rough bucket for the diversity pass, derived from detected tech —
    not a real classifier, just enough to stop six near-identical repos from
    crowding out variety."""
    names = {t.lower() for t in techs}
    ml = {"tensorflow", "pytorch", "opencv", "scikit-learn", "pandas", "numpy", "huggingface"}
    frontend = {"react", "next.js", "vue", "svelte"}
    backend = {"express.js", "fastapi", "django", "flask", "nestjs", "fastify"}
    if names & ml:
        return "ai-ml"
    if names & frontend and names & backend:
        return "full-stack"
    if names & backend:
        return "backend"
    if names & frontend:
        return "frontend"
    return "other"


def diversify(scored, limit):
    """scored: list of (repo, score, techs, category), any order. Greedily
    fills up to `limit` slots highest-score-first, skipping to the next
    best-scoring repo in a *different* category before repeating one."""
    chosen = []
    used_categories = []
    remaining = list(scored)
    while remaining and len(chosen) < limit:
        pick_idx = 0
        for i, (repo, score, techs, cat) in enumerate(remaining):
            if cat not in used_categories:
                pick_idx = i
                break
        chosen.append(remaining.pop(pick_idx))
        used_categories.append(chosen[-1][3])
    return chosen


def select_showcase(login, profile_repo_name):
    """Returns (projects, techs_by_project):
    - projects: list of (name, description, tags) ready for rendering
    - techs_by_project: list of raw tech-name lists, for stack aggregation
      (entries from config.FORCE_PROJECTS contribute no techs — there's no
      real repo behind them to scan).
    """
    all_repos = github_api.fetch_repositories(login)
    pinned_names = github_api.get_pinned_names(login)
    eligible = hard_filter(all_repos, profile_repo_name)

    forced_topic_repos = [r for r in eligible if has_topic(r, config.SHOWCASE_TOPIC)]
    forced_topic_lower = {r["name"].lower() for r in forced_topic_repos}
    hardcoded_lower = {p["name"].lower() for p in config.FORCE_PROJECTS if "name" in p}

    auto_candidates = [
        r for r in eligible
        if r["name"].lower() not in forced_topic_lower
        and r["name"].lower() not in hardcoded_lower
    ]
    auto_candidates.sort(key=lambda r: preliminary_score(r, pinned_names), reverse=True)
    shortlist = auto_candidates[: config.MAX_SCAN_CANDIDATES]

    scored = []
    for r in shortlist:
        detail = github_api.fetch_repo_detail(login, r["name"])
        techs = stack_detection.detect_repo_technologies(r, detail)
        score = final_score(r, detail, len(techs), pinned_names)
        scored.append((r, score, techs, category_of(techs)))
    scored.sort(key=lambda x: x[1], reverse=True)

    entries = []  # (name, description, tags_str, techs_list)

    # 1. hardcoded, literal overrides — no repo lookup, no techs contributed
    for p in config.FORCE_PROJECTS:
        entries.append((p["name"], p.get("description", "no description set"), p.get("tags", "-"), []))

    # 2. repos carrying the showcase topic — real data, always included
    for r in forced_topic_repos:
        detail = github_api.fetch_repo_detail(login, r["name"])
        techs = stack_detection.detect_repo_technologies(r, detail)
        entries.append((
            r["name"], r["description"] or "no description set",
            " · ".join(techs) if techs else "-", techs,
        ))

    # 3. automatic + diversity, filling whatever slots remain
    remaining_slots = max(config.MAX_PROJECTS - len(entries), 0)
    for r, score, techs, cat in diversify(scored, remaining_slots):
        entries.append((
            r["name"], r["description"] or "no description set",
            " · ".join(techs) if techs else "-", techs,
        ))

    # EXCLUDE_PROJECTS is the final word, regardless of how something got here
    exclude_lower = {n.lower() for n in config.EXCLUDE_PROJECTS}
    entries = [e for e in entries if e[0].lower() not in exclude_lower]
    entries = entries[: config.MAX_PROJECTS]

    projects = [(name, truncate(desc, 66), tags) for name, desc, tags, _ in entries]
    techs_by_project = [techs for *_, techs in entries]

    return projects, techs_by_project
