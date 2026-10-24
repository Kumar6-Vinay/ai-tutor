# AI Tutor (Class 1–3 maths; FastAPI + SQLite + vanilla JS)

Deterministic tutor for 2-digit add/subtract. An LLM may only reword a line; it never decides teaching or touches numbers. README.md has the API table and deploy notes.

## Commands
- Run: `uvicorn app.main:app --reload`
- Test: `python3 -m pytest -q` (bare `pytest` isn't on PATH here). Single file: `python3 -m pytest -q tests/test_policy.py`
- A Stop hook runs the suite and blocks finishing while tests fail; CI runs the same on push.

## Gotchas
- `app/domain/policy.py` (541 lines) and `static/app.js` (505) are large: read by function, not whole.
- The client never receives expected answers; keep it that way.
- Child data is sensitive: never log names or photos, photos are never stored, never commit keys or `*.db`.
- Env vars: `GEMINI_API_KEY`/`ANTHROPIC_API_KEY` (photos), `TUTOR_ACCESS_CODE`, `TUTOR_DB`, `TUTOR_VISION_MODEL`, `TUTOR_LLM_*`.
- Render free plan has no disk: the DB resets on restart.
- No new dependencies without asking.

## Workflow
- Skills: `/check`, `/review-changes` (before commit/PR), `/deploy-render`. Subagents: `test-fixer`, `security-reviewer`.
- Layer rules load automatically from `.claude/rules/` when you touch `app/domain/` or `tests/`.
- `@claude` on a GitHub issue/PR runs `.github/workflows/claude.yml` (needs `ANTHROPIC_API_KEY` secret).
- When compacting, preserve the list of modified files and the test command.
