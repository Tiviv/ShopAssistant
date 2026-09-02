# Свежо и Вкусно — управление

A small offline-style invoicing/inventory app for a produce/grocery wholesale
business, now backed by [Supabase](https://supabase.com) (free tier) instead
of only browser `localStorage`.

## What changed from the original offline version

The original single-file app (kept at `legacy-offline/index.html` for
reference) stored everything in the browser's `localStorage` on one machine,
with manual JSON export/import as the only way to move data between devices.
That has two real risks for a business:

1. **Total data loss** if that one browser/computer is wiped, and
2. **Duplicate invoice numbers** if two devices are used without perfect
   backup discipline (both branches keeping their own separately-incrementing
   counter).

This version fixes both by moving storage to a Supabase project:

- **Real login** (email + password) via Supabase Auth.
- **Live multi-device sync** via Supabase Realtime — edit on one device, see
  it appear on another within a second or two.
- **Server-side atomic invoice/offer/credit numbering** (`supabase/schema.sql`,
  function `next_document_number`) — two devices can never hand out the same
  number, because Postgres row-locks the counter during the increment.
- **Stock now actually moves.** The old app never decremented `Наличност`
  when an invoice was issued. This version calls `adjust_stock` for every
  line item on save (decrements on invoices, restores on credit notes).
- A basic **offline fallback**: the last successfully synced copy of your
  data is mirrored into `localStorage`. If the app can't reach Supabase, it
  shows that cached copy in read-only mode instead of a blank screen — but
  editing is disabled until the connection comes back, since offline edits
  with no conflict resolution is exactly the kind of risk this rewrite was
  meant to remove.

## One-time setup

1. Create a free project at [supabase.com](https://supabase.com).
2. In your Supabase project, open **SQL Editor → New query**, paste the
   contents of `supabase/schema.sql`, and run it. This creates the tables,
   Row Level Security policies, and the two functions described above.
3. In **Settings → API**, copy the **Project URL** and the **anon public**
   key (not the `service_role` key — that one must never be pasted into a
   browser app).
4. Open `index.html` (just double-click it, or host it anywhere — it's a
   static file, no build step). On first run it asks for those two values
   and remembers them in that browser going forward.
5. Create an account (email + password) on the first screen. The first
   login automatically gets an empty `settings` row via a database trigger.
6. Optional: on the **Данни / Резервно копие** tab, use "Качи файл (JSON)"
   to upload `supabase/seed-data.json` — the same 52-product starter catalog
   from before — or an old backup exported from `legacy-offline/index.html`,
   to migrate existing data in.

Everyone who needs access (owner + staff) can either share that one login,
or — if you want separate named logins later — say so and I'll add a
`business_id` + membership table so multiple accounts can share one shop's
data without sharing a password.

## Cost

Supabase's free tier (500MB database, 50k monthly active users, 2GB file
storage) comfortably covers years of invoices for a business this size.
Nothing here should require a paid plan unless the business grows
substantially.

## Known limitations / next steps

- No offline *writing* — you can view cached data without a connection, but
  can't create invoices until back online. A real offline queue with
  conflict resolution is possible later but is meaningfully more complex;
  worth doing only if the shop genuinely operates disconnected for long
  stretches.
- Money fields use `numeric(12,2)` in Postgres now (exact decimal), which
  also fixes the old floating-point rounding drift risk from the offline
  version's plain JS `number` math.
- No access control tiers yet (owner vs. staff) — anyone logged into the
  shared account has full read/write. Worth adding once there's more than
  one person truly needing separate accountability.
