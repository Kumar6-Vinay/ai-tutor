---
name: check
description: Run the test suite and summarise failures briefly. Use after code changes or when asked to check/verify tests.
---
Run `python3 -m pytest -q`. If everything passes, reply with one line. If anything fails, show only the failing test names and the key assertion, then propose the smallest fix. Do not read unrelated files.
