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
pytest -q                            # 45 tests
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
| POST | `/api/worksheets/photo` | 501 until a vision service is connected. |
| POST | `/api/sessions` | `{child_id, items}` → first action. |
| POST | `/api/sessions/{id}/input` | `{kind: digit|regroup|help|stuck|break|continue|build|number, ...}` → feedback + next action. |
| GET | `/api/sessions/{id}/report` | Parent report. |

The client never receives expected answers; it sends the child's input and renders what comes back.

## Optional LLM wording

Set `TUTOR_LLM_URL` (an OpenAI-compatible chat completions URL), `TUTOR_LLM_KEY` and `TUTOR_LLM_MODEL`.
Unset, the template text is used. Timeouts and errors fall back to the template.

## Not built yet

- Photo reading (vision model behind `VisionExtractor`, with the confirm step already in place).
- Speech input; speech output uses the browser voice only.
- Parent login and accounts. The child id is kept in the browser; there is no authentication, so do not deploy publicly as is.
- Session rows keep start and screen timestamps for the session-length cap; per-answer times are not written to the learner record.
- Skills beyond 2-digit addition/subtraction within 99.
- UI/UX polish (next step).
