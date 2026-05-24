/**
 * Cloudflare Worker — Gemini API VN block proxy
 *
 * Google's `generativelanguage.googleapis.com` blocks Vietnam IPs with
 * "User location is not supported for the API use" (HTTP 400). This
 * Worker re-issues the request from Cloudflare's edge (US/SG/etc.),
 * bypassing the geo restriction.
 *
 * Deploy:
 *   1. wrangler login
 *   2. wrangler deploy
 *   (or paste this file into a Worker via dash.cloudflare.com → Workers)
 *
 * Use from chatgpt2api by setting providers.gemini_free.base_url to:
 *   https://<your-worker-name>.<your-subdomain>.workers.dev
 *
 * Optional auth: set the env var PROXY_TOKEN in Cloudflare. If set,
 * requests must include header `X-Proxy-Token: <value>` or query
 * param `proxy_token=<value>`. Without it, the Worker is open and any
 * caller can exhaust your free quota (100k req/day).
 */

const UPSTREAM = "https://generativelanguage.googleapis.com";
const ALLOWED_METHODS = new Set(["GET", "POST", "OPTIONS"]);

/**
 * @param {Request} request
 * @param {{PROXY_TOKEN?: string}} env
 */
async function handle(request, env) {
  if (request.method === "OPTIONS") {
    return cors(new Response(null, { status: 204 }));
  }
  if (!ALLOWED_METHODS.has(request.method)) {
    return cors(new Response("Method Not Allowed", { status: 405 }));
  }

  const url = new URL(request.url);

  // Health check
  if (url.pathname === "/" || url.pathname === "/health") {
    return cors(json({ ok: true, target: UPSTREAM, ts: Date.now() }));
  }

  // Optional shared-secret auth
  if (env.PROXY_TOKEN) {
    const provided =
      request.headers.get("X-Proxy-Token") ||
      url.searchParams.get("proxy_token") ||
      "";
    if (provided !== env.PROXY_TOKEN) {
      return cors(new Response("Forbidden", { status: 403 }));
    }
    url.searchParams.delete("proxy_token");
  }

  // Build upstream URL — keep path + query identical, just swap host
  const upstreamUrl = new URL(UPSTREAM + url.pathname + url.search);

  // Clone headers but drop hop-by-hop and Cloudflare-specific ones
  const fwdHeaders = new Headers();
  for (const [k, v] of request.headers.entries()) {
    const lk = k.toLowerCase();
    if (
      lk === "host" ||
      lk === "cf-connecting-ip" ||
      lk === "cf-ipcountry" ||
      lk === "cf-ray" ||
      lk === "cf-visitor" ||
      lk.startsWith("x-forwarded") ||
      lk === "x-real-ip" ||
      lk === "x-proxy-token"
    ) {
      continue;
    }
    fwdHeaders.set(k, v);
  }
  // Force a clean UA so Google sees a normal client, not a Worker
  if (!fwdHeaders.has("user-agent")) {
    fwdHeaders.set("user-agent", "google-genai-sdk/0.1 gl-node/22.0.0");
  }

  let body = null;
  if (request.method === "POST") {
    body = await request.arrayBuffer();
  }

  const upstreamResp = await fetch(upstreamUrl.toString(), {
    method: request.method,
    headers: fwdHeaders,
    body,
    redirect: "follow",
  });

  const respHeaders = new Headers();
  for (const [k, v] of upstreamResp.headers.entries()) {
    const lk = k.toLowerCase();
    if (lk === "transfer-encoding" || lk === "connection" || lk === "content-encoding") {
      continue;
    }
    respHeaders.set(k, v);
  }

  return cors(
    new Response(upstreamResp.body, {
      status: upstreamResp.status,
      statusText: upstreamResp.statusText,
      headers: respHeaders,
    }),
  );
}

function cors(resp) {
  resp.headers.set("Access-Control-Allow-Origin", "*");
  resp.headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  resp.headers.set(
    "Access-Control-Allow-Headers",
    "Content-Type, Authorization, X-Goog-Api-Key, X-Proxy-Token",
  );
  resp.headers.set("Access-Control-Max-Age", "86400");
  return resp;
}

function json(obj) {
  return new Response(JSON.stringify(obj), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

export default {
  /**
   * @param {Request} request
   * @param {{PROXY_TOKEN?: string}} env
   */
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (err) {
      return cors(
        new Response(
          JSON.stringify({ error: "proxy_error", message: String(err) }),
          { status: 502, headers: { "Content-Type": "application/json" } },
        ),
      );
    }
  },
};
