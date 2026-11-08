# Contributing

Use one branch per ticket. Keep pull requests small. Run `python -m ruff check .` and
`python -m pytest -q` before pushing.

The tests in `tests/` and the workflow belong to Wadiline. Add personal tests as new
`learner_tests/test_mine_*.py` files and leave out skip markers. If you change an earlier
personal test, explain why in the pull request.

In the pull request, explain what changed, which case it addresses, how you checked it and
whether you used AI tools. Take the review to GitHub. Use chat for coordination.
