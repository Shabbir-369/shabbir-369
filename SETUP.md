# Terminal profile setup

1. Put this repository's contents into the profile repository `Shabbir-369/Shabbir-369`.
2. Keep the repository public.
3. Commit/push the files. The `push` trigger runs the first live sync automatically; you can also use **Actions -> Update terminal profile -> Run workflow** for an immediate manual refresh.
4. After that, the workflow refreshes the generated panels every 15 minutes. GitHub may delay scheduled workflow starts occasionally.

The workflow uses the repository's `GITHUB_TOKEN` to query public GitHub profile data. No personal access token is required for the normal setup.

The README uses GitHub's light/dark `<picture>` pattern, so GitHub selects the matching generated asset for the viewer's theme.

Run `python scripts/generate_profile.py --demo` locally to preview the renderer without network access. Run `python scripts/generate_profile.py --bootstrap` to regenerate the honest pre-sync state.
