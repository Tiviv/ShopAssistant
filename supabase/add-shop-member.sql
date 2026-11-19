-- ShopAssistant — let another login work on the same shop's data
--
-- Run in Supabase → SQL Editor AFTER schema.sql. Before running:
--   1. Create the login: Authentication → Users → Add user → Create new user
--      (tick "Auto Confirm User"). This works with sign-ups turned off.
--   2. Replace the two e-mails below: the shop owner's account (the one that
--      holds the data) and the new login.
-- Run once per extra login. Running it again for the same login just moves it
-- to the owner given here.

insert into public.shop_members (user_id, owner_id)
select m.id, o.id
from auth.users m, auth.users o
where m.email = 'NEW_LOGIN@example.com'
  and o.email = 'SHOP_OWNER@example.com'
on conflict (user_id) do update set owner_id = excluded.owner_id;

-- Check: every extra login and whose shop it works on. A login missing here
-- (a typo in an e-mail above) still sees only its own, empty shop.
select m.email as login, o.email as works_on_shop_of, sm.added_at
from public.shop_members sm
join auth.users m on m.id = sm.user_id
join auth.users o on o.id = sm.owner_id
order by sm.added_at;

-- To take a login out of the shop again:
-- delete from public.shop_members where user_id = (select id from auth.users where email = 'NEW_LOGIN@example.com');
