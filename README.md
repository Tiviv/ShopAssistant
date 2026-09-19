# ShopAssistant / Магазинер

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
- **Two languages** — the whole interface is available in Bulgarian
  (*Магазинер*) and English (*ShopAssistant*), switchable at any time with
  the БГ / EN toggle; see [Language](#language) below.
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
6. Optional: on the **Данни / Резервно копие** / **Data / Backup** tab, use
   "Качи файл (JSON)" / "Upload file (JSON)"
   to upload `supabase/seed-data.json` — the same 52-product starter catalog
   from before — or an old backup exported from `legacy-offline/index.html`,
   to migrate existing data in.

### Backup and restore

**Изтегли резервно копие** writes the whole account to one JSON file: company
settings, the category list, products, customers, every document, and the cash
register's closings and retail entries.

**Качи файл** reads that file back, in one of two modes:

- **Добави към текущите** (default) — nothing is deleted. A record is skipped
  only when it matches an existing one *exactly*: every field a person could
  have typed, compared character by character, with money normalised to two
  decimals. A one-cent difference, a changed note, an extra space in an address
  — any of those make it a different record, and it is added rather than
  silently merged. Ids and timestamps are ignored in the comparison, since they
  differ on every install and would make every record look new.
- **Замени всичко** — deletes everything in the cloud and leaves only the file's
  contents. It asks for the word `ЗАМЕНИ` / `REPLACE` to be typed, after showing
  exactly how many records of each kind will be destroyed.

Before a replace deletes anything, the current data is saved twice: a backup
file is downloaded, and a snapshot is kept inside the app. That snapshot puts a
**Върни предишното състояние** card on this tab, which restores the data exactly
as it was just before the replace — so an import into the wrong account is one
click to undo, without having to find the downloaded file.

Two things the import is careful about. Documents are re-linked to their
customer rows by name and ЕИК, rather than keeping only a name. And the invoice,
offer and credit-note counters only ever move *forward* — taking the highest of
what the file says, what the account already had, and the highest number
actually imported — because rolling a counter back would eventually hand out an
invoice number that already exists on paper.

### Invoicing by department

A line on an invoice or quote can be a **whole department** instead of a
specific product — "Плодове, 20 кг" or a flat "Други — 20,00 €". The picker on
each line lists your products first and your departments below them, so one
invoice can mix both freely.

Each department line is priced one of two ways, chosen on the line itself:

- **× цена** — unit, quantity and unit price, exactly like a product line.
- **обща сума** — a single amount, with no quantity. On the printed sheet such
  a line shows only the description and the amount, leaving unit, quantity and
  unit price blank.

Department lines deliberately **do not move stock**: there is no single product
to decrement for "20 kg of fruit". Product lines still do, as before. Credit
notes handle both — a flat-amount line is credited by amount rather than by
quantity, so you can return €12.50 of a €20.00 line.

Departments are **the same list as product categories** — one list, used in
both places. It starts as the seven built-in categories and grows: pick
"+ Нова категория…" in either the product form or an invoice line to add one,
and it is immediately available in both. Added categories show exactly as
typed in both languages, since they are your words rather than part of the
interface.

The full list is managed under **Настройки → Категории**, where each entry can
be renamed or removed — built-in ones included, since there is no reason a shop
that never sells sweets should be stuck with "Сладки". Three rules keep that
from losing data:

- **Renaming moves the products with it.** Every product filed under the old
  name is updated in the same step, so the old name cannot reappear in the list
  as a still-in-use category.
- **A category in use cannot be deleted.** The app says how many products are
  filed under it; move them first.
- **Documents already issued keep the wording they were issued with.** A rename
  today does not rewrite an invoice from last month — that is a record, not a
  label. Old invoices therefore still show the old department name, which is
  intended.

### Language

Every screen is translated. The toggle sits in the top-right of the
login/setup cards before you sign in, and at the bottom of the sidebar (or
the slide-out menu on a phone) afterwards. The choice is remembered per
browser, so each person can use the app in whichever language they prefer
on their own device.

Two things stay Bulgarian on purpose, because they are *data*, not
interface: product categories and units (`кг`, `Плодове`, …) are stored in
the database as written, and are only shown with an English label where one
exists; and anything you typed yourself — company name, addresses, customer
names, notes — is shown exactly as entered.

Printed documents follow their own rule, not the interface toggle:

- **Invoices and credit notes always print in Bulgarian**, whatever language
  the app is in. They are accounting documents that go to Bulgarian customers
  and to your accountant, so their language shouldn't depend on who happened
  to be looking at the screen. When the interface is in English, the print
  view says so above the sheet.
- **Quotes/offers are your choice.** The print view has its own БГ / EN
  toggle, so you can send an English quote to a foreign buyer and a Bulgarian
  one to everybody else. It starts on the interface language and resets each
  time you open a quote — it never changes the saved document, only how this
  printout reads.

### Password reset

The login screen has a "Забравена парола?" / "Forgot password?" link: enter the account email,
Supabase emails a recovery link, and opening it brings you back to the app
on a "Нова парола" screen to set a new one.

Two things in the Supabase dashboard have to be right for this to work:

1. **Authentication → URL Configuration** — the app's address must be listed
   under *Site URL* or *Redirect URLs* (e.g.
   `https://tiviv.github.io/ShopAssistant/`). Without it the recovery link
   bounces to Supabase's default URL instead of the app, and the reset
   appears to do nothing.
2. **Email delivery** — Supabase's built-in email sender is rate-limited to
   a handful of messages per hour and is meant for testing. For day-to-day
   use, configure custom SMTP under *Authentication → Emails*.

Locked out right now and can't wait for an email? An owner can also reset a
password directly from **Authentication → Users** in the Supabase dashboard
(the row's "…" menu offers a password-recovery / reset action).

### Sharing a ready-to-open link

Anyone who opens the plain `index.html` URL has to paste in the Project URL
and anon key by hand before they even reach login — fine for you, but
friction for someone you just want to try the app out. Instead, share:

```
https://tiviv.github.io/ShopAssistant/?url=<Project URL>&key=<anon key>
```

Opening that link auto-fills the connection and drops the visitor straight
on the login/signup screen — it only kicks in on a browser with no saved
connection yet, so it never overwrites your own setup. If they sign up
fresh, they get their own empty, isolated dataset (Row Level Security keeps
it separate from yours); share your actual login instead if you want them
to see your data. The anon key is meant to be shared this way — it's the
public key, safe outside the browser, not the secret `service_role` key.

### Updating an existing project's schema

`supabase/schema.sql` is safe to re-run in full any time it changes — every
statement is written to be a no-op on things that already exist. If you
already ran it once, just re-run the whole file again in the SQL Editor to
pick up new tables/columns (e.g. the `payment_method` column and
`cash_closings` table added for the Каса tab).

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
