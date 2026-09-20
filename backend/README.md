# ShopAssistant backend (Python / FastAPI)

Part of the `feature/python_backend` branch — see
`../docs/python-backend-plan.md` for why this exists and
`../docs/python-backend-progress.md` for what's done so far. `main`
doesn't have this directory; it stays on Supabase.

Currently implemented:
- **Phase 1 — skeleton + auth.** Signup, login, JWT, and the `settings` row
  auto-created on signup (mirrors the Supabase `handle_new_user` trigger).
- **Phase 2 — products.** List/create/update/delete, all scoped to the
  authenticated owner, plus a `rename-category` bulk endpoint (mirrors the
  frontend's category rename, which moves every product filed under the
  old name).
- **Phase 3 — customers.** Same shape: list/create/update/delete, owner-
  scoped.
- **Phase 4 — documents** (invoices/offers/credit notes). List/create, an
  edit endpoint limited to the fields a document can actually change after
  creation (type, number and the offer/invoice/credit relations are fixed
  at creation), separate endpoints for toggling `paid` and linking a
  customer (both partial patches, not a full-row replace), delete, and
  `POST /documents/next-number` — an atomic, race-free counter (a single
  `UPDATE ... RETURNING`, same row-lock guarantee the old Postgres function
  gave). Stock movement is `POST /products/{id}/adjust-stock`.
- **Phase 5 — cash register.** `cash_entries` (walk-in/till sales) is plain
  owner-scoped CRUD. `cash_closings` is keyed by `(owner_id, date)` rather
  than an id, so it gets `PUT`/`DELETE /cash_closings/{date}` instead
  (upsert to close a day, delete to reopen it). Auto-closing forgotten days
  — `POST /cash_closings/close-forgotten-days` — is one raw SQL statement
  mirroring `close_finished_days()` from `supabase/schema.sql` closely on
  purpose, so the money aggregation can't drift from the original. No cron
  job calls this here; the frontend calling it on every load (as the
  original schema's own fallback for a project without `pg_cron` already
  does) is the only mechanism, by design.
- **Phase 6 — realtime.** A real WebSocket (`GET /ws?token=...`), not
  polling — an in-process `ConnectionManager` (`app/realtime.py`) tracks
  each owner's open sockets and every mutating endpoint broadcasts
  `{"table": "..."}` to them after its commit. The token rides a query
  param rather than the `Authorization` header, since a browser can't set
  custom headers on a WebSocket handshake. In-process only: a
  multi-instance deployment would need a shared layer (Redis pub/sub or
  similar) instead — not built speculatively before it's ever needed.
- **Phase 7 — backup/restore.** No new endpoints — JSON export and the
  Excel report already worked, since both just read data the frontend
  already has loaded. Only *import* needed anything, and since every table
  already has single-row CRUD, the frontend's bulk import/replace just
  loops those endpoints (`cash_closings` by date, everything else by id)
  instead of calling a bulk one. That trades away the atomicity Supabase's
  single bulk call gave: a network failure mid-import can leave a
  replace/restore partially applied here. The UI says so.

In `index.html`, connect via the "Python backend (experimental)" card on
the Settings tab — it's a separate, optional connection from the Supabase
one; while connected, product, customer, document, and cash-register
writes go here instead of Supabase, changes push live to every other open
tab/device connected to the same account, and JSON backup/restore and the
Excel report all work against this data too. One thing worth knowing: once
documents are backend-managed, Supabase's own invoice/offer/credit
counters stop advancing, so the "next number" shown on the Settings tab
goes stale until you disconnect — the UI says so.

Every phase from the original plan (`docs/python-backend-plan.md`) is
done.

## One-time setup

1. **A Postgres database.** Either:
   - `docker compose up -d` (starts Postgres on `localhost:5433`), or
   - a Postgres you already have — create a database and user for this
     project yourself.
2. **Python deps**, in a virtualenv:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt   # or requirements.txt without the tests
   ```
3. **Config**: `cp .env.example .env` and adjust `DATABASE_URL` to match
   whichever Postgres you're using (the docker-compose one already matches
   the example).
4. **Migrate**: `alembic upgrade head`

## Running

```
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

Try it:
```
curl -X POST localhost:8000/auth/signup -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"something-long"}'
# -> {"access_token": "...", "token_type": "bearer"}

curl localhost:8000/products -H "Authorization: Bearer <token from above>"
# -> []
```

## Tests

```
source .venv/bin/activate
python -m pytest
```

These run against the real database from `DATABASE_URL` (no mocks) and
clean up after themselves (anything with an `@example.com` address
starting `test-`). Point `.env` at a disposable database if you'd rather
not run them against your main one.

## Migrations

After changing `app/models.py`:
```
alembic revision --autogenerate -m "describe the change"
```
Then read the generated file in `alembic/versions/` before running
`alembic upgrade head` — autogenerate is a good first draft, not a
guarantee (it won't notice a renamed column, for instance — that comes out
as a drop + an add, which loses data).

## Why these choices

See `../docs/python-backend-plan.md` for the full reasoning. Short version:
FastAPI + async SQLAlchemy + Alembic + our own JWT auth (passlib for
hashing, python-jose for tokens), replacing what Supabase Auth + RLS did.
`NullPool` on the DB engine (see the comment in `app/database.py`) trades
away connection pooling — irrelevant at this app's scale — for sidestepping
an asyncpg/event-loop footgun that otherwise bites on every dev-server
reload and every test run.
