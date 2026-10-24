---
name: review-changes
description: Review the current diff against this repo's rules (pure domain layer, tests for logic changes, child-data safety). Use before committing or opening a PR.
---
Run `git diff main...HEAD` (or `git diff` if uncommitted). Check only:
- `app/domain/` gained no I/O or imports from `app/services`/`app/store`.
- Every change to policy, learner model or maths engine has a matching test.
- Child-facing text still goes through `services/safety.py`; no names, photos or keys are logged or committed.
- No new dependencies. Report findings as a short list with file:line; say "clean" if none.
