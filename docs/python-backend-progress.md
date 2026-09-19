# Python backend rework — progress

Live checklist. See `docs/python-backend-plan.md` for the reasoning behind
each phase. Update this file as work lands so the task is easy to resume.

## Status

| Step | Status | Notes |
|---|---|---|
| Plan written | ✅ done | `docs/python-backend-plan.md` |
| Step 0 — `db.*` seam in `index.html` | ✅ done | Every `supabaseClient.*` call (auth, table CRUD, RPCs, realtime) moved into a `db` object, thin pass-throughs, zero behavior change. Verified: inline script still parses (`new Function`), app still boots to the login/connect screen in headless Chromium with no new console errors. |
| Phase 1 — FastAPI skeleton + auth | ⬜ not started | |
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
  `db.subscribeRealtime`, bulk import/export helpers, etc). Next: Phase 1
  FastAPI skeleton.
