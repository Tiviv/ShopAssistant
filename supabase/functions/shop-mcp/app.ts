// The HTTP side of the MCP server: who may call it, and where.
//
// Routes (all under the function's own URL, …/functions/v1/shop-mcp):
//   POST /mcp                                   the MCP endpoint itself
//   GET  /.well-known/oauth-protected-resource  where to sign in (RFC 9728)
//   GET  /oauth-protected-resource              same document, second path
//
// The sign-in flow, in short. An AI app (Claude, ChatGPT…) calls /mcp with no
// token and gets 401 plus a WWW-Authenticate header pointing at the metadata
// document. That names Supabase Auth as the authorization server, so the app
// sends the user to Supabase's OAuth 2.1 server, which shows our consent page
// (oauth/consent/index.html). After the user signs in with their normal shop
// account and approves, the app gets a Supabase access token for that user and
// sends it on every call. We verify it and run every query *as that user*, so
// Row Level Security keeps them inside their own shop. The service_role key is
// never used.

import { StreamableHttpTransport } from "mcp-lite";
import type { ShopData } from "./data.ts";
import { buildServer } from "./tools.ts";

export interface VerifiedUser {
  userId: string;
  clientId: string | null;
}

export interface AppConfig {
  /** Public URL of this function, e.g. https://<ref>.supabase.co/functions/v1/shop-mcp */
  publicBaseUrl: string;
  /** Issuer of the access tokens, e.g. https://<ref>.supabase.co/auth/v1 */
  authIssuer: string;
  /**
   * OAuth client ids allowed to call. Empty = any client the user approved on
   * the consent page. Once Claude has registered, pin its id here.
   */
  allowedClientIds: string[];
  /**
   * Accept ordinary web-app session tokens (no client_id claim). Only for
   * local testing with a token pasted by hand; keep false when deployed.
   */
  allowSessionTokens: boolean;
  /** Browser origins allowed to call. Requests with no Origin (servers) always pass. */
  allowedOrigins: string[];
}

export interface AppDeps {
  config: AppConfig;
  /** Checks a bearer token; returns null when it is not valid. */
  verifyToken(token: string): Promise<(VerifiedUser & { raw: Record<string, unknown> }) | null>;
  /** Data access bound to the caller's own token. */
  dataFor(token: string): ShopData;
}

const MAX_BODY_BYTES = 64 * 1024;
const FUNCTION_SLUG = "/shop-mcp";

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });
}

/** The part of the path after the function name, so the code works locally and deployed. */
function routeOf(url: URL): string {
  const p = url.pathname;
  const i = p.indexOf(FUNCTION_SLUG);
  const rest = i >= 0 ? p.slice(i + FUNCTION_SLUG.length) : p;
  return rest.replace(/\/+$/, "") || "/";
}

export function createHandler(deps: AppDeps): (req: Request) => Promise<Response> {
  const { config } = deps;
  const base = config.publicBaseUrl.replace(/\/+$/, "");
  const resource = `${base}/mcp`;
  const metadataUrl = `${base}/.well-known/oauth-protected-resource`;

  const metadata = {
    resource,
    authorization_servers: [config.authIssuer],
    bearer_methods_supported: ["header"],
    scopes_supported: ["openid", "email", "profile"],
    resource_name: "Магазинер",
  };

  const unauthorized = (error: "invalid_request" | "invalid_token", description: string) =>
    json(401, { error, error_description: description }, {
      "www-authenticate":
        `Bearer resource_metadata="${metadataUrl}", error="${error}", error_description="${description}"`,
    });

  return async (req: Request): Promise<Response> => {
    const url = new URL(req.url);
    const route = routeOf(url);

    if (route === "/.well-known/oauth-protected-resource" || route === "/oauth-protected-resource") {
      // Public, non-secret, and fetched by browser-based clients such as MCP
      // Inspector, so any site may read it. The MCP endpoint itself sends no
      // CORS headers.
      const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "mcp-protocol-version" };
      if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
      if (req.method !== "GET") return json(405, { error: "method_not_allowed" });
      return json(200, metadata, cors);
    }

    if (route !== "/mcp") return json(404, { error: "not_found" });

    // A browser page on another site has no business here. Servers (Claude,
    // ChatGPT) send no Origin and are not affected.
    const origin = req.headers.get("origin");
    if (origin && !config.allowedOrigins.includes(origin)) {
      return json(403, { error: "origin_not_allowed" });
    }

    const auth = req.headers.get("authorization") ?? "";
    const match = /^Bearer\s+([A-Za-z0-9\-_.]+)$/i.exec(auth);
    if (!match) return unauthorized("invalid_request", "Sign-in required");
    const token = match[1];

    const user = await deps.verifyToken(token);
    if (!user) return unauthorized("invalid_token", "Token is invalid or expired");

    // Only tokens issued through the OAuth consent flow carry client_id, so by
    // default a stolen web-app session token cannot be replayed here.
    if (!user.clientId && !config.allowSessionTokens) {
      return unauthorized("invalid_token", "Token was not issued for this connector");
    }
    if (user.clientId && config.allowedClientIds.length > 0 && !config.allowedClientIds.includes(user.clientId)) {
      return json(403, { error: "insufficient_scope", error_description: "This app is not allowed" });
    }

    // Read the body ourselves so a huge or chunked upload is cut off here.
    let mcpRequest = req;
    if (req.method === "POST") {
      const length = Number(req.headers.get("content-length") ?? "0");
      if (length > MAX_BODY_BYTES) return json(413, { error: "payload_too_large" });
      const body = await req.text();
      if (new TextEncoder().encode(body).length > MAX_BODY_BYTES) return json(413, { error: "payload_too_large" });
      mcpRequest = new Request(req.url, { method: "POST", headers: req.headers, body });
    }

    // Stateless: a fresh server per request, bound to this caller's data.
    const server = buildServer(deps.dataFor(token), (tool) => {
      // Audit trail in the function's logs: who used which tool, never the data.
      console.log(JSON.stringify({ event: "tool_call", tool, user: user.userId, client: user.clientId }));
    });
    const transport = new StreamableHttpTransport();
    return await transport.bind(server)(mcpRequest);
  };
}
