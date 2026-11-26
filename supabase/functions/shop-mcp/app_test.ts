// Tests for the MCP server without a database: the data layer is replaced by
// an in-memory fake, and token checking by a stub. Run with:
//   cd supabase/functions/shop-mcp && deno task test

import { assert, assertEquals, assertMatch } from "@std/assert";
import { type AppConfig, createHandler } from "./app.ts";
import { likePattern, type ShopData } from "./data.ts";
import { shopToday } from "./tools.ts";

const BASE = "https://ref.supabase.co/functions/v1/shop-mcp";
const ISSUER = "https://ref.supabase.co/auth/v1";

const config: AppConfig = {
  publicBaseUrl: BASE,
  authIssuer: ISSUER,
  allowedClientIds: [],
  allowSessionTokens: false,
  allowedOrigins: [],
};

const fake: ShopData = {
  shopInfo: () => Promise.resolve({ company_name: "Свежо и Вкусно" }),
  tillDocuments: (date) =>
    Promise.resolve(date === "2026-11-25"
      ? [
        { doc_type: "invoice", number: 101, date, customer_name: "Иван", total: 120.5, paid: true, payment_method: "cash" },
        { doc_type: "invoice", number: 102, date, customer_name: "Мария", total: 80, paid: true, payment_method: "card" },
        { doc_type: "credit", number: 5, date, customer_name: "Иван", total: -20.5, paid: true, payment_method: "cash" },
      ]
      : []),
  cashEntries: (date) =>
    Promise.resolve(date === "2026-11-25" ? [{ date, amount: 15, payment_method: "cash", note: "" }] : []),
  closing: (date) =>
    Promise.resolve(date === "2026-11-25"
      ? {
        date, counted_cash: 110, note: "", closed_at: "2026-11-25T18:00:00Z",
        total_cash: 115, total_card: 80, total_bank: 0, total: 195, invoice_count: 2, entry_count: 1, auto_closed: false,
      }
      : null),
  recentClosings: (limit) =>
    Promise.resolve([
      {
        date: "2026-11-25", counted_cash: 110, note: "", closed_at: "", total_cash: 115, total_card: 80,
        total_bank: 0, total: 195, invoice_count: 2, entry_count: 1, auto_closed: false,
      },
      {
        date: "2026-11-24", counted_cash: 0, note: "", closed_at: "", total_cash: 10, total_card: 0,
        total_bank: 0, total: 10, invoice_count: 1, entry_count: 0, auto_closed: true,
      },
    ].slice(0, limit)),
  searchProducts: (q) =>
    Promise.resolve([{ name: "Домати", category: "Зеленчуци", unit: "кг", price: 3.2, stock: 12 }]
      .filter((p) => p.name.toLowerCase().includes(q.toLowerCase()))),
  listDocuments: (f) =>
    Promise.resolve([
      { doc_type: "invoice" as const, number: 102, date: "2026-11-25", customer_name: "Мария", total: 80, paid: false, payment_method: "bank" as const },
    ].slice(0, f.limit)),
  getDocument: (t, n) =>
    Promise.resolve(t === "invoice" && n === 102
      ? {
        doc_type: "invoice", number: 102, date: "2026-11-25", customer_name: "Мария", total: 96, paid: false,
        payment_method: "bank", items: [{ name: "Домати", unit: "кг", qty: 25, price: 3.2 }, { name: "" }],
        vat_rate: 20, subtotal: 80, vat_amount: 16, valid_until: null, payment_note: null, related_invoice_number: null,
      }
      : null),
  searchCustomers: () => Promise.resolve([]),
};

const tokens: Record<string, { userId: string; clientId: string | null }> = {
  "oauth.token.ok": { userId: "u1", clientId: "claude-client" },
  "session.token.ok": { userId: "u1", clientId: null },
};

function handler(overrides: Partial<AppConfig> = {}) {
  return createHandler({
    config: { ...config, ...overrides },
    verifyToken: (t) => Promise.resolve(tokens[t] ? { ...tokens[t], raw: {} } : null),
    dataFor: () => fake,
  });
}

/** The transport may answer as JSON or as one SSE event; read either. */
async function readRpc(res: Response) {
  const text = await res.text();
  if (text.trimStart().startsWith("{")) return JSON.parse(text);
  const line = text.split("\n").find((l) => l.startsWith("data:"));
  assert(line, `no data line in: ${text}`);
  return JSON.parse(line.slice(5));
}

let rpcId = 0;
function rpc(method: string, params: unknown, token = "oauth.token.ok", headers: Record<string, string> = {}) {
  return new Request(`http://localhost/shop-mcp/mcp`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      "mcp-protocol-version": "2025-06-18",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: ++rpcId, method, params }),
  });
}

/** A refused input may come back as a JSON-RPC error or as a tool error; both count. */
async function callToolRejected(name: string, args: unknown) {
  const res = await handler()(rpc("tools/call", { name, arguments: args }));
  const body = await readRpc(res);
  assert(body.error || body.result?.isError, JSON.stringify(body));
}

async function callTool(name: string, args: unknown) {
  const res = await handler()(rpc("tools/call", { name, arguments: args }));
  assertEquals(res.status, 200);
  const body = await readRpc(res);
  return body.result as { content: { text: string }[]; structuredContent?: Record<string, unknown>; isError?: boolean };
}

Deno.test("metadata names Supabase Auth as the authorization server", async () => {
  for (const path of ["/.well-known/oauth-protected-resource", "/oauth-protected-resource"]) {
    const res = await handler()(new Request(`http://localhost/shop-mcp${path}`));
    assertEquals(res.status, 200);
    const body = await res.json();
    assertEquals(body.resource, `${BASE}/mcp`);
    assertEquals(body.authorization_servers, [ISSUER]);
  }
});

Deno.test("no token → 401 with a pointer to the metadata", async () => {
  const res = await handler()(rpc("tools/list", {}, ""));
  assertEquals(res.status, 401);
  assertMatch(res.headers.get("www-authenticate") ?? "", /resource_metadata="https:\/\/ref\.supabase\.co\/functions\/v1\/shop-mcp\/\.well-known\/oauth-protected-resource"/);
  await res.body?.cancel();
});

Deno.test("bad token → 401", async () => {
  const res = await handler()(rpc("tools/list", {}, "forged.token.x"));
  assertEquals(res.status, 401);
  await res.body?.cancel();
});

Deno.test("plain web-app session token is refused unless testing mode is on", async () => {
  const refused = await handler()(rpc("tools/list", {}, "session.token.ok"));
  assertEquals(refused.status, 401);
  await refused.body?.cancel();
  const allowed = await handler({ allowSessionTokens: true })(rpc("tools/list", {}, "session.token.ok"));
  assertEquals(allowed.status, 200);
  await allowed.body?.cancel();
});

Deno.test("client allow-list blocks other apps", async () => {
  const res = await handler({ allowedClientIds: ["someone-else"] })(rpc("tools/list", {}));
  assertEquals(res.status, 403);
  await res.body?.cancel();
});

Deno.test("browser requests from other sites are refused", async () => {
  const res = await handler()(rpc("tools/list", {}, "oauth.token.ok", { origin: "https://evil.example" }));
  assertEquals(res.status, 403);
  await res.body?.cancel();
});

Deno.test("oversized body is refused", async () => {
  const req = new Request("http://localhost/shop-mcp/mcp", {
    method: "POST",
    headers: { authorization: "Bearer oauth.token.ok", "content-type": "application/json" },
    body: "x".repeat(70 * 1024),
  });
  const res = await handler()(req);
  assertEquals(res.status, 413);
  await res.body?.cancel();
});

Deno.test("unknown paths → 404", async () => {
  const res = await handler()(new Request("http://localhost/shop-mcp/admin"));
  assertEquals(res.status, 404);
  await res.body?.cancel();
});

Deno.test("tools/list: six tools, all read-only", async () => {
  const res = await handler()(rpc("tools/list", {}));
  const body = await readRpc(res);
  const tools = body.result.tools as { name: string; annotations?: { readOnlyHint?: boolean } }[];
  assertEquals(tools.map((t) => t.name).sort(), [
    "shop_closed_days", "shop_day_summary", "shop_find_customers",
    "shop_find_products", "shop_get_document", "shop_list_documents",
  ]);
  for (const t of tools) assertEquals(t.annotations?.readOnlyHint, true, t.name);
});

Deno.test("day summary adds invoices, credit notes and till entries by payment method", async () => {
  const r = await callTool("shop_day_summary", { date: "2026-11-25" });
  assert(!r.isError);
  assertEquals(r.structuredContent?.totals, { cash: 115, card: 80, bank: 0, total: 195 });
  assertEquals(r.structuredContent?.invoiceCount, 2);
  assertMatch(r.content[0].text, /разлика -5\.00 €/);
});

Deno.test("day summary without a date uses the shop's today", async () => {
  const r = await callTool("shop_day_summary", {});
  assertEquals(r.structuredContent?.date, shopToday());
  assertMatch(r.content[0].text, /не е приключен/);
});

Deno.test("invalid date is rejected before touching data", async () => {
  await callToolRejected("shop_day_summary", { date: "25.11.2026" });
  await callToolRejected("shop_day_summary", { date: "2026-13-45" });
});

Deno.test("limits are enforced", async () => {
  await callToolRejected("shop_list_documents", { limit: 500 });
  await callToolRejected("shop_find_products", { query: "x".repeat(500) });
});

Deno.test("closed days list marks auto-closed days", async () => {
  const r = await callTool("shop_closed_days", { limit: 5 });
  assertMatch(r.content[0].text, /2026-11-24: общо 10\.00 € \(автоматично/);
});

Deno.test("get document shows lines and skips empty rows", async () => {
  const r = await callTool("shop_get_document", { type: "invoice", number: 102 });
  assertMatch(r.content[0].text, /Домати: 25 кг × 3\.20 € = 80\.00 €/);
  assertMatch(r.content[0].text, /НЕПЛАТЕНА/);
  const missing = await callTool("shop_get_document", { number: 999 });
  assert(missing.isError);
});

Deno.test("product search", async () => {
  const r = await callTool("shop_find_products", { query: "дом" });
  assertMatch(r.content[0].text, /Домати — 3\.20 € \/ кг, наличност 12/);
});

Deno.test("shop today follows Sofia time, not UTC", () => {
  // 22:30 UTC on 25 Nov is already 00:30 on 26 Nov in Sofia (UTC+2).
  assertEquals(shopToday(new Date("2026-11-25T22:30:00Z")), "2026-11-26");
  assertEquals(shopToday(new Date("2026-07-25T20:30:00Z")), "2026-07-25");
});

Deno.test("search text cannot inject wildcards", () => {
  assertEquals(likePattern("50%_off*"), "%50\\%\\_off%");
});
