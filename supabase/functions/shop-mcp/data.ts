// Everything the MCP tools may read from the shop, in one narrow interface.
//
// The tools never see a database client. They ask this interface for exactly
// the rows they need, so the list of things an AI assistant can reach is the
// list of methods below and nothing more: no raw SQL, no table names coming
// from the model, no writes.
//
// The real implementation talks to Supabase with the *user's own* access
// token, so Row Level Security (schema.sql, public.shop_owner()) decides which
// shop's rows come back, exactly as it does for the web app. The tests swap in
// an in-memory fake.

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export type DocType = "invoice" | "offer" | "credit" | "receipt";
export type PayMethod = "cash" | "card" | "bank";

export interface DocumentSummary {
  doc_type: DocType;
  number: number;
  date: string;
  customer_name: string;
  total: number;
  paid: boolean;
  payment_method: PayMethod;
}

export interface DocumentItem {
  name?: string;
  unit?: string;
  qty?: number | string;
  price?: number | string;
}

export interface DocumentDetail extends DocumentSummary {
  items: DocumentItem[];
  vat_rate: number;
  subtotal: number;
  vat_amount: number;
  valid_until: string | null;
  payment_note: string | null;
  related_invoice_number: number | null;
}

export interface CashEntry {
  date: string;
  amount: number;
  payment_method: PayMethod;
  note: string;
}

export interface CashClosing {
  date: string;
  counted_cash: number;
  note: string;
  closed_at: string;
  total_cash: number | null;
  total_card: number | null;
  total_bank: number | null;
  total: number | null;
  invoice_count: number | null;
  entry_count: number | null;
  auto_closed: boolean;
}

export interface Product {
  name: string;
  category: string;
  unit: string;
  price: number;
  stock: number | null;
}

export interface Customer {
  name: string;
  eik: string;
  vat_number: string;
  address: string;
  phone: string;
  email: string;
}

export interface ShopInfo {
  company_name: string;
}

export interface DocumentFilter {
  docType?: DocType;
  from?: string;
  to?: string;
  unpaidOnly?: boolean;
  customer?: string;
  limit: number;
}

export interface ShopData {
  shopInfo(): Promise<ShopInfo | null>;
  /** Invoices and credit notes dated on one day (what the till counts). */
  tillDocuments(date: string): Promise<DocumentSummary[]>;
  cashEntries(date: string): Promise<CashEntry[]>;
  closing(date: string): Promise<CashClosing | null>;
  recentClosings(limit: number): Promise<CashClosing[]>;
  searchProducts(query: string, category: string | undefined, limit: number): Promise<Product[]>;
  listDocuments(filter: DocumentFilter): Promise<DocumentSummary[]>;
  getDocument(docType: DocType, number: number): Promise<DocumentDetail | null>;
  searchCustomers(query: string, limit: number): Promise<Customer[]>;
}

/** Thrown for any database failure. The message is safe to show the model. */
export class DataError extends Error {}

/**
 * Turns user text into a literal ILIKE pattern. Without this a search for
 * "%" or "_" would match everything, which is harmless here but surprising.
 * PostgREST also reads "*" as a wildcard and has no escape for it, so it is
 * dropped.
 */
export function likePattern(text: string): string {
  return `%${text.replace(/\*/g, "").replace(/[\\%_]/g, (c) => `\\${c}`)}%`;
}

const SUMMARY_COLUMNS = "doc_type, number, date, customer_name, total, paid, payment_method";
const DETAIL_COLUMNS =
  `${SUMMARY_COLUMNS}, items, vat_rate, subtotal, vat_amount, valid_until, payment_note, related_invoice_number`;
const CLOSING_COLUMNS =
  "date, counted_cash, note, closed_at, total_cash, total_card, total_bank, total, invoice_count, entry_count, auto_closed";

function check<T>(result: { data: T | null; error: { message: string } | null }, what: string): T {
  if (result.error) {
    // The real message goes to the function's logs; the model only learns
    // which lookup failed, so table internals never leak into a chat.
    console.error(`shop-mcp: ${what} failed: ${result.error.message}`);
    throw new DataError(`Не успях да прочета ${what}. Опитайте отново след малко.`);
  }
  return result.data as T;
}

export class SupabaseShopData implements ShopData {
  private db: SupabaseClient;

  /**
   * @param url       the project URL
   * @param anonKey   the project's public (anon / publishable) key
   * @param userToken the caller's own access token: every query runs as them
   */
  constructor(url: string, anonKey: string, userToken: string) {
    this.db = createClient(url, anonKey, {
      global: { headers: { Authorization: `Bearer ${userToken}` } },
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    });
  }

  async shopInfo(): Promise<ShopInfo | null> {
    const rows = check(await this.db.from("settings").select("company_name").limit(1), "данните за фирмата");
    return rows[0] ?? null;
  }

  async tillDocuments(date: string): Promise<DocumentSummary[]> {
    return check(
      await this.db.from("documents").select(SUMMARY_COLUMNS)
        .in("doc_type", ["invoice", "credit"]).eq("date", date)
        .order("number", { ascending: true }).limit(500),
      "документите за деня",
    );
  }

  async cashEntries(date: string): Promise<CashEntry[]> {
    return check(
      await this.db.from("cash_entries").select("date, amount, payment_method, note")
        .eq("date", date).order("created_at", { ascending: true }).limit(500),
      "касовите записи",
    );
  }

  async closing(date: string): Promise<CashClosing | null> {
    const rows = check(
      await this.db.from("cash_closings").select(CLOSING_COLUMNS).eq("date", date).limit(1),
      "приключването на деня",
    );
    return rows[0] ?? null;
  }

  async recentClosings(limit: number): Promise<CashClosing[]> {
    return check(
      await this.db.from("cash_closings").select(CLOSING_COLUMNS)
        .order("date", { ascending: false }).limit(limit),
      "приключените дни",
    );
  }

  async searchProducts(query: string, category: string | undefined, limit: number): Promise<Product[]> {
    let q = this.db.from("products").select("name, category, unit, price, stock");
    if (query) q = q.ilike("name", likePattern(query));
    if (category) q = q.ilike("category", likePattern(category));
    return check(await q.order("name", { ascending: true }).limit(limit), "продуктите");
  }

  async listDocuments(f: DocumentFilter): Promise<DocumentSummary[]> {
    let q = this.db.from("documents").select(SUMMARY_COLUMNS);
    if (f.docType) q = q.eq("doc_type", f.docType);
    if (f.from) q = q.gte("date", f.from);
    if (f.to) q = q.lte("date", f.to);
    if (f.unpaidOnly) q = q.eq("paid", false);
    if (f.customer) q = q.ilike("customer_name", likePattern(f.customer));
    return check(
      await q.order("date", { ascending: false }).order("number", { ascending: false }).limit(f.limit),
      "документите",
    );
  }

  async getDocument(docType: DocType, number: number): Promise<DocumentDetail | null> {
    const rows = check(
      await this.db.from("documents").select(DETAIL_COLUMNS)
        .eq("doc_type", docType).eq("number", number).limit(1),
      "документа",
    );
    return rows[0] ?? null;
  }

  async searchCustomers(query: string, limit: number): Promise<Customer[]> {
    let q = this.db.from("customers").select("name, eik, vat_number, address, phone, email");
    if (query) q = q.ilike("name", likePattern(query));
    return check(await q.order("name", { ascending: true }).limit(limit), "клиентите");
  }
}
