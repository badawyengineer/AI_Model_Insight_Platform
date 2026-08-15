# dashboard/live/ — Milestone 12: Live Monitoring Dashboard

A Streamlit dashboard showing real-time prediction volume, latency, and
drift status for every model flowing through the Milestone 11 streaming
pipeline. Auto-refreshes every 10 seconds.

## Why Streamlit, and why split into `data.py` + `app.py`

Every other visualization in this project (`warehouse/analytics.sql`,
the Power BI assets) targets a BI-tool audience reading historical
training-experiment data. This dashboard's job is different — showing
what's *currently* happening in the streaming/monitoring layer — which
is a smaller, more operational surface that a lightweight Python-only
tool serves well without adding a JS build step to the project.

`dashboard/live/data.py` holds every query as a plain function
returning a `pandas.DataFrame`/`dict` — no Streamlit imports. This
means the actual data logic is testable with ordinary `pytest` against
a real database (see `tests/test_dashboard_data.py`), without needing
to drive a running Streamlit session to verify a query is correct.
`dashboard/live/app.py` is the thin UI layer on top.

**The drift PSI shown here is computed by calling
`monitoring.drift_detection.compute_psi()` directly** — not
reimplemented — so the dashboard can never show a different drift
number than what actually triggers a real alert.

## Usage

```bash
# Make sure there's data flowing first (see streaming/README.md):
python -m streaming.producer --simulate 500 --drift-after 250
python -m streaming.consumer --once

streamlit run dashboard/live/app.py
```

Open http://localhost:8501.

## Tests

```bash
pytest tests/test_dashboard_data.py -v   # needs real Redis + PostgreSQL (skips gracefully otherwise)
```

---

# CI/CD (Milestone 12)

Three GitHub Actions workflows under `.github/workflows/`:

| Workflow | Runs on | What it verifies |
|---|---|---|
| `tests.yml` | every push/PR | `ruff check .`, then the full `pytest` suite against **real** Postgres + Redis service containers, then the Airflow DAG structural tests |
| `docker.yml` | push/PR touching `docker/`, `docker-compose.yml` | Actually builds every image (`app`, `mlflow`, `airflow-*`) and smoke-tests that the `app` image can import the project |
| `terraform.yml` | push/PR touching `terraform/` | `terraform fmt -check` + `terraform validate` (no AWS credentials needed — validate never talks to AWS) |

**Why this matters beyond "tests run automatically":** this project was
developed in a sandbox whose network policy blocks Docker Hub entirely
and couldn't install the Terraform CLI at all. Milestones 9 and 10 were
therefore only verified as far as "Docker/HCL parses correctly" during
development. GitHub Actions runners have normal internet access, so
`docker.yml` and `terraform.yml` are the first *real* build/validate
verification those milestones get — once this is pushed and the
workflows run, check the Actions tab to see them pass for real.

Lint config lives in `pyproject.toml` (`[tool.ruff]`) — deliberately
permissive (catches real bugs: unused imports, undefined names; doesn't
enforce line-length or reformat 11 milestones of already-working,
already-tested code retroactively).
