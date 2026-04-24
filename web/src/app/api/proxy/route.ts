import {NextRequest, NextResponse} from "next/server";

import {isAuthorized} from "@/server/auth";
import {readRuntimeConfig, updateRuntimeConfig} from "@/server/config";
import {errorResponse} from "@/server/http";

function toProxyResponse(config: {proxy?: unknown}) {
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
    return NextResponse.json({proxy: toProxyResponse(await readRuntimeConfig())});
}

export async function POST(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    let proxyBody: {enabled?: unknown; url?: unknown};
    try {
        proxyBody = (await request.json()) as {enabled?: unknown; url?: unknown};
    } catch {
        return errorResponse(400, "invalid json body");
    }
    const enabled = Boolean(proxyBody.enabled);
    const url = String(proxyBody.url || "").trim();
    if (enabled && !url) {
        return errorResponse(400, "proxy url is required when enabled");
    }
    const config = await updateRuntimeConfig({proxy: enabled ? url : ""});
    return NextResponse.json({proxy: toProxyResponse(config)});
}
