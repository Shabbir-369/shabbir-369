# Setup

Push the contents of this folder to the root of the `Shabbir-369/shabbir-369` profile repository.

## Files

```text
README.md
assets/
  github-dashboard.svg
scripts/
  generate_dashboard.py
.github/
  workflows/
    update-profile.yml
```

Run **Actions → Update GitHub Profile Dashboard → Run workflow** once after the first push.

Until that first run completes, `assets/github-dashboard.svg` in this folder ships as an honest placeholder (dashes instead of numbers, "no language data yet") rather than fabricated stats — that's expected, not a bug.

The workflow uses the repository's `GITHUB_TOKEN` to generate the dashboard SVG and commits the refreshed file back to `main`.

The UI is intentionally a single retro terminal/CRT dashboard:
- muted green + amber palette
- subtle scanlines
- blinking terminal cursor
- animated contribution cells
- compact contribution stats (total / current streak / longest streak)
- a subtitle line with public repo count, follower count, and account "uptime"
- a top-languages readout (by byte share across your public, non-fork repos) filling the space under the contribution grid
- recent public activity stream

The activity stream comes from GitHub's public user-events endpoint, so it can have some delay and does not guarantee private activity.

## How data is fetched

One combined GraphQL request (needs `GITHUB_TOKEN`, which the workflow already provides) gets the contribution calendar, follower count, public repo count, account creation date, and per-repo language bytes in a single round trip. A separate small REST call gets the public activity feed (no auth needed for that one).

## If the token/API has a bad day

If the GraphQL call fails for any reason (rate limit, revoked token, GitHub outage), the dashboard does **not** fall back to a fake "zero contributions all year" graph — that would misrepresent your activity. Instead it renders the same layout with the stat numbers replaced by `—` and a small `(live stats unavailable — showing cached layout)` note under the title, so the dashboard still looks intentional instead of broken. Check the Action's run log for the actual error if you see this on the live profile.

## Known limits

- `skillicons.dev` and `komarev.com` (used for the tech-stack icons and the profile-view counter in `README.md`) are third-party services outside this repo's control — if either goes down, that one image just won't load; nothing else in the README depends on them.
- Top languages are computed from each repo's primary-language byte counts as GitHub reports them, across your public, non-fork, owned repositories (up to the 100 most recently pushed) — it won't include forks or private repos.
