# Python backend rework — progress

Live checklist. See `docs/python-backend-plan.md` for the reasoning behind
each phase. Update this file as work lands so the task is easy to resume.

## Status

| Step | Status | Notes |
|---|---|---|
| Plan written | ✅ done | `docs/python-backend-plan.md` |
| Step 0 — `db.*` seam in `index.html` | ✅ done | Every `supabaseClient.*` call (auth, table CRUD, RPCs, realtime) moved into a `db` object, thin pass-throughs, zero behavior change. Verified: inline script still parses (`new Function`), app still boots to the login/connect screen in headless Chromium with no new console errors. |
| Phase 1 — FastAPI skeleton + auth | ✅ done | `backend/` — FastAPI + async SQLAlchemy + Alembic, `users`/`settings` tables, signup/login/JWT, `/health`. Settings row auto-created on signup. Verified end-to-end against a real local Postgres (signup, login, `/me`, wrong-password rejection, duplicate-email rejection) and with an automated pytest suite (`backend/tests/`). See `backend/README.md` for setup. |
| Phase 2 — Products | ✅ done | `backend/app/routers/products.py` — list/create/update/delete + a `rename-category` bulk endpoint, all owner-scoped (tested for cross-owner isolation: 404, not 403, on someone else's id). Frontend: a new optional "Python backend" connection (`pyBackend` in `index.html`, separate from the Supabase one) with a small settings card (connect/disconnect, signup-or-login prompts). `db.listProducts`/`insertRow`/`updateRow`/`deleteRow`/`renameProductsCategory` branch to the Python API when connected, Supabase otherwise — same call sites as before, only the `db` function bodies changed, per the Step 0 seam. Known gap (documented in the UI): while connected, products are left out of the JSON backup/restore and don't get Supabase's realtime push to other tabs/devices — both are explicitly later phases (7 and 6). Verified against the live backend from inside a real browser page (signup → list → insert → update → rename-category → delete → disconnect fallback), plus new backend pytest coverage. |
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
  broke across event loops in tests/reloads.
- 2026-09-19 — Phase 2 done: products CRUD + category rename on the
  backend, wired into the frontend behind a new, independent "Python
  backend" connection (Settings tab). Supabase still gates login for
  everything else — this only redirects product writes once connected.
  CORS relaxed to `allow_origins=["*"]` with `allow_credentials=False`
  (safe: Bearer-token auth isn't a "credentialed" request in the CORS
  sense), mainly so a plain `file://` `index.html` (Origin: `null`) still
  works without per-origin config. Next: Phase 3, customers.
