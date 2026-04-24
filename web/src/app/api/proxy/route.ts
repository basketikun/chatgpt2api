import {NextRequest, NextResponse} from "next/server";

import {isAuthorized} from "@/server/auth";
import {readRuntimeConfig, updateRuntimeConfig} from "@/server/config";
import {errorResponse} from "@/server/http";

function parseProxyConfig(config: {proxy?: unknown}) {
    const proxyUrl = String(config.proxy || "").trim();
    return {
        enabled: Boolean(proxyUrl),
        url: proxyUrl,
    };
}

export async function GET(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    return NextResponse.json({proxy: parseProxyConfig(await readRuntimeConfig())});
}

export async function POST(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    const body = (await request.json().catch(() => ({}))) as {enabled?: unknown; url?: unknown};
    const enabled = Boolean(body.enabled);
    const url = String(body.url || "").trim();
    const config = await updateRuntimeConfig({proxy: enabled ? url : ""});
    return NextResponse.json({proxy: parseProxyConfig(config)});
}
