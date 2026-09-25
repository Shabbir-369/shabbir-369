# Profile README setup

This package is ready for the `Shabbir-369/shabbir-369` profile repository.

## 1. Copy exactly these files

```text
Shabbir-369/shabbir-369/
├── README.md
└── assets/
    ├── terminal-boot-dark.svg
    └── terminal-boot-light.svg
```

The local header uses relative paths, so it does not depend on a specific branch name.

## 2. Nothing else is required

There is no Python script, GitHub Action, token, build step or scheduled commit in this version.

The live panels use hosted SVG endpoints for public GitHub data. GitHub's official README guidance supports `<picture>` with `prefers-color-scheme` to choose different images for dark and light modes.

## 3. Open the profile

Visit `https://github.com/Shabbir-369` and switch GitHub between light and dark appearance settings. The profile images are set up to load the matching palette automatically.

## Live panels

- **Terminal telemetry:** `github-stats-terminal-style` hosted API
- **Contribution matrix:** `ghchart.xqsit94.in`
- **31-day activity graph:** `github-readme-activity-graph.vercel.app`

These are image-based live/public-data panels, so the README itself stays GitHub-safe and does not need JavaScript.

## Important

Do not bring back the old animated SVG generator. GitHub documents that SVG images are supported, but inline scripting and animation are not supported when viewing SVGs on GitHub.
