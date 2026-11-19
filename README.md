# Trench Research data branch

Collected by the daily GitHub Actions job (`.github/workflows/daily.yml` on `main`).

- `raw/`   every upstream response, gzipped, with a manifest per day (immutable).
- `lake/`  write-once Parquet tables; each row carries `fetched_at` and `run_id`.
- `lake/published/`  append-only point-in-time indicator values.
- `usage/` monthly metered-usage ledger for capped providers.

Files are only ever added, never edited or deleted. Do not rewrite this branch's history.

## Notes

- 2026-11-19: `lake/lp_launch_outcomes_v0_exploratory/` holds the first, exploratory Long.xyz cohort output (written 2026-11-18). Its schema differs from the production `lp_launch_outcomes` table (`Lstar` vs `lstar`), so it was moved, not deleted, to keep the two apart.
