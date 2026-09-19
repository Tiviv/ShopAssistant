# ShopAssistant backend (Python / FastAPI)

Part of the `feature/python_backend` branch — see
`../docs/python-backend-plan.md` for why this exists and
`../docs/python-backend-progress.md` for what's done so far. `main`
doesn't have this directory; it stays on Supabase.

Currently implemented: **Phase 1 — skeleton + auth.** Signup, login, JWT,
and the `settings` row auto-created on signup (mirrors the Supabase
`handle_new_user` trigger). Products/customers/documents/cash-register
endpoints come in later phases.

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
