-- Fake shop data for trying out the MCP connector on a TEST Supabase project.
--
-- ONLY for a separate test project. Never run this on the live shop.
-- As an extra guard it stops without changing anything if the account already
-- has any products or documents, so it cannot mix fake rows into real data.
--
-- Before running: create the test user in Authentication → Users → Add user
-- (tick "Auto Confirm User"), then put that email on the line below.

do $$
declare
  v_email text := 'test@example.com';   -- ← the test user's email
  v_owner uuid;
  v_today date := (now() at time zone 'Europe/Sofia')::date;
  c1 uuid; c2 uuid; c3 uuid;
begin
  select id into v_owner from auth.users where email = v_email;
  if v_owner is null then
    raise exception 'No user with email %. Create it in Authentication → Users first.', v_email;
  end if;

  if exists (select 1 from public.products where owner_id = v_owner)
     or exists (select 1 from public.documents where owner_id = v_owner) then
    raise exception 'This account already has data. Test data is only added to an empty account.';
  end if;

  insert into public.settings (owner_id) values (v_owner) on conflict (owner_id) do nothing;
  update public.settings
     set company_name = 'Тестов магазин ЕООД', eik = '000000000', address = 'гр. София, ул. Тестова 1',
         next_invoice_no = 1006, next_offer_no = 12, next_credit_no = 3, next_receipt_no = 1
   where owner_id = v_owner;

  insert into public.products (owner_id, name, category, unit, price, stock) values
    (v_owner, 'Домати', 'Зеленчуци', 'кг', 3.20, 40),
    (v_owner, 'Краставици', 'Зеленчуци', 'кг', 2.40, 25),
    (v_owner, 'Ябълки Златна превъзходна', 'Плодове', 'кг', 2.10, 60),
    (v_owner, 'Банани', 'Плодове', 'кг', 2.60, 30),
    (v_owner, 'Сирене краве', 'Млечни', 'кг', 11.50, 8),
    (v_owner, 'Кисело мляко 3,6%', 'Млечни', 'бр', 1.35, 48),
    (v_owner, 'Хляб Добруджа', 'Хлебни', 'бр', 1.60, null),
    (v_owner, 'Мед акациев', 'Други', 'бр', 9.90, 12);

  insert into public.customers (owner_id, name, eik, vat_number, address, phone, email)
    values (v_owner, 'Ресторант Липа ООД', '111111111', 'BG111111111', 'гр. София, ул. Липа 5', '0888 000 001', 'lipa@example.com')
    returning id into c1;
  insert into public.customers (owner_id, name, eik, address, phone)
    values (v_owner, 'Детска градина Слънце', '222222222', 'гр. София, ж.к. Изток', '0888 000 002')
    returning id into c2;
  insert into public.customers (owner_id, name, phone)
    values (v_owner, 'Иван Петров', '0888 000 003')
    returning id into c3;

  insert into public.documents
    (owner_id, doc_type, number, date, customer_id, customer_name, items, vat_rate, subtotal, vat_amount, total, paid, payment_method)
  values
    (v_owner, 'invoice', 1001, v_today - 2, c1, 'Ресторант Липа ООД',
     '[{"name":"Домати","unit":"кг","qty":20,"price":3.2},{"name":"Краставици","unit":"кг","qty":10,"price":2.4}]',
     20, 88.00, 17.60, 105.60, true, 'bank'),
    (v_owner, 'invoice', 1002, v_today - 2, c3, 'Иван Петров',
     '[{"name":"Мед акациев","unit":"бр","qty":2,"price":9.9}]',
     20, 19.80, 3.96, 23.76, true, 'cash'),
    (v_owner, 'invoice', 1003, v_today - 1, c2, 'Детска градина Слънце',
     '[{"name":"Ябълки Златна превъзходна","unit":"кг","qty":15,"price":2.1},{"name":"Кисело мляко 3,6%","unit":"бр","qty":30,"price":1.35}]',
     20, 72.00, 14.40, 86.40, false, 'bank'),
    (v_owner, 'invoice', 1004, v_today, c1, 'Ресторант Липа ООД',
     '[{"name":"Сирене краве","unit":"кг","qty":3,"price":11.5},{"name":"Домати","unit":"кг","qty":5,"price":3.2}]',
     20, 50.50, 10.10, 60.60, true, 'card'),
    (v_owner, 'invoice', 1005, v_today, c3, 'Иван Петров',
     '[{"name":"Банани","unit":"кг","qty":2,"price":2.6},{"name":"Хляб Добруджа","unit":"бр","qty":1,"price":1.6}]',
     20, 6.80, 1.36, 8.16, true, 'cash'),
    (v_owner, 'credit', 2, v_today, c3, 'Иван Петров',
     '[{"name":"Хляб Добруджа","unit":"бр","qty":-1,"price":1.6}]',
     20, -1.60, -0.32, -1.92, true, 'cash'),
    (v_owner, 'offer', 11, v_today, c2, 'Детска градина Слънце',
     '[{"name":"Ябълки Златна превъзходна","unit":"кг","qty":50,"price":2.0}]',
     20, 100.00, 20.00, 120.00, false, 'bank');

  update public.documents set related_invoice_number = 1005
   where owner_id = v_owner and doc_type = 'credit' and number = 2;
  update public.documents set valid_until = v_today + 14
   where owner_id = v_owner and doc_type = 'offer' and number = 11;

  insert into public.cash_entries (owner_id, date, amount, payment_method, note) values
    (v_owner, v_today - 2, 34.50, 'cash', 'Продажби на дребно'),
    (v_owner, v_today - 1, 41.20, 'cash', 'Продажби на дребно'),
    (v_owner, v_today - 1, 18.00, 'card', ''),
    (v_owner, v_today, 27.30, 'cash', 'Продажби на дребно');

  -- The day before yesterday closed by hand (with 1 € missing), yesterday left
  -- for the automatic close, today still open.
  insert into public.cash_closings
    (owner_id, date, counted_cash, note, total_cash, total_card, total_bank, total, invoice_count, entry_count, auto_closed)
  values
    (v_owner, v_today - 2, 57.26, 'Липсва 1 €', 58.26, 0, 105.60, 163.86, 2, 1, false);

  raise notice 'Test data added for %.', v_email;
end $$;
