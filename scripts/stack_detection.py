"""
Reconstructs a real technology stack from repo manifests, instead of raw
GitHub language-byte stats.

GitHub's language API answers "what file types are in this repo" — it can't
tell React from vanilla JavaScript, because both are just ".js" files. This
module reads the actual dependency manifest (package.json / requirements.txt
/ pyproject.toml) and maps real package names to display technologies, which
is what someone actually built with.
"""

import json
import re

import config

# Recognized package/dependency name -> display technology. "core" tech
# (frameworks, databases, platforms) is always prioritized over plain
# languages when space is limited. Extend or override via
# config.EXTRA_TECH_MAP — no need to edit this file for that.
TECH_MAP = {
    # JS / Node ecosystem
    "react": {"name": "React", "tier": "core"},
    "react-dom": {"name": "React", "tier": "core"},
    "next": {"name": "Next.js", "tier": "core"},
    "vue": {"name": "Vue", "tier": "core"},
    "svelte": {"name": "Svelte", "tier": "core"},
    "express": {"name": "Express.js", "tier": "core"},
    "fastify": {"name": "Fastify", "tier": "core"},
    "@nestjs/core": {"name": "NestJS", "tier": "core"},
    "mongoose": {"name": "MongoDB", "tier": "core"},
    "mongodb": {"name": "MongoDB", "tier": "core"},
    "mysql2": {"name": "MySQL", "tier": "core"},
    "mysql": {"name": "MySQL", "tier": "core"},
    "pg": {"name": "PostgreSQL", "tier": "core"},
    "@prisma/client": {"name": "Prisma", "tier": "core"},
    "prisma": {"name": "Prisma", "tier": "core"},
    "sequelize": {"name": "Sequelize", "tier": "core"},
    "redis": {"name": "Redis", "tier": "core"},
    "ioredis": {"name": "Redis", "tier": "core"},
    "bullmq": {"name": "BullMQ", "tier": "core"},
    "firebase": {"name": "Firebase", "tier": "core"},
    "firebase-admin": {"name": "Firebase", "tier": "core"},
    "@supabase/supabase-js": {"name": "Supabase", "tier": "core"},
    "socket.io": {"name": "Socket.io", "tier": "core"},
    "tailwindcss": {"name": "Tailwind CSS", "tier": "core"},
    "jsonwebtoken": {"name": "JWT", "tier": "core"},
    "graphql": {"name": "GraphQL", "tier": "core"},
    "apollo-server": {"name": "GraphQL", "tier": "core"},

    # Python ecosystem
    "fastapi": {"name": "FastAPI", "tier": "core"},
    "flask": {"name": "Flask", "tier": "core"},
    "django": {"name": "Django", "tier": "core"},
    "sqlalchemy": {"name": "SQLAlchemy", "tier": "core"},
    "pandas": {"name": "Pandas", "tier": "core"},
    "numpy": {"name": "NumPy", "tier": "core"},
    "tensorflow": {"name": "TensorFlow", "tier": "core"},
    "torch": {"name": "PyTorch", "tier": "core"},
    "scikit-learn": {"name": "scikit-learn", "tier": "core"},
    "opencv-python": {"name": "OpenCV", "tier": "core"},
    "transformers": {"name": "HuggingFace", "tier": "core"},
    "sentence-transformers": {"name": "HuggingFace", "tier": "core"},

    # infra / tooling worth a slot
    "docker": {"name": "Docker", "tier": "core"},
}

# Real languages, shown if there's room left after core tech. Anything not
# listed here falls back to its GitHub-reported name as-is.
LANGUAGE_DISPLAY = {
    "JavaScript": "JavaScript",
    "TypeScript": "TypeScript",
    "Python": "Python",
    "C++": "C++",
    "C": "C",
    "Java": "Java",
    "Go": "Go",
    "Rust": "Rust",
    "C#": "C#",
}

# Never worth a slot on their own — every web repo has these regardless of
# effort, so they add no signal about what was actually built.
HIDDEN_LANGUAGES = {"HTML", "CSS", "JSON", "Markdown", "Shell", "YAML", "Dockerfile", "Jupyter Notebook"}


def _tech_map():
    merged = dict(TECH_MAP)
    merged.update(config.EXTRA_TECH_MAP)
    return merged


def _excluded():
    return {s.lower() for s in config.EXCLUDE_STACK}


def parse_package_json(text):
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return set()
    deps = {}
    deps.update(data.get("dependencies") or {})
    deps.update(data.get("devDependencies") or {})
    found = set(deps.keys())
    found.add("node")  # any package.json implies Node.js
    return found


def parse_requirements_txt(text):
    found = set()
    for line in (text or "").splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[=<>!\[; ]", line)[0].strip()
        if name:
            found.add(name)
    return found


def parse_pyproject_toml(text):
    # Cheap heuristic, no toml dependency: pull bare keys out of
    # dependency-shaped lines ("fastapi = \"^0.100\"").
    found = set()
    for line in (text or "").splitlines():
        m = re.match(r'\s*"?([a-zA-Z0-9_.\-]+)"?\s*=', line)
        if m:
            found.add(m.group(1).strip().lower())
    return found


def detect_repo_technologies(repo, detail):
    """Returns an ordered list of display names for one repo — core tech
    (frameworks/DBs/platforms) first, then real languages. Respects
    config.EXCLUDE_STACK. `detail` may be None (e.g. an empty repo)."""
    if detail is None:
        detail = {}

    package_names = set()
    if detail.get("packageJson"):
        package_names |= parse_package_json(detail["packageJson"]["text"])
    if detail.get("requirementsTxt"):
        package_names |= parse_requirements_txt(detail["requirementsTxt"]["text"])
    if detail.get("pyprojectToml"):
        package_names |= parse_pyproject_toml(detail["pyprojectToml"]["text"])

    tech_map = _tech_map()
    excluded = _excluded()

    core = []
    seen = set()
    for pkg in package_names:
        entry = tech_map.get(pkg.lower())
        if entry and entry["name"] not in seen and entry["name"].lower() not in excluded:
            core.append(entry["name"])
            seen.add(entry["name"])
    if "node" in package_names and "Node.js" not in seen and "node.js" not in excluded:
        core.append("Node.js")
        seen.add("Node.js")

    languages = []
    lang_edges = (detail.get("languages") or {}).get("edges", [])
    for e in lang_edges:
        name = e["node"]["name"]
        if name in HIDDEN_LANGUAGES:
            continue
        display = LANGUAGE_DISPLAY.get(name, name)
        if display not in seen and display.lower() not in excluded:
            languages.append(display)
            seen.add(display)

    return core + languages


def aggregate_stack(per_repo_techs):
    """per_repo_techs: list of lists (one per showcased repo that has real
    GitHub data). Ranks technologies by how many different repos use them —
    a stronger "actually part of my stack" signal than raw byte volume.
    Applies FORCE_STACK / EXCLUDE_STACK and caps at config.MAX_STACK_ITEMS."""
    excluded = _excluded()
    counts = {}
    order_hint = []  # keeps first-seen order for stable-ish ties
    for techs in per_repo_techs:
        for t in techs:
            if t.lower() in excluded:
                continue
            if t not in counts:
                order_hint.append(t)
            counts[t] = counts.get(t, 0) + 1

    ranked = sorted(counts.keys(), key=lambda t: (-counts[t], order_hint.index(t)))

    final = [t for t in config.FORCE_STACK if t.lower() not in excluded]
    for t in ranked:
        if len(final) >= config.MAX_STACK_ITEMS:
            break
        if t not in final:
            final.append(t)

    return final[: config.MAX_STACK_ITEMS]
