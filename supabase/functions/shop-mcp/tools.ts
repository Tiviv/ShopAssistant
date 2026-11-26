// The tools an AI assistant sees. Version 1 is read-only on purpose: every
// tool is marked readOnlyHint, none of them writes, and none takes a table
// name, column name or SQL from the model. Inputs are checked by zod before a
// handler runs, and every list has a hard upper limit.
//
// Texts are in Bulgarian because the shop works in Bulgarian; the assistant
// answers in whatever language the user writes in.

import { McpServer } from "mcp-lite";
import { z } from "zod";
import { DataError, type DocType, type PayMethod, type ShopData } from "./data.ts";

export const SERVER_NAME = "magaziner";
export const SERVER_VERSION = "0.1.0";

const SHOP_TIMEZONE = "Europe/Sofia";

/** The shop's calendar day, which is not UTC's for part of every evening. */
export function shopToday(now: Date = new Date()): string {
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: SHOP_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

const isoDate = z.string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Датата трябва да е във формат ГГГГ-ММ-ДД")
  .refine((s) => !Number.isNaN(Date.parse(`${s}T00:00:00Z`)), "Невалидна дата");

const docType = z.enum(["invoice", "offer", "credit", "receipt"]);

const DOC_LABEL: Record<DocType, string> = {
  invoice: "Фактура",
  offer: "Оферта",
  credit: "Кредитно известие",
  receipt: "Стокова разписка",
};

const PAY_LABEL: Record<PayMethod, string> = {
  cash: "в брой",
  card: "с карта",
  bank: "по банка",
};

const READ_ONLY = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };

function money(n: number | string | null | undefined): number {
  const v = Number(n ?? 0);
  return Number.isFinite(v) ? Math.round(v * 100) / 100 : 0;
}

function fmt(n: number): string {
  return `${money(n).toFixed(2)} €`;
}

type Result = {
  content: { type: "text"; text: string }[];
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
};

function ok(text: string, data: Record<string, unknown>): Result {
  return { content: [{ type: "text", text }], structuredContent: data };
}

function fail(text: string): Result {
  return { content: [{ type: "text", text }], isError: true };
}

/**
 * Runs a handler and turns any failure into a tool error the model can read,
 * without passing internal error text along.
 */
async function guarded(tool: string, run: () => Promise<Result>): Promise<Result> {
  try {
    return await run();
  } catch (err) {
    if (err instanceof DataError) return fail(err.message);
    console.error(`shop-mcp: ${tool} crashed:`, err);
    return fail("Възникна неочаквана грешка. Опитайте отново.");
  }
}

export function buildServer(data: ShopData, log: (tool: string) => void = () => {}): McpServer {
  const server = new McpServer({
    name: SERVER_NAME,
    version: SERVER_VERSION,
    schemaAdapter: (schema) => z.toJSONSchema(schema as z.ZodType),
  });

  // ---------------------------------------------------------------------
  server.tool("shop_day_summary", {
    title: "Каса за деня",
    description:
      "Касата на магазина за един ден: оборот в брой, с карта и по банка (фактури, кредитни известия и ръчни касови записи), " +
      "дали денят е приключен и с каква отчетена наличност. Без дата показва днешния ден (часова зона Europe/Sofia).",
    annotations: READ_ONLY,
    inputSchema: z.object({
      date: isoDate.optional().describe("Ден във формат ГГГГ-ММ-ДД. Празно = днес."),
    }),
    handler: (args) =>
      guarded("shop_day_summary", async () => {
        log("shop_day_summary");
        const date = args.date ?? shopToday();
        const [docs, entries, closing] = await Promise.all([
          data.tillDocuments(date),
          data.cashEntries(date),
          data.closing(date),
        ]);

        const totals = { cash: 0, card: 0, bank: 0 };
        for (const d of docs) totals[d.payment_method] += money(d.total);
        for (const e of entries) totals[e.payment_method] += money(e.amount);
        const total = money(totals.cash + totals.card + totals.bank);
        const invoiceCount = docs.filter((d) => d.doc_type === "invoice").length;

        const lines = [
          `Каса за ${date}${date === shopToday() ? " (днес)" : ""}`,
          `В брой: ${fmt(totals.cash)} · С карта: ${fmt(totals.card)} · По банка: ${fmt(totals.bank)}`,
          `Общо: ${fmt(total)} — ${invoiceCount} фактури, ${docs.length - invoiceCount} кредитни известия, ${entries.length} касови записа`,
        ];
        if (closing) {
          if (closing.auto_closed) {
            lines.push("Денят е приключен автоматично; касата не е броена.");
          } else {
            const diff = money(closing.counted_cash) - money(closing.total_cash ?? totals.cash);
            lines.push(
              `Денят е приключен. Отчетени в брой: ${fmt(closing.counted_cash)}` +
                (Math.abs(diff) >= 0.005 ? ` (разлика ${diff > 0 ? "+" : ""}${fmt(diff)})` : " (без разлика)"),
            );
          }
        } else {
          lines.push("Денят още не е приключен.");
        }

        return ok(lines.join("\n"), {
          date,
          totals: { cash: money(totals.cash), card: money(totals.card), bank: money(totals.bank), total },
          invoiceCount,
          creditCount: docs.length - invoiceCount,
          entryCount: entries.length,
          closed: closing !== null,
          closing,
          documents: docs,
          entries,
        });
      }),
  });

  // ---------------------------------------------------------------------
  server.tool("shop_closed_days", {
    title: "Приключени дни",
    description: "Последните приключени дни на касата, най-новите първи, с оборота и отчетените пари за всеки.",
    annotations: READ_ONLY,
    inputSchema: z.object({
      limit: z.number().int().min(1).max(31).default(10).describe("Колко дни (1–31). По подразбиране 10."),
    }),
    handler: (args) =>
      guarded("shop_closed_days", async () => {
        log("shop_closed_days");
        const days = await data.recentClosings(args.limit);
        if (days.length === 0) return ok("Няма приключени дни.", { days: [] });
        const text = days.map((d) =>
          `${d.date}: общо ${d.total == null ? "—" : fmt(d.total)}` +
          (d.auto_closed ? " (автоматично, без броене)" : `, отчетени в брой ${fmt(d.counted_cash)}`) +
          (d.note ? ` — ${d.note}` : "")
        ).join("\n");
        return ok(text, { days });
      }),
  });

  // ---------------------------------------------------------------------
  server.tool("shop_find_products", {
    title: "Търсене на продукти",
    description: "Търси продукти по име (и по желание категория) и връща цена, мерна единица и наличност.",
    annotations: READ_ONLY,
    inputSchema: z.object({
      query: z.string().trim().max(80).default("").describe("Част от името на продукта. Празно = всички."),
      category: z.string().trim().max(60).optional().describe("Част от името на категорията."),
      limit: z.number().int().min(1).max(50).default(20),
    }),
    handler: (args) =>
      guarded("shop_find_products", async () => {
        log("shop_find_products");
        const products = await data.searchProducts(args.query, args.category || undefined, args.limit);
        if (products.length === 0) return ok("Няма намерени продукти.", { products: [] });
        const text = products.map((p) =>
          `${p.name} — ${fmt(p.price)}${p.unit ? ` / ${p.unit}` : ""}` +
          (p.stock == null ? "" : `, наличност ${p.stock}`) +
          (p.category ? ` [${p.category}]` : "")
        ).join("\n");
        return ok(text, { products });
      }),
  });

  // ---------------------------------------------------------------------
  server.tool("shop_list_documents", {
    title: "Списък с документи",
    description:
      "Списък с фактури, оферти, кредитни известия или стокови разписки, най-новите първи. " +
      "Може да се филтрира по вид, период, клиент и неплатени.",
    annotations: READ_ONLY,
    inputSchema: z.object({
      type: docType.optional().describe("invoice = фактура, offer = оферта, credit = кредитно известие, receipt = стокова разписка"),
      from: isoDate.optional().describe("От дата (включително), ГГГГ-ММ-ДД"),
      to: isoDate.optional().describe("До дата (включително), ГГГГ-ММ-ДД"),
      customer: z.string().trim().max(80).optional().describe("Част от името на клиента"),
      unpaid_only: z.boolean().default(false).describe("Само неплатените"),
      limit: z.number().int().min(1).max(50).default(20),
    }),
    handler: (args) =>
      guarded("shop_list_documents", async () => {
        log("shop_list_documents");
        if (args.from && args.to && args.from > args.to) {
          return fail("Началната дата е след крайната.");
        }
        const docs = await data.listDocuments({
          docType: args.type,
          from: args.from,
          to: args.to,
          customer: args.customer || undefined,
          unpaidOnly: args.unpaid_only,
          limit: args.limit,
        });
        if (docs.length === 0) return ok("Няма намерени документи.", { documents: [], total: 0 });
        const sum = money(docs.reduce((s, d) => s + money(d.total), 0));
        const text = docs.map((d) =>
          `${DOC_LABEL[d.doc_type]} № ${d.number} от ${d.date} — ${d.customer_name || "без клиент"}, ` +
          `${fmt(d.total)}, ${PAY_LABEL[d.payment_method] ?? d.payment_method}${d.paid ? "" : ", НЕПЛАТЕНА"}`
        ).join("\n") +
          `\nОбщо за показаните ${docs.length}: ${fmt(sum)}` +
          (docs.length === args.limit ? " (може да има още — увеличете limit или стеснете периода)" : "");
        return ok(text, { documents: docs, total: sum, maybeMore: docs.length === args.limit });
      }),
  });

  // ---------------------------------------------------------------------
  server.tool("shop_get_document", {
    title: "Документ по номер",
    description: "Показва един документ (фактура, оферта, кредитно известие или стокова разписка) с редовете му.",
    annotations: READ_ONLY,
    inputSchema: z.object({
      type: docType.default("invoice"),
      number: z.number().int().min(1).max(2_000_000_000),
    }),
    handler: (args) =>
      guarded("shop_get_document", async () => {
        log("shop_get_document");
        const doc = await data.getDocument(args.type, args.number);
        if (!doc) return fail(`Няма ${DOC_LABEL[args.type].toLowerCase()} с № ${args.number}.`);
        const items = (doc.items ?? []).filter((it) => it && it.name);
        const lines = [
          `${DOC_LABEL[doc.doc_type]} № ${doc.number} от ${doc.date}`,
          `Клиент: ${doc.customer_name || "—"}`,
          ...items.map((it) =>
            `• ${it.name}: ${Number(it.qty) || 0} ${it.unit ?? ""} × ${fmt(Number(it.price) || 0)} = ` +
            fmt((Number(it.qty) || 0) * (Number(it.price) || 0))
          ),
          `Сума без ДДС: ${fmt(doc.subtotal)} · ДДС ${money(doc.vat_rate)}%: ${fmt(doc.vat_amount)} · Общо: ${fmt(doc.total)}`,
          `Плащане: ${PAY_LABEL[doc.payment_method] ?? doc.payment_method}, ${doc.paid ? "платена" : "НЕПЛАТЕНА"}`,
        ];
        if (doc.valid_until) lines.push(`Валидна до: ${doc.valid_until}`);
        if (doc.related_invoice_number) lines.push(`Към фактура № ${doc.related_invoice_number}`);
        if (doc.payment_note) lines.push(`Бележка: ${doc.payment_note}`);
        return ok(lines.join("\n"), { document: { ...doc, items } });
      }),
  });

  // ---------------------------------------------------------------------
  server.tool("shop_find_customers", {
    title: "Търсене на клиенти",
    description: "Търси клиенти по име и връща ЕИК, ДДС номер, адрес, телефон и имейл.",
    annotations: READ_ONLY,
    inputSchema: z.object({
      query: z.string().trim().min(1).max(80).describe("Част от името на клиента"),
      limit: z.number().int().min(1).max(20).default(10),
    }),
    handler: (args) =>
      guarded("shop_find_customers", async () => {
        log("shop_find_customers");
        const customers = await data.searchCustomers(args.query, args.limit);
        if (customers.length === 0) return ok("Няма намерени клиенти.", { customers: [] });
        const text = customers.map((c) =>
          [c.name, c.eik && `ЕИК ${c.eik}`, c.vat_number && `ДДС ${c.vat_number}`, c.address, c.phone, c.email]
            .filter(Boolean).join(" · ")
        ).join("\n");
        return ok(text, { customers });
      }),
  });

  return server;
}
