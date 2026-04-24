import {errorResponse} from "@/server/http";
import {trimTrailingSlashes} from "@/server/url";

const DEFAULT_LEGACY_API_BASE_URL = "http://127.0.0.1:8000";

const HOP_BY_HOP_HEADERS = new Set([
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
]);

function buildLegacyUrl(pathname: string, search = "") {
    const baseUrl = trimTrailingSlashes(String(process.env.LEGACY_API_BASE_URL || DEFAULT_LEGACY_API_BASE_URL).trim());
    const normalizedPath = pathname.startsWith("/") ? pathname : `/${pathname}`;
    return `${baseUrl}${normalizedPath}${search}`;
}

function copyHeaders(source: Headers) {
    const target = new Headers();
    source.forEach((value, key) => {
        if (HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
            return;
        }
        target.set(key, value);
    });
    return target;
}

async function createProxyResponse(upstream: Response) {
    const headers = copyHeaders(upstream.headers);
    return new Response(upstream.body, {
        status: upstream.status,
        headers,
    });
}

export async function proxyToLegacy(request: Request, pathname: string) {
    try {
        const targetUrl = buildLegacyUrl(pathname, new URL(request.url).search);
        const method = request.method.toUpperCase();
        const headers = copyHeaders(request.headers);
        const init: RequestInit = {
            method,
            headers,
            redirect: "manual",
        };
        if (method !== "GET" && method !== "HEAD") {
            const bodyBuffer = await request.arrayBuffer();
            if (bodyBuffer.byteLength > 0) {
                init.body = bodyBuffer;
            }
        }
        const upstream = await fetch(targetUrl, init);
        return createProxyResponse(upstream);
    } catch (error) {
        const safeError = error instanceof Error ? {name: error.name, message: error.message} : {message: "unknown"};
        console.error("[legacy-proxy] request failed", {pathname, error: safeError});
        return errorResponse(502, "legacy backend unavailable");
    }
}
