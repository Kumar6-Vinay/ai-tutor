# AI Tutor (Class 1–3 maths, FastAPI + SQLite + vanilla JS)

Deterministic tutor for 2-digit add/subtract. An LLM may only reword a line; never let it decide teaching or touch numbers. README.md has the API table and deploy notes; don't duplicate it here.

## Commands
- Install: `pip install -r requirements-dev.txt`
- Run: `uvicorn app.main:app --reload` (http://127.0.0.1:8000)
- Test: `python3 -m pytest -q` (fast; run after every change). One file: `pytest -q tests/test_policy.py`
- CI (`.github/workflows/ci.yml`) just runs `pytest -q` on Python 3.13.

## Architecture
- `app/domain/` pure logic, **no I/O** (maths_engine, curriculum, help_ladder, learner_model, policy). Keep it that way.
- `app/services/` edges: intake (worksheet text + photo via Gemini/Claude), phraser (template default, optional LLM), safety (number-preservation check).
- `app/store.py` SQLite; child identity stored apart from learning data.
- `app/main.py` FastAPI routes. `static/` browser client; it renders server actions and never receives expected answers.
- Biggest files: `app/domain/policy.py` (541 lines), `static/app.js` (505). Read by function, not whole file.

## Rules
- Any change to policy/learner model/maths engine needs a test in the matching `tests/test_*.py`.
- Child-facing text must pass `services/safety.py`; keep LLM output optional with template fallback.
- Child data is sensitive: no logging of names/photos; photos are never stored.
- Env vars: `GEMINI_API_KEY`/`ANTHROPIC_API_KEY` (photos), `TUTOR_ACCESS_CODE`, `TUTOR_DB`, `TUTOR_VISION_MODEL`, `TUTOR_LLM_*`. Never commit keys or `*.db`.
- Deploys via `render.yaml` (free plan, no disk: DB resets on restart).
- Match existing style; no new dependencies without asking.
