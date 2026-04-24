import {NextRequest, NextResponse} from "next/server";

import {isAuthorized} from "@/server/auth";
import {readRuntimeConfig} from "@/server/config";
import {errorResponse} from "@/server/http";

function isSupportedProxyProtocol(protocol: string) {
    return ["http:", "https:", "socks5:", "socks5h:"].includes(protocol);
}

export async function POST(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }

    const body = (await request.json().catch(() => ({}))) as {url?: unknown};
    const fallback = String((await readRuntimeConfig()).proxy || "").trim();
    const candidate = String(body.url || "").trim() || fallback;
    if (!candidate) {
        return errorResponse(400, "proxy url is required");
    }
    const startedAt = Date.now();
    try {
        const parsed = new URL(candidate);
        if (!isSupportedProxyProtocol(parsed.protocol)) {
            return NextResponse.json({
                result: {
                    ok: false,
                    status: 0,
                    latency_ms: Date.now() - startedAt,
                    error: "unsupported proxy protocol",
                },
            });
        }
        return NextResponse.json({
            result: {
                ok: true,
                status: 200,
                latency_ms: Date.now() - startedAt,
                error: null,
            },
        });
    } catch {
        return NextResponse.json({
            result: {
                ok: false,
                status: 0,
                latency_ms: Date.now() - startedAt,
                error: "invalid proxy url",
            },
        });
    }
}
