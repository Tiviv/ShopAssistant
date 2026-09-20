# Python backend rework — plan

## Why

`main` stays on Supabase — it's the version the shop actually runs on.
This branch (`feature/python_backend`) is a parallel, non-breaking track to
gradually replace Supabase (Postgres + Auth + Realtime + RLS, all called
straight from the browser) with a small FastAPI backend we own. Purpose is
twofold: remove the Supabase dependency long-term, and a hands-on way to
learn Python. No timeline pressure — done "little by little," one resource
at a time, and `main` is never touched by this work.

See `docs/python-backend-progress.md` for the live status/checklist — this
file is the plan itself and shouldn't need to change often.

**Update, Phase 8:** the plan below describes the original design — Python
backend as an optional, independently-toggled connection running *alongside*
Supabase, resource by resource. That held through Phase 7. Once every
resource had a working Python endpoint, the plan changed: Supabase (auth
included) is now fully removed from `index.html` on this branch, and the
Python backend — with its own signup/login and SMTP-based password reset —
is the only way this branch's `index.html` runs. `main` is still untouched
and still Supabase-only. See the "How the two versions coexist" section
below for what that means in practice now, and `docs/python-backend-progress.md`'s
Phase 8 entry for the details.

## Current state (as of this branch's creation)

`index.html` is a single-file vanilla JS SPA, no build step. It talks
directly to Supabase via `supabaseClient.from("table").select/insert/update/
delete(...)` and `supabaseClient.rpc(...)`, called inline at ~40 sites
across event handlers (not centralized). Supabase also provides:

- **Auth** — email/password, session in `supabaseClient.auth`.
- **RLS** — every table scoped by `owner_id = auth.uid()`.
- **Two RPCs with real logic**: `next_document_number` (atomic, row-locked
  counter — the #1 reason this rewrite happened in the first place: two
  devices must never hand out the same invoice number) and `adjust_stock`
  (decrements on invoice lines, restores on credit-note lines).
- **Realtime** — Postgres change feed pushed to other open tabs/devices.
- **pg_cron** — hourly job that closes any calendar day nobody closed by
  hand (`close_all_finished_days`).

Full schema: `supabase/schema.sql`. Tables: `settings` (one row per owner,
holds company info + the three document counters + custom categories),
`products`, `customers`, `documents` (invoice/offer/credit, with a JSON
`items` array and a `customer_snapshot` for one-off buyers), `cash_closings`,
`cash_entries`.

## Target stack

- **Backend**: FastAPI (async).
- **DB**: plain Postgres, owned by us — not Supabase's. SQLAlchemy 2.0
  async + Alembic migrations. Local dev via Docker Compose; hosting
  (Railway/Render/Neon free tier, or self-hosted) is a later decision, not
  needed to start.
- **Auth**: our own — `passlib[bcrypt]` for hashing, JWT access tokens
  (`python-jose`). Replaces Supabase Auth + RLS: ownership becomes an
  explicit `owner_id` FK, checked per-request in each endpoint instead of
  enforced by Postgres policies.
- **Frontend**: stays `index.html` for as long as possible. It gets a
  `db.*` seam (see Step 0) so each resource's calls can point at Supabase
  or the new API independently, toggled at runtime.

## Step 0 — prerequisite refactor (frontend only, no backend yet)

Wrap every `supabaseClient.*` call in `index.html` behind named functions on
a `db` object (`db.listProducts()`, `db.saveProduct(row)`,
`db.nextDocumentNumber(type)`, …). Zero behavior change — this is purely
the seam that makes a resource-by-resource backend swap possible later
instead of a big-bang rewrite. Worth doing even independent of the Python
work.

## Phases (backend, one resource at a time)

Each phase: SQLAlchemy model → Alembic migration → FastAPI router → tests →
point the matching `db.*` function(s) at the new endpoint behind a runtime
toggle, so Supabase stays the default until a phase is verified working.

1. **Skeleton + auth** — FastAPI app, `users` + `settings` tables,
   signup/login/JWT, health check. Port `handle_new_user` (auto-create an
   empty `settings` row on signup).
2. **Products** — simplest CRUD; first resource actually swapped over in
   the frontend, to prove the toggle mechanism end-to-end.
3. **Customers** — same shape as products.
4. **Documents** — the hard phase: port `next_document_number` (needs a
   transaction + row lock, e.g. `SELECT ... FOR UPDATE` on the settings
   row, to keep two devices from colliding) and `adjust_stock`, plus
   offer→invoice conversion and credit-note logic.
5. **Cash register** — `cash_closings`, `cash_entries`, and
   `close_finished_days`. No `pg_cron` outside Postgres-as-a-service, so
   this becomes either an in-process APScheduler job or an endpoint an
   external cron hits (e.g. a scheduled GitHub Action).
6. **Realtime** — deferred. Start with polling/refetch-on-focus; a
   WebSocket endpoint (FastAPI has native support) is a good later
   addition once CRUD is solid.
7. **Backup/restore + XLSX export** — stays client-side either way, since
   it just reads everything through the `db.*` layer.

## How the two versions coexist

- `main` — Supabase, untouched by this work.
- `feature/python_backend` — adds a `backend/` directory alongside the
  existing `index.html`/`supabase/`. The `supabase/` directory and
  `legacy-offline/` are left in place (unused, for reference/history), but
  `index.html` on this branch no longer references Supabase at all: no
  `supabase-js` script tag, no project URL/anon key setup, no Supabase
  auth or realtime. The `db.*` seam still exists, but every function now
  unconditionally calls the Python backend — there's nothing left to
  toggle.
- Merging `main` into this branch for unrelated fixes (e.g. a wording or
  validation fix in a shared function) stays workable, but any Supabase-
  specific hunk `main` touches will conflict or no-op here, since that code
  no longer exists on this branch.

## Open decisions (revisit if they start to matter)

- Where the backend + its DB actually run long-term (local-only while
  learning vs. a free host) — not needed until Phase 1 is working locally.
- Whether to eventually migrate real Supabase data into the new DB, or
  treat this as a from-scratch dataset for as long as it's a study project.
