# Python backend rework — progress

Live checklist. See `docs/python-backend-plan.md` for the reasoning behind
each phase. Update this file as work lands so the task is easy to resume.

## Status

| Step | Status | Notes |
|---|---|---|
| Plan written | ✅ done | `docs/python-backend-plan.md` |
| Step 0 — `db.*` seam in `index.html` | ✅ done | Every `supabaseClient.*` call (auth, table CRUD, RPCs, realtime) moved into a `db` object, thin pass-throughs, zero behavior change. Verified: inline script still parses (`new Function`), app still boots to the login/connect screen in headless Chromium with no new console errors. |
| Phase 1 — FastAPI skeleton + auth | ✅ done | `backend/` — FastAPI + async SQLAlchemy + Alembic, `users`/`settings` tables, signup/login/JWT, `/health`. Settings row auto-created on signup. Verified end-to-end against a real local Postgres (signup, login, `/me`, wrong-password rejection, duplicate-email rejection) and with an automated pytest suite (`backend/tests/`). See `backend/README.md` for setup. |
| Phase 2 — Products | ⬜ not started | |
| Phase 3 — Customers | ⬜ not started | |
| Phase 4 — Documents (numbering + stock) | ⬜ not started | |
| Phase 5 — Cash register + day closing | ⬜ not started | |
| Phase 6 — Realtime | ⬜ not started | |
| Phase 7 — Backup/restore + XLSX | ⬜ not started | |

## Log

- 2026-09-19 — Branch `feature/python_backend` created off `main`. Plan
  written. Starting Step 0.
- 2026-09-19 — Step 0 done: all ~40 `supabaseClient.*` call sites in
  `index.html` now go through a `db` object (`db.auth.*`, `db.insertRow`,
  `db.updateRow`, `db.deleteRow`, `db.nextDocumentNumber`, `db.adjustStock`,
  `db.subscribeRealtime`, bulk import/export helpers, etc).
- 2026-09-19 — Phase 1 done: `backend/` FastAPI app scaffolded (SQLAlchemy
  async + Alembic + JWT auth via passlib/python-jose). One gotcha worth
  recording: passlib 1.7.4's self-test crashes against bcrypt>=4.1 (raises
  instead of truncating on a >72-byte string) — pinned `bcrypt==4.0.1` in
  `requirements.txt` to work around it. Also switched the DB engine to
  `NullPool` (see comment in `app/database.py`) after pooled connections
  broke across event loops in tests/reloads. Next: Phase 2, products CRUD,
  plus pointing the frontend's `db.listProducts`/`db.insertRow("products",
  ...)`/etc. at this API behind a toggle.
