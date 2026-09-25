"""Small shared helpers used across the profile-generator modules."""


def truncate(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def fmt_date(d):
    return d.strftime("%b %d, %Y") if d else "-"
