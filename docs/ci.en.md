# Continuous integration (CI) and local verification

CI runs Ruff, mypy, and pytest in GitHub Actions. The same commands work in the host virtualenv.

## Local Ruff / mypy / pytest

In the host Python virtualenv, run static analysis (Ruff, mypy) and the test suite (pytest) in order:

```bash
source .venv/bin/activate
pip install -e "port_pick_align/[training,dev]"

# Code style and static type checks
ruff check port_pick_align scripts
ruff format --check port_pick_align scripts
(cd port_pick_align && mypy src/port_pick_align)

# Unit and integration tests
(cd port_pick_align && pytest -m unit -q)
(cd port_pick_align && pytest -m integration -q)
```

## GitHub Actions workflow layout

The pipeline defined in `.github/workflows/ci.yml` uses the following stages:

1. **Parallel Lint and Unit jobs**: format checks, type checks, and fast unit tests run concurrently.
2. **Serial Integration job**: starts after the unit job succeeds and runs integration tests including weight save and inference smoke checks.
