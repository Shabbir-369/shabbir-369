# Setup

Push the contents of this folder to the root of the `Shabbir-369/shabbir-369` profile repository (repo name must match your username, case-insensitively, for GitHub to render it as your profile README).

## Files

```text
README.md
assets/
  github-dashboard.svg      ← regenerated automatically, don't hand-edit
scripts/
  generate_dashboard.py
.github/
  workflows/
    update-profile.yml
```

## First-time setup

1. Push this folder to the root of `Shabbir-369/Shabbir-369`.
2. Go to **Settings → Actions → General → Workflow permissions** and make sure
   **"Read and write permissions"** is selected. Without this the workflow can
   generate the SVG but can't commit it back.
3. Go to **Actions → Update GitHub Profile Dashboard → Run workflow** once to
   generate the first real dashboard. Until this runs, `assets/github-dashboard.svg`
   is a placeholder that shows zeroed-out stats — that's expected, not a bug.
4. After that, it refreshes itself daily on the schedule in the workflow file,
   and again automatically whenever you edit the generator script.

## What the dashboard shows

- **Contribution matrix** — rolling 365-day GitHub contribution calendar, plus current and longest streaks
- **Top languages** — computed live from your public, non-fork repositories (by code volume)
- **Activity stream** — your 5 most recent public GitHub events
- **Followers / public repos / total stars** — pulled live from the GitHub API

All of it is real data fetched at generation time — nothing hardcoded.

The UI is intentionally a single retro terminal/CRT dashboard:
- muted green + amber palette
- subtle scanlines
- blinking terminal cursor
- animated contribution cells
- compact contribution stats
- recent public activity stream

The activity stream comes from GitHub's public user-events endpoint, so it can have some delay and won't show private activity. The languages and stars figures only count public, non-fork repositories you own.

## Running it locally

```bash
pip install --break-system-packages typing_extensions  # stdlib-only otherwise, nothing else to install
USER_NAME=Shabbir-369 GITHUB_TOKEN=<a personal access token> python3 scripts/generate_dashboard.py
open assets/github-dashboard.svg  # or just open it in a browser
```

A token isn't strictly required — the script falls back to zeroed stats and an empty activity stream if calls fail — but GitHub's unauthenticated rate limit is very easy to hit (60 requests/hour, shared across your whole network), so a token makes local testing far more reliable. In the Action itself, the built-in `GITHUB_TOKEN` secret is used automatically and doesn't need to be created by hand.

## Troubleshooting

- **Dashboard image is a broken link in the README** — make sure the repo is actually named `Shabbir-369` (not `shabbir-369-profile` or similar) and that `assets/github-dashboard.svg` exists on the `main` branch.
- **Stats look empty right after setup** — run the workflow manually once (step 3 above); it doesn't backfill on its own until triggered.
- **Workflow runs but doesn't commit anything** — almost always the missing "Read and write permissions" setting from step 2.
- **Numbers look wrong / a repo you archived still counts** — the language and star totals only refresh once a day; give it until the next scheduled run, or trigger the workflow manually.
