// Entry point of the "shop-mcp" Supabase Edge Function: reads settings from
// the environment and wires the real token check and data access into app.ts.
//
// Deploy with JWT verification off at the gateway (--no-verify-jwt), because
// the sign-in discovery requests arrive without a token by design. This file
// checks every token itself before any data is touched.

import { createClient } from "@supabase/supabase-js";
import { createHandler } from "./app.ts";
import { SupabaseShopData } from "./data.ts";

// Provided by Supabase in every Edge Function.
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY")!;

const list = (name: string) =>
  (Deno.env.get(name) ?? "").split(",").map((s) => s.trim()).filter(Boolean);

// Locally SUPABASE_URL is the Docker-internal address, so the public URLs can
// be overridden. Deployed, the defaults are right.
const publicBaseUrl = Deno.env.get("SHOP_MCP_PUBLIC_URL") ?? `${SUPABASE_URL}/functions/v1/shop-mcp`;
const authIssuer = Deno.env.get("SHOP_MCP_AUTH_ISSUER") ?? `${SUPABASE_URL}/auth/v1`;

const authClient = createClient(SUPABASE_URL, ANON_KEY, {
  auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
});

const handler = createHandler({
  config: {
    publicBaseUrl,
    authIssuer,
    allowedClientIds: list("SHOP_MCP_ALLOWED_CLIENTS"),
    allowSessionTokens: Deno.env.get("SHOP_MCP_ALLOW_SESSION_TOKENS") === "true",
    allowedOrigins: list("SHOP_MCP_ALLOWED_ORIGINS"),
  },

  async verifyToken(token) {
    // getClaims checks the signature and expiry (locally against the
    // project's public keys, or by asking Supabase Auth for older HS256
    // projects, which also catches a signed-out session).
    const { data, error } = await authClient.auth.getClaims(token);
    if (error || !data?.claims) return null;
    const c = data.claims as Record<string, unknown>;
    if (c.role !== "authenticated" || c.aud !== "authenticated") return null;
    if (c.is_anonymous === true) return null;
    if (typeof c.sub !== "string" || !c.sub) return null;
    return {
      userId: c.sub,
      clientId: typeof c.client_id === "string" && c.client_id ? c.client_id : null,
      raw: c,
    };
  },

  dataFor: (token) => new SupabaseShopData(SUPABASE_URL, ANON_KEY, token),
});

Deno.serve(handler);
