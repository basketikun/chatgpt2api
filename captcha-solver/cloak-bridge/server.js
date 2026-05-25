/**
 * HTTP bridge wrapping cloakbrowser for the Python captcha-solver.
 *
 * Why a separate process instead of calling Node per-request:
 *  - Node startup + cloakbrowser warm-up adds ~2-3 s per call.
 *  - Persistent browser contexts (cookies, localStorage) need a long-lived
 *    runtime that survives between Python HTTP calls.
 *  - We can reuse the same stealth context across the chatgpt login,
 *    turnstile solve, and follow-up navigation steps without re-launching.
 *
 * Wire-format: simple JSON HTTP. One persistent context per `profile`
 * string so the caller can keep a logged-in session alive across
 * navigations.
 */

import http from "node:http";

const PORT = parseInt(process.env.CLOAK_BRIDGE_PORT || "8011", 10);
const HEADLESS = process.env.CLOAK_HEADLESS !== "0";

let cloak = null;
const contexts = new Map(); // profile -> { browser, pages: Map<pageId, page> }

async function getCloak() {
  if (cloak === null) {
    cloak = await import("cloakbrowser");
  }
  return cloak;
}

async function getContext(profile) {
  let entry = contexts.get(profile);
  if (entry && entry.browser && entry.browser.isConnected()) {
    return entry;
  }
  const c = await getCloak();
  const browser = await c.launch({
    headless: HEADLESS,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });
  entry = { browser, pages: new Map() };
  contexts.set(profile, entry);
  return entry;
}

async function getPage(profile, pageId = "default") {
  const ctx = await getContext(profile);
  let page = ctx.pages.get(pageId);
  if (!page || page.isClosed()) {
    page = await ctx.browser.newPage();
    ctx.pages.set(pageId, page);
  }
  return page;
}

async function closeProfile(profile) {
  const entry = contexts.get(profile);
  if (!entry) return false;
  contexts.delete(profile);
  try {
    await entry.browser.close();
  } catch {
    /* best effort */
  }
  return true;
}

function send(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(payload),
  });
  res.end(payload);
}

async function readJSON(req) {
  return new Promise((resolve, reject) => {
    let buf = "";
    req.on("data", (chunk) => {
      buf += chunk;
      // Reject pathologically large bodies — image bytes flow via base64 in
      // discrete fields so 10 MB is plenty for any legitimate captcha call.
      if (buf.length > 10 * 1024 * 1024) {
        reject(new Error("body too large"));
      }
    });
    req.on("end", () => {
      if (!buf) return resolve({});
      try {
        resolve(JSON.parse(buf));
      } catch (e) {
        reject(e);
      }
    });
    req.on("error", reject);
  });
}

const routes = {
  async "/health"(_req, _body) {
    return { ok: true, contexts: contexts.size };
  },

  async "/launch"(_req, body) {
    const profile = String(body.profile || "default");
    await getContext(profile);
    return { ok: true, profile };
  },

  async "/navigate"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    const timeout = body.timeout || 30000;
    const waitUntil = body.waitUntil || "domcontentloaded";
    await page.goto(String(body.url), { timeout, waitUntil });
    return { ok: true, url: page.url() };
  },

  async "/get_html"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    const html = await page.content();
    return { ok: true, html };
  },

  async "/get_text"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    if (body.selector) {
      const el = await page.$(String(body.selector));
      if (!el) return { ok: false, error: "selector not found" };
      const text = await el.innerText();
      return { ok: true, text };
    }
    const text = await page.evaluate(() => document.body.innerText || "");
    return { ok: true, text };
  },

  async "/click"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    await page.click(String(body.selector), { timeout: body.timeout || 10000 });
    return { ok: true };
  },

  async "/type"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    await page.fill(String(body.selector), String(body.text || ""), {
      timeout: body.timeout || 10000,
    });
    return { ok: true };
  },

  async "/evaluate"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    const result = await page.evaluate(String(body.script));
    return { ok: true, result };
  },

  async "/wait_for_selector"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    await page.waitForSelector(String(body.selector), {
      timeout: body.timeout || 30000,
      state: body.state || "visible",
    });
    return { ok: true };
  },

  async "/screenshot"(_req, body) {
    const page = await getPage(body.profile || "default", body.pageId);
    const buf = await page.screenshot({
      fullPage: body.fullPage !== false,
      type: "png",
    });
    return { ok: true, png_b64: buf.toString("base64") };
  },

  async "/cookies"(_req, body) {
    const ctx = await getContext(body.profile || "default");
    const cookies = await ctx.browser.cookies();
    return { ok: true, cookies };
  },

  async "/close"(_req, body) {
    const ok = await closeProfile(String(body.profile || "default"));
    return { ok };
  },
};

const server = http.createServer(async (req, res) => {
  if (req.method !== "POST" && req.url !== "/health") {
    send(res, 405, { ok: false, error: "method not allowed" });
    return;
  }
  const handler = routes[req.url];
  if (!handler) {
    send(res, 404, { ok: false, error: `unknown route ${req.url}` });
    return;
  }
  try {
    const body = req.method === "POST" ? await readJSON(req) : {};
    const result = await handler(req, body);
    send(res, 200, result);
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    send(res, 500, { ok: false, error: message });
  }
});

server.listen(PORT, () => {
  console.log(
    JSON.stringify({
      event: "cloak_bridge_listening",
      port: PORT,
      headless: HEADLESS,
    })
  );
});

const shutdown = async () => {
  for (const profile of Array.from(contexts.keys())) {
    await closeProfile(profile);
  }
  process.exit(0);
};
process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);
