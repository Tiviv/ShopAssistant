-- ShopAssistant — start the shop from a clean slate, keeping the products
--
-- Deletes every invoice, offer, credit note and receipt, every cash register
-- entry and closed day (so all reports start empty), and sets the document
-- numbers back to 1. Products, categories and the company details stay.
--
-- THIS CANNOT BE UNDONE. Download a backup in the app first:
--   Данни / Резервно копие → Изтегли резервно копие (JSON).
--
-- Replace the e-mail below with the shop owner's account, then Run.

begin;

create temp table reset_target on commit drop as
  select id from auth.users where email = 'SHOP_OWNER@example.com';

do $$
begin
  if (select count(*) from reset_target) <> 1 then
    raise exception 'No account with that e-mail: nothing was deleted.';
  end if;
end $$;

delete from public.documents     where owner_id in (select id from reset_target);
delete from public.cash_entries  where owner_id in (select id from reset_target);
delete from public.cash_closings where owner_id in (select id from reset_target);

-- The first real invoice gets number 1. If the shop already issues invoices
-- on paper, put the next free number here instead (it can also be changed
-- later in Настройки).
update public.settings
   set next_invoice_no = 1, next_offer_no = 1, next_credit_no = 1, next_receipt_no = 1,
       updated_at = now()
 where owner_id in (select id from reset_target);

-- Optional: remove "--" to also delete the test customers.
-- delete from public.customers where owner_id in (select id from reset_target);

-- Optional: remove "--" to clear stock on every product, so the shop enters
-- its own counts (the test invoices have already moved the old ones).
-- update public.products set stock = null where owner_id in (select id from reset_target);

commit;

-- What is left:
select
  (select count(*) from public.products  p where p.owner_id = u.id) as products,
  (select count(*) from public.customers c where c.owner_id = u.id) as customers,
  (select count(*) from public.documents d where d.owner_id = u.id) as documents
from auth.users u where u.email = 'SHOP_OWNER@example.com';
