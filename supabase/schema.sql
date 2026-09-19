-- ShopAssistant / "Свежо и Вкусно" — Supabase schema
-- Run this once in your Supabase project's SQL editor (Dashboard → SQL Editor → New query → Run).
-- Safe to re-run: uses "if not exists" / "create or replace" throughout.

-- ---------------------------------------------------------------------
-- 1. Tables
-- ---------------------------------------------------------------------
-- Every table is scoped by owner_id = auth.uid(), and Row Level Security
-- (below) makes sure a logged-in user can only ever see/write their own
-- rows. If several people (owner + staff) should share one shop's data,
-- have them log in with the same account — see README.md for the
-- multi-login alternative if you outgrow that.

create table if not exists public.settings (
  owner_id uuid primary key references auth.users(id) on delete cascade,
  company_name text not null default '',
  eik text not null default '',
  vat_number text not null default '',
  address text not null default '',
  mol text not null default '',
  iban text not null default '',
  next_invoice_no int not null default 1,
  next_offer_no int not null default 1,
  next_credit_no int not null default 1,
  updated_at timestamptz not null default now()
);

create table if not exists public.products (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  category text not null default '',
  unit text not null default '',
  price numeric(12,2) not null default 0,
  stock numeric(12,2),
  created_at timestamptz not null default now()
);

create table if not exists public.customers (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  eik text not null default '',
  vat_number text not null default '',
  address text not null default '',
  phone text not null default '',
  email text not null default '',
  created_at timestamptz not null default now()
);

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  doc_type text not null check (doc_type in ('invoice', 'offer', 'credit')),
  number int not null,
  date date not null,
  customer_id uuid references public.customers(id) on delete set null,
  customer_name text not null default '',
  customer_snapshot jsonb,
  items jsonb not null default '[]'::jsonb,
  vat_rate numeric(5,2) not null default 20,
  subtotal numeric(12,2) not null default 0,
  vat_amount numeric(12,2) not null default 0,
  total numeric(12,2) not null default 0,
  paid boolean not null default false,
  related_invoice_number int,
  converted_from_offer_id uuid,
  created_at timestamptz not null default now()
);

-- Custom product/department categories the shop added on top of the built-in
-- list. One shared list: the same names appear in the product form and in the
-- department lines on an invoice. Built-in categories are not stored here —
-- only additions — so the defaults stay translatable.
alter table public.settings add column if not exists categories jsonb not null default '[]'::jsonb;

-- "create table if not exists" above is a no-op if the table already exists
-- (i.e. on a database that ran a previous version of this schema), so the
-- new column needs its own idempotent statement to actually land there too.
alter table public.documents add column if not exists payment_method text not null default 'cash';

do $$
begin
  alter table public.documents add constraint documents_payment_method_check check (payment_method in ('cash', 'card', 'bank'));
exception when duplicate_object then null;
end $$;

-- One row per calendar day: what the till was counted at, vs. what invoices for
-- that day say it should hold. Lets a shop close out a day the way a physical
-- till/Z-report would, without needing an actual POS terminal.
create table if not exists public.cash_closings (
  owner_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  counted_cash numeric(12,2) not null default 0,
  note text not null default '',
  closed_at timestamptz not null default now(),
  primary key (owner_id, date)
);

-- Closing a day stores that day's sums next to the counted cash, so a closed
-- day keeps the figures it was closed on even if an invoice for that date is
-- edited afterwards. Nullable on purpose: a day closed before these columns
-- existed has no snapshot, and the app recounts it live instead of showing 0.
alter table public.cash_closings add column if not exists total_cash numeric(12,2);
alter table public.cash_closings add column if not exists total_card numeric(12,2);
alter table public.cash_closings add column if not exists total_bank numeric(12,2);
alter table public.cash_closings add column if not exists total numeric(12,2);
alter table public.cash_closings add column if not exists invoice_count int;
alter table public.cash_closings add column if not exists entry_count int;

-- Set on a day nobody closed by hand, which the scheduled job in section 7
-- closed on its own. The till was never counted on such a day, so the app
-- shows "not counted" rather than a difference against counted_cash = 0.
alter table public.cash_closings add column if not exists auto_closed boolean not null default false;

-- Walk-in / cash-register sales that never go through the invoice flow
-- (e.g. a private individual buying in person). Each row is one manual
-- till entry for a day, counted toward that day's expected cash/card/bank
-- totals on the Каса tab alongside invoices.
create table if not exists public.cash_entries (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  amount numeric(12,2) not null default 0,
  payment_method text not null default 'cash',
  note text not null default '',
  created_at timestamptz not null default now()
);

do $$
begin
  alter table public.cash_entries add constraint cash_entries_payment_method_check check (payment_method in ('cash', 'card', 'bank'));
exception when duplicate_object then null;
end $$;

create index if not exists documents_owner_doctype_idx on public.documents (owner_id, doc_type);
create index if not exists products_owner_idx on public.products (owner_id);
create index if not exists customers_owner_idx on public.customers (owner_id);
create index if not exists cash_entries_owner_date_idx on public.cash_entries (owner_id, date);

-- ---------------------------------------------------------------------
-- 2. Row Level Security — each user only ever sees their own data
-- ---------------------------------------------------------------------
alter table public.settings enable row level security;
alter table public.products enable row level security;
alter table public.customers enable row level security;
alter table public.documents enable row level security;
alter table public.cash_closings enable row level security;
alter table public.cash_entries enable row level security;

drop policy if exists "own settings" on public.settings;
create policy "own settings" on public.settings
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists "own products" on public.products;
create policy "own products" on public.products
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists "own customers" on public.customers;
create policy "own customers" on public.customers
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists "own documents" on public.documents;
create policy "own documents" on public.documents
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists "own cash closings" on public.cash_closings;
create policy "own cash closings" on public.cash_closings
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists "own cash entries" on public.cash_entries;
create policy "own cash entries" on public.cash_entries
  for all using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- ---------------------------------------------------------------------
-- 3. Atomic invoice/offer/credit-note numbering
-- ---------------------------------------------------------------------
-- This is the fix for the #1 real risk in the old offline app: two
-- devices handing out the same invoice number. The UPDATE below takes a
-- row lock on the caller's settings row, so two simultaneous calls from
-- two computers are serialized by Postgres and always hand out two
-- different, consecutive numbers.
create or replace function public.next_document_number(p_doc_type text)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_number int;
begin
  if p_doc_type = 'invoice' then
    update settings set next_invoice_no = next_invoice_no + 1, updated_at = now()
      where owner_id = auth.uid()
      returning next_invoice_no - 1 into v_number;
  elsif p_doc_type = 'offer' then
    update settings set next_offer_no = next_offer_no + 1, updated_at = now()
      where owner_id = auth.uid()
      returning next_offer_no - 1 into v_number;
  elsif p_doc_type = 'credit' then
    update settings set next_credit_no = next_credit_no + 1, updated_at = now()
      where owner_id = auth.uid()
      returning next_credit_no - 1 into v_number;
  else
    raise exception 'unknown document type: %', p_doc_type;
  end if;

  if v_number is null then
    raise exception 'no settings row for current user — app should create one on first login';
  end if;

  return v_number;
end;
$$;

-- ---------------------------------------------------------------------
-- 4. Atomic stock adjustment (invoices decrement, credit notes restore)
-- ---------------------------------------------------------------------
-- Fixes the other real gap in the old app: stock never moved when an
-- invoice was issued. Called once per line item with a productId; qty is
-- positive for an invoice line (stock goes down) and negative for a
-- credit-note line (stock goes back up), matching how the app already
-- represents credit-note line items.
create or replace function public.adjust_stock(p_product_id uuid, p_qty numeric)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update products
    set stock = coalesce(stock, 0) - p_qty
    where id = p_product_id and owner_id = auth.uid() and stock is not null;
end;
$$;

-- ---------------------------------------------------------------------
-- 5. Auto-create a default settings row the moment someone signs up
-- ---------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.settings (owner_id) values (new.id)
  on conflict (owner_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------
-- 6. Realtime — lets a second device see changes live
-- ---------------------------------------------------------------------
-- If this errors with "already a member", that's fine — it just means
-- it's already enabled.
do $$
begin
  alter publication supabase_realtime add table public.products;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.customers;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.documents;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.settings;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.cash_closings;
exception when duplicate_object then null;
end $$;

do $$
begin
  alter publication supabase_realtime add table public.cash_entries;
exception when duplicate_object then null;
end $$;

-- ---------------------------------------------------------------------
-- 7. Closing a forgotten day on its own
-- ---------------------------------------------------------------------
-- A day nobody closes is a day whose takings were never written down, and
-- whose figures keep drifting as old invoices are edited. These functions
-- close any finished day that still has no closing, with exactly the sums the
-- Каса tab would have saved. counted_cash stays 0 and auto_closed marks the
-- row, so the app can say the till wasn't counted instead of inventing a
-- difference; reopening the day in the app removes the row and lets it be
-- closed by hand.

-- The shop's own calendar day decides whether a day is over. The database runs
-- in UTC, which is already the next day for part of every evening here.
create or replace function public.shop_today()
returns date
language sql
stable
as $$ select (now() at time zone 'Europe/Sofia')::date $$;

create or replace function public.close_finished_days(p_owner uuid)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_closed int;
begin
  with activity as (
    select d.date, d.payment_method, d.total as amount,
           case when d.doc_type = 'invoice' then 1 else 0 end as invoices, 0 as entries
      from documents d
      where d.owner_id = p_owner and d.doc_type in ('invoice', 'credit')
    union all
    select e.date, e.payment_method, e.amount, 0, 1
      from cash_entries e
      where e.owner_id = p_owner
  ),
  sums as (
    select a.date,
           coalesce(sum(a.amount) filter (where a.payment_method = 'cash'), 0) as total_cash,
           coalesce(sum(a.amount) filter (where a.payment_method = 'card'), 0) as total_card,
           coalesce(sum(a.amount) filter (where a.payment_method = 'bank'), 0) as total_bank,
           coalesce(sum(a.amount), 0) as total,
           sum(a.invoices) as invoice_count,
           sum(a.entries) as entry_count
      from activity a
      where a.date < public.shop_today()
      group by a.date
  )
  insert into cash_closings (owner_id, date, counted_cash, note, closed_at,
                             total_cash, total_card, total_bank, total,
                             invoice_count, entry_count, auto_closed)
  select p_owner, s.date, 0, '', now(),
         s.total_cash, s.total_card, s.total_bank, s.total,
         s.invoice_count, s.entry_count, true
    from sums s
  on conflict (owner_id, date) do nothing;

  get diagnostics v_closed = row_count;
  return v_closed;
end;
$$;

-- What the app calls when it opens, so forgotten days still get closed on a
-- project where pg_cron can't be enabled.
create or replace function public.close_my_finished_days()
returns int
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.uid() is null then return 0; end if;
  return public.close_finished_days(auth.uid());
end;
$$;

-- What the scheduled job calls: every shop on this project.
create or replace function public.close_all_finished_days()
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_owner uuid;
  v_closed int := 0;
begin
  for v_owner in select owner_id from settings loop
    v_closed := v_closed + public.close_finished_days(v_owner);
  end loop;
  return v_closed;
end;
$$;

-- The two above take an owner, or loop over every owner, so neither may be
-- reachable from a browser: PostgREST publishes every function in "public",
-- and one shop must never be able to close another shop's days.
revoke all on function public.close_finished_days(uuid) from public, anon, authenticated;
revoke all on function public.close_all_finished_days() from public, anon, authenticated;
-- The app's own entry point is for a signed-in shop only. Postgres grants
-- execute to PUBLIC by default, so it has to be taken away before granting it
-- to the one role that should have it.
revoke all on function public.close_my_finished_days() from public, anon, authenticated;
grant execute on function public.close_my_finished_days() to authenticated;

-- The scheduled run. Hourly rather than once at midnight, so an hour the job
-- missed (or a project that was paused) still catches up: closing is
-- idempotent, since "on conflict do nothing" leaves an already-closed day
-- exactly as it is, and only days before the shop's today are touched.
do $$
begin
  execute 'create extension if not exists pg_cron with schema extensions';
  perform cron.schedule('shopassistant-close-finished-days', '5 * * * *',
                        'select public.close_all_finished_days();');
exception when others then
  raise notice 'pg_cron is not available here (%) — the app will close forgotten days when it is next opened instead.', sqlerrm;
end $$;
