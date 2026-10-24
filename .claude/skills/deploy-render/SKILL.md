---
name: deploy-render
description: Pre-deploy checklist for shipping this app to Render. Use when asked to deploy, release, or go live.
disable-model-invocation: true
---
1. `python3 -m pytest -q` must pass; stop if not.
2. `git status` must be clean and on `main`; confirm with the user before pushing.
3. Check `render.yaml` still sets `healthCheckPath: /api/health` and that `GEMINI_API_KEY` and `TUTOR_ACCESS_CODE` stay `sync: false` (never put real values in the repo).
4. Remind the user: free plan has no disk, so the database resets on restart; set `TUTOR_ACCESS_CODE` before sharing the link.
5. After the push, report that Render auto-deploys from `main`; do not claim the deploy succeeded without checking.
