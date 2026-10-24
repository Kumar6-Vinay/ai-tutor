# Class 1–3 Maths Tutor (MVP)

A home tutor for 2-digit addition and subtraction (Class 2). The parent types the problems from the
homework sheet; the tutor checks place value, models one problem, fades help, gives practice and a
word problem, hands the rest back to paper, and writes a short parent report.

All teaching decisions are deterministic code. An LLM is optional and may only reword a line; if it
changes any number or fails the safety check, the original line is used.

## Run

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload        # http://127.0.0.1:8000
pytest -q                            # 60 tests
```

Docker: `docker build -t tutor . && docker run -p 8000:8000 -v tutor-data:/data tutor`

## Layout

```
app/
  domain/            pure logic, no I/O
    maths_engine.py  column arithmetic, step checking, misconception (bug) detection
    curriculum.py    skills, item bank, worked example, word problems
    help_ladder.py   graduated hints, levels 1-6 (auto-escalation stops at 4)
    learner_model.py BKT-style mastery, states, spaced reviews, misconception expiry
    policy.py        session plan, input handling, parent report
  services/
    intake.py        parse typed worksheet text; VisionExtractor is the plug-in point for photos
    phraser.py       TemplatePhraser (default) or LLMPhraser (OpenAI-compatible, optional)
    safety.py        prohibited phrasing, number-preservation check, disclosure detection
  store.py           SQLite; child identity kept apart from learning data
  main.py            FastAPI routes
static/              browser client (renders server actions; Tilli speaks via the browser's speech)
tests/               engine, learner model, policy, services, HTTP API
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/children` | Create profile. Requires `parent_consent: true`. Nickname, class, age band only. |
| DELETE | `/api/children/{id}` | Delete the child and all learning data. |
| GET | `/api/children/{id}/progress` | Skill states, review dates, current observations. |
| DELETE | `/api/children/{id}/observations/{skill}/{bug}` | Parent removes an observation they think is wrong. |
| POST | `/api/worksheets/parse` | `{text}` → items, with out-of-scope items flagged for confirmation. |
| POST | `/api/worksheets/photo` | Raw image body (JPEG/PNG/WebP, max 5 MB) → items with per-problem confidence. 501 unless `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` is set. Limited to 10 photos/hour per visitor, 60/hour overall. |
| POST | `/api/unlock` | `{code}` → sets the access cookie when `TUTOR_ACCESS_CODE` is set. |
| POST | `/api/sessions` | `{child_id, items}` → first action. |
| POST | `/api/sessions/{id}/input` | `{kind: digit|regroup|help|stuck|break|continue|build|number, ...}` → feedback + next action. |
| GET | `/api/sessions/{id}/report` | Parent report. |

The client never receives expected answers; it sends the child's input and renders what comes back.

## Homework photo

On a phone the parent taps "Take a photo of the homework". The browser shrinks the picture and sends it once to
`/api/worksheets/photo`, which asks a vision model to return a fixed list of problems, twice. Gemini (has a free
tier) is used when `GEMINI_API_KEY` is set (default `gemini-2.5-flash`), otherwise Claude when `ANTHROPIC_API_KEY`
is set (default `claude-sonnet-5-5`). Override with `TUTOR_VISION_MODEL`. The model never writes text the child sees. Problems the two passes
disagree on, or that are low confidence, are marked "not sure" for the parent to check before anything starts.
Exercises that are not simple sums are only counted, and left to the parent. Photos are not stored.

```bash
export GEMINI_API_KEY=...      # or ANTHROPIC_API_KEY=...  enables the camera button
```

Note: on Google's free tier, Google may use submitted content to improve its products (check their current terms).
Tell parents to avoid photos showing names or faces; the app says so on the photo screen.

## How the tutor makes sure the homework is learned

- Every problem on the sheet is worked on screen with Tilli. Nothing is quietly handed back to paper.
- Each skill on the sheet gets its own block, easiest first: Tilli shows one, then the child does the rest.
- A problem that needed real help or a wrong try comes back once, a few steps later.
- Each skill ends with a brand-new problem (not on the sheet) the child must do alone. If they can't,
  Tilli shows another and checks again.
- If time runs out (15 min for ages 5-7), unreached problems are listed as "saved for next time" in the parent report.
- The parent report shows each homework problem as: solved alone, solved with help, watched, or saved.

## Going live (Render)

1. Push this repo to GitHub, then in Render choose **New > Blueprint** and pick it (`render.yaml` is read).
2. Fill in the two secrets: `GEMINI_API_KEY` (from Google AI Studio) and `TUTOR_ACCESS_CODE` (a family passcode).
3. Open the https link Render gives you. Enter the passcode once per device (30 days).

The blueprint uses Render's free plan: no disk, so the database resets on every restart, redeploy and idle
spin-down (the first visit after idle also takes about a minute). To keep progress, switch to `starter` plus a disk
(see the comment in `render.yaml`, about $7/month).
With no `TUTOR_ACCESS_CODE` the app is open to anyone with the link: always set one before sharing it.
There is still no parent login, only the shared passcode, and one SQLite file, so this suits a family, not a school.

## Optional LLM wording

Set `TUTOR_LLM_URL` (an OpenAI-compatible chat completions URL), `TUTOR_LLM_KEY` and `TUTOR_LLM_MODEL`.
Unset, the template text is used. Timeouts and errors fall back to the template.

## Not built yet

- Exercises other than 2-digit adding/subtracting (word-only sums, shapes, times tables).
- Speech input; speech output uses the browser voice only.
- Parent login and accounts. The child id is kept in the browser; there is no authentication, so do not deploy publicly as is.
- Session rows keep start and screen timestamps for the session-length cap; per-answer times are not written to the learner record.
- Skills beyond 2-digit addition/subtraction within 99.
- UI/UX polish (next step).
