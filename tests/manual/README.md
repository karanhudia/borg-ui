# Manual tests

Not collected by pytest (`collect_ignore` in `tests/conftest.py`) and not part
of any CI job: everything here needs a running Borg UI. Run a script
explicitly, for example `python3 tests/manual/test_app.py --url http://localhost:8081`;
the smoke runners under `tests/smoke/` drive the same scripts against a live
server. pytest still collects the wrapper when given an explicit path, a file
or this directory: `pytest tests/manual`.
