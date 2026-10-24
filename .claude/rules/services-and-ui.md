---
paths:
  - "app/services/**/*.py"
  - "static/**/*"
---
- Anything a child sees must pass `services/safety.py` (prohibited phrasing, number preservation); LLM output is optional with a template fallback.
- Photo intake must not store images and must keep the per-visitor/overall rate limits.
- Never send expected answers to the browser.
