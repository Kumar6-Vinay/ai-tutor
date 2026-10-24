---
paths:
  - "app/domain/**/*.py"
---
- Domain code is pure: no I/O, no imports from `app/services`, `app/store` or `app/main`.
- Every change to policy, learner model, help ladder or maths engine needs a test in the matching `tests/test_*.py`.
- Teaching decisions stay deterministic; no LLM calls here.
