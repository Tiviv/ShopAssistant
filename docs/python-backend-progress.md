# Python backend rework — progress

Live checklist. See `docs/python-backend-plan.md` for the reasoning behind
each phase. Update this file as work lands so the task is easy to resume.

## Status

| Step | Status | Notes |
|---|---|---|
| Plan written | ✅ done | `docs/python-backend-plan.md` |
| Step 0 — `db.*` seam in `index.html` | ✅ done | Every `supabaseClient.*` call (auth, table CRUD, RPCs, realtime) moved into a `db` object, thin pass-throughs, zero behavior change. Verified: inline script still parses (`new Function`), app still boots to the login/connect screen in headless Chromium with no new console errors. |
| Phase 1 — FastAPI skeleton + auth | ✅ done | `backend/` — FastAPI + async SQLAlchemy + Alembic, `users`/`settings` tables, signup/login/JWT, `/health`. Settings row auto-created on signup. Verified end-to-end against a real local Postgres (signup, login, `/me`, wrong-password rejection, duplicate-email rejection) and with an automated pytest suite (`backend/tests/`). See `backend/README.md` for setup. |
| Phase 2 — Products | ✅ done | `backend/app/routers/products.py` — list/create/update/delete + a `rename-category` bulk endpoint, all owner-scoped (tested for cross-owner isolation: 404, not 403, on someone else's id). Frontend: a new optional "Python backend" connection (`pyBackend` in `index.html`, separate from the Supabase one) with a small settings card (connect/disconnect, signup-or-login prompts). `db.listProducts`/`insertRow`/`updateRow`/`deleteRow`/`renameProductsCategory` branch to the Python API when connected, Supabase otherwise — same call sites as before, only the `db` function bodies changed, per the Step 0 seam. Known gap at the time (documented in the UI): products were left out of the JSON backup/restore. Both that and the realtime-sync gap flagged when this phase landed were resolved later — restore in Phase 7, realtime in Phase 6, both below. Verified against the live backend from inside a real browser page (signup → list → insert → update → rename-category → delete → disconnect fallback), plus new backend pytest coverage. |
| Phase 3 — Customers | ✅ done | `backend/app/routers/customers.py` — same shape as products: owner-scoped list/create/update/delete, 404 (not 403) on someone else's id. Frontend: `db.listCustomers`/`insertRow`/`updateRow`/`deleteRow` for `"customers"` now branch the same way products' do — the generic CRUD functions (`insertRow`/`updateRow`/`deleteRow`) were generalized from hardcoded `/products` paths to `` `/${table}` ``, so this needed no new branching logic, just adding `"customers"` to `usingPyBackendFor`'s resource list. The Settings card copy widened accordingly ("products and customers"). Verified against the live backend from inside a real browser page (signup → list → insert → update → delete), including confirming `customerRowToObj`'s snake_case→camelCase mapping works unchanged against the Python API's response shape, plus new backend pytest coverage (CRUD, blank-field defaults, cross-owner isolation). Same known gap as products at the time — left out of JSON backup/restore and realtime — both since resolved (Phase 7 and Phase 6 below). |
| Phase 4 — Documents (numbering + stock) | ✅ done | `backend/app/routers/documents.py` — list/create, an edit `PUT` limited to the mutable fields only (doc_type/number/related_invoice_number/converted_from_offer_id are set once at creation, never editable — matches the frontend exactly), a dedicated `PATCH .../paid` (toggling paid is a partial patch, not a full-body PUT) and `PATCH .../customer` (offer→invoice one-off-buyer linking), delete, and `POST /documents/next-number` — the atomic, race-free counter this whole rewrite exists for. Single `UPDATE ... RETURNING` per call, same row-lock guarantee Postgres gave the old `next_document_number()` function; proven under real concurrency with 20 parallel requests landing on exactly `{1..20}`, no dupes or gaps (`test_next_document_number_is_race_free_under_concurrency`). `adjust_stock` became `POST /products/{id}/adjust-stock` (products-scoped, so it lives in that router) — silently a no-op on an untracked (`stock=null`) or not-owned product, matching the original RPC. Frontend: `db.nextDocumentNumber`/`adjustStock`/`listDocuments`/`linkDocumentCustomer` branch now, plus a new `db.setDocumentPaid` (the generic `updateRow` PUT doesn't fit a partial patch, so `togglePaid()` got its own call). Verified two ways: 20 new backend pytest cases (CRUD, isolation, the concurrency check, stock behavior), and — the real proof — driving the actual frontend functions (`saveDoc`, `editDoc`, `togglePaid`, `beginCreditNote`/`saveCreditNote`, `convertToInvoice`, `deleteDocument`) from inside a live browser page against the running backend: created an invoice, edited its quantity (stock rebalanced correctly), toggled paid, issued a full credit note (stock restored), converted an offer with a one-off buyer into an invoice (customer auto-created and linked, stock decremented), then deleted the original invoice (stock reversed) — every number came out exactly right. New, more consequential gap this phase adds (documented in the UI): once documents are backend-managed, Supabase's own invoice/offer/credit counters stop advancing, so the "next number" shown on the Settings tab goes stale until disconnected — settings/company-info sync itself was never an enumerated phase, so this is flagged rather than fixed here. |
| Phase 5 — Cash register + day closing | ✅ done | `backend/app/routers/cash_entries.py` — plain owner-scoped CRUD, fits the generic `insertRow`/`deleteRow` seam unchanged (`cash_entries` is now just another entry in `usingPyBackendFor`'s list). `backend/app/routers/cash_closings.py` — `cash_closings` has a composite `(owner_id, date)` primary key rather than its own id, so it gets dedicated `PUT/DELETE /cash_closings/{date}` endpoints (upsert / reopen) instead of the generic id-based ones. The interesting piece: `POST /cash_closings/close-forgotten-days`, mirroring `close_finished_days()` in `supabase/schema.sql` — one raw parameterized SQL statement (`UNION ALL` of documents + cash_entries, grouped by date and payment method, `INSERT ... ON CONFLICT (owner_id, date) DO NOTHING`) rather than reimplementing the aggregation in Python, so the money math is exactly Postgres's own arithmetic, not a second implementation that could drift from it. "Today" is computed with `zoneinfo("Europe/Sofia")`, matching `shop_today()`. No cron equivalent exists (or is needed) here — same as the original schema's own documented fallback for a project where `pg_cron` isn't available, closing-on-load *is* the primary mechanism for this backend, not a fallback. Frontend: `listCashClosings`/`listCashEntries`/`upsertCashClosing`/`deleteCashClosing`/`closeMyFinishedDays` now branch; `cash_entries` CRUD needed no new frontend code at all beyond adding it to the resource list. Verified: 6 new backend pytest cases including an aggregation test (invoice total + cash entry, summed correctly by payment method) and an idempotency check (running twice closes nothing the second time), plus — again — driving the real frontend functions (`saveCashEntry`, `saveCashClosing`, `reopenDay`, `closeForgottenDays`, and the day-lock checks in `deleteCashEntry`) against the live backend from inside a browser: saved a till entry, closed the day by hand, confirmed deletion is refused on a closed day and allowed after reopening, then back-dated an invoice two days out and confirmed `closeForgottenDays()` auto-closed exactly that day with the right totals. Same numbering-display gap as Phase 4 (documented in the UI, now also mentioning cash register); no new gaps beyond that. |
| Phase 6 — Realtime | ✅ done | Real WebSocket push, not polling — `backend/app/realtime.py` is a tiny in-process `ConnectionManager` (owner_id → set of open sockets; in-process only, so a multi-instance deployment would need a shared layer like Redis pub/sub, deliberately not built before it's ever needed) plus `GET/websocket /ws?token=...` in `backend/app/routers/realtime.py`. The token travels as a query param, not an Authorization header, because the browser `WebSocket` API can't set custom headers on the handshake — `decode_user_id()` was factored out of `get_current_user` so both paths share the same JWT check. Every mutating endpoint across all five routers (products, customers, documents, cash_entries, cash_closings — ~17 call sites) calls `manager.broadcast(owner_id, table)` after its commit; `close-forgotten-days` only broadcasts when it actually closed something, since the frontend calls it on every load and a closed-nothing run shouldn't nudge every open tab to refetch for no reason. Frontend: a second realtime connection alongside the existing Supabase channel (which keeps covering `settings`, since that resource never moved) — `db.subscribePyRealtime`/`unsubscribePyRealtime`, wired into the existing `setupRealtime()`/`teardownRealtime()` so nothing about *when* realtime gets (re)established had to change, plus a reconnect-once-after-2s on an unintentional drop (`unsubscribePyRealtime` clears `onclose` first, so an intentional disconnect never triggers one). Verified thoroughly: 4 new backend pytest cases (rejects a bad token, delivers a push, cross-owner isolation, coverage across documents/cash tables) using Starlette's `TestClient` (httpx has no WebSocket support, unlike the async client the other tests use) — and, the real proof, two independent browser pages standing in for two devices, both connected to the same account: created a product on page A, watched it appear on page B's `state.products` without B ever calling the mutation itself; deleted it from B, watched it disappear from A. Also drove the reconnect logic directly: force-closed the live socket, confirmed it reconnected within 2s and still worked, and separately confirmed an *intentional* disconnect does not reconnect. |
| Phase 7 — Backup/restore + XLSX | ✅ done | No new backend code at all — the whole phase turned out to be frontend-only. **XLSX export and the JSON backup (export) already worked**, unnoticed until this phase: both just serialize/read `state`, which Phases 2–5 already keep correctly populated regardless of which backend is active — nothing to build. The one real gap was **import/restore**, which does bulk writes (`db.deleteAllRows`, `db.insertRows`, `db.selectAll`), and there were no bulk endpoints. Rather than add transactional bulk endpoints per table, these three now just loop over the *existing* single-row endpoints when the Python backend is active (`pyBulkDelete`/`pyBulkInsert` in `index.html`) — `cash_closings` is keyed by date instead of id, so it's special-cased to hit `PUT`/`DELETE /cash_closings/{date}` instead of the id-based path. Traded off deliberately: a mid-import network failure can now leave a replace/restore partially applied, unlike Supabase's single atomic bulk call — acceptable for a rare, user-initiated operation on a shop-sized dataset; a real bulk endpoint wrapped in one DB transaction would be the natural fix if this ever bit someone in practice, not something to build speculatively. Documented plainly in the Settings card copy rather than glossed over. Verified against the live backend by driving the actual `runImport`/`planImport` functions (not reimplemented test logic): seeded one of everything in account A, captured its `state` as the exact shape `downloadBackup()` would have written, imported it into a fresh account B in "add" mode (all 5 record types landed, including the customer↔document link surviving re-linking-by-identity), re-ran the same import (correctly found nothing new and skipped), then ran "replace" mode (wiped and restored correctly). One thing this surfaced along the way, worth noting for future tests rather than a product bug: `loadAllData()`'s catch-and-fall-back-to-cache behavior means a stubbed dependency returning the wrong shape fails *silently* (falls back to stale/empty state, no thrown error) rather than loudly — cost some time isolating in this phase's own test, good to remember next time something in a browser-driven test looks like a no-op. |

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
  works without per-origin config.
- 2026-09-19 — Phase 3 done: customers CRUD on the backend, same pattern as
  products. Generalized the frontend's `insertRow`/`updateRow`/`deleteRow`
  to route by table name (`` `/${table}` ``) instead of a hardcoded
  `/products` path, now that a second resource uses them — this is the
  shape future phases (documents, cash register) should keep fitting, as
  long as each new router's prefix matches its Supabase table name.
- 2026-09-20 — Phase 4 done: documents (invoices/offers/credit notes) on
  the backend — atomic numbering (`POST /documents/next-number`, proven
  race-free under 20 concurrent requests), stock adjustment
  (`POST /products/{id}/adjust-stock`), edit/paid-toggle/customer-link as
  separate endpoints since they're different shapes of update (full
  replace vs. two kinds of partial patch), delete. Frontend wiring added a
  `db.setDocumentPaid` alongside the existing generic CRUD, since toggling
  paid is a partial patch the generic `updateRow` PUT can't express.
  Verified by driving the real frontend functions (not reimplemented test
  logic) against the live backend from inside a browser: full invoice →
  edit → toggle paid → credit note → offer-to-invoice conversion → delete
  lifecycle, every stock/number/total came out correct. New gap worth
  flagging prominently: Supabase's own document counters stop advancing
  once this is active, so Settings' "next number" display goes stale until
  disconnected — noted in the UI copy, not fixed (settings sync was never
  a planned phase on its own).
- 2026-09-20 — Phase 5 done: cash register (`cash_entries`, `cash_closings`)
  on the backend. `cash_entries` needed zero new frontend branching — it
  just fit the existing `insertRow`/`deleteRow` generic seam once added to
  `usingPyBackendFor`'s list, which is the seam paying off exactly as
  intended three phases in. `cash_closings` needed its own endpoints since
  its primary key is `(owner_id, date)`, not an id. The auto-close-
  forgotten-days logic is one raw SQL statement mirroring the original
  Postgres function almost line for line, specifically so the money
  aggregation can't drift between the two implementations. Verified with
  new pytest coverage (including an aggregation-correctness test and an
  idempotency check) and by driving the real frontend cash-register
  functions against the live backend, including the day-lock behavior.
  This closes out every phase from the original plan except realtime (6)
  and backup/restore (7) — both explicitly deferred from the start.
- 2026-09-20 — Phase 6 done: real WebSocket push (`backend/app/realtime.py`
  + `backend/app/routers/realtime.py`), not the polling the plan floated as
  a fallback — CRUD was solid enough by this point that the real thing
  wasn't much more work. An in-process `ConnectionManager` fans out
  `{table: "..."}` messages to every open socket for an owner; every
  mutating endpoint across all five routers calls `broadcast()` after its
  commit (~17 call sites). Auth travels as a `?token=` query param since
  browsers can't set a custom header on a WebSocket handshake — factored
  `decode_user_id()` out of `get_current_user` so both paths share one JWT
  check. Frontend keeps the existing Supabase channel alongside a new one
  (`db.subscribePyRealtime`), wired into the same `setupRealtime()`/
  `teardownRealtime()` so *when* realtime gets established didn't need to
  change, plus a reconnect-once-after-2s on an unintentional drop. Verified
  properly this time, not just plausibly: two independent browser pages
  standing in for two devices on the same account — created a product on
  one, watched it appear on the other without that page ever calling the
  mutation itself, then deleted it from the second and watched it vanish
  from the first. Also force-closed a live socket and confirmed it
  reconnects within 2s and still works, and confirmed an intentional
  disconnect does not reconnect. Only Phase 7 (backup/restore + XLSX) is
  left from the original plan.
- 2026-09-20 — Phase 7 done, and it turned out smaller than expected: XLSX
  export and the JSON backup (export) needed zero changes, since both just
  read `state`, already correct regardless of backend since Phase 2. Only
  import/restore needed work, and since every table already has full CRUD,
  it needed no new backend endpoints either — `pyBulkDelete`/`pyBulkInsert`
  in `index.html` just loop the existing single-row endpoints instead of
  calling a bulk one. Traded transactional atomicity for that simplicity
  (documented in the UI): unlike Supabase's one bulk call, a network
  failure mid-import can now leave a replace/restore partially applied.
  Verified against the live backend by driving the real `runImport`/
  `planImport` functions: seeded one of everything, captured `state` as
  the exact shape a real backup file would have, imported into a fresh
  account (all 5 tables, customer↔document linking intact), confirmed
  re-importing the same file finds nothing new, then confirmed "replace"
  mode wipes and restores correctly. This was every phase in the original
  plan — `docs/python-backend-plan.md` is fully implemented now, modulo
  the gaps already flagged along the way (Supabase's own invoice/offer/
  credit counters going stale once documents are backend-managed, and
  restore no longer being one atomic step under the Python backend).
