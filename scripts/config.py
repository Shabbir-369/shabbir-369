"""
Tunable settings for the profile generator.

Everything you'd want to adjust without touching logic lives here: manual
overrides, limits, topic names, and scoring weights. The other modules read
these values but shouldn't need editing for day-to-day tuning.

Priority order (both projects and stack):

    EXCLUDE  >  FORCE  >  AUTOMATIC

An excluded item never shows, even if it's also forced or scores well.
"""

# ---- manual overrides: projects ---------------------------------------------

# Force a project into the showcase regardless of score. Only "name" is
# required — "description" and "tags" are shown as given (these are literal,
# hand-typed entries, not looked up on GitHub).
FORCE_PROJECTS = [
    # {"name": "my-repo", "description": "custom description", "tags": "react · mysql"},
]

# Repo names (case-insensitive) to always exclude from the showcase, even if
# they'd otherwise score well or carry the "showcase" topic.
EXCLUDE_PROJECTS = [
    # "old-experiment",
]

# ---- manual overrides: tech stack --------------------------------------------

# Technology display names to always include in the aggregate stack line,
# even if no scanned repo's manifest surfaced them.
FORCE_STACK = [
    # "Docker",
]

# Technology display names to always hide, even if detected in a manifest —
# applies everywhere (the stack line and each project's own tags).
EXCLUDE_STACK = [
    # "jQuery",
]

# Add or override entries in the technology map without touching
# stack_detection.py. Keys are the exact package/dependency name as it
# appears in package.json / requirements.txt (lowercase). Values follow the
# same shape as stack_detection.TECH_MAP: {"name": "Display Name", "tier": "core"}.
EXTRA_TECH_MAP = {
    # "my-internal-lib": {"name": "My Internal Lib", "tier": "core"},
}

# ---- limits ------------------------------------------------------------------

MAX_PROJECTS = 3
MAX_STACK_ITEMS = 6

# How many auto-ranked candidates get a full detail scan (README + manifests).
# Keeps the number of API calls per run bounded regardless of how many repos
# you have.
MAX_SCAN_CANDIDATES = 20

# ---- topics -------------------------------------------------------------------

SHOWCASE_TOPIC = "showcase"
HIDE_TOPIC = "hide-profile"

# ---- scoring weights ----------------------------------------------------------
# These four should add to roughly 100 across a repo's lifetime score; the
# exact scale doesn't matter since only relative ranking is used.

WEIGHTS = dict(
    stack_depth=30,    # how many recognized, high-value technologies it uses
    completeness=20,   # README size, description, topics
    community=10,      # stars + forks, log-scaled
    recency=10,        # decay curve, not a cliff — old finished work still ranks
)

PINNED_BONUS = 5

# Repos whose name matches one of these (case-insensitive substring) get their
# score multiplied by this factor rather than being removed outright — a repo
# called "Practice-Ledger" might still be a real project.
THROWAWAY_NAME_PENALTY = 0.5
THROWAWAY_NAME_PATTERNS = [
    "practice", "test", "testing", "temp", "demo", "experiment",
    "assignment", "lab", "practical", "sandbox", "scratch", "hello-world",
]

# A README at or above this size gets full completeness credit for that signal.
README_MIN_BYTES_FOR_FULL_SCORE = 1500

# Half-life for the recency decay, in days. A repo pushed this long ago still
# scores at 50% of the recency signal, not zero.
RECENCY_HALF_LIFE_DAYS = 240
