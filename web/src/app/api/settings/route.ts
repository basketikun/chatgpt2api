import {NextRequest, NextResponse} from "next/server";

import {isAuthorized} from "@/server/auth";
import {readRuntimeConfig, sanitizeRuntimeConfigForResponse, updateRuntimeConfig} from "@/server/config";
import {errorResponse} from "@/server/http";

export async function GET(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    return NextResponse.json({config: sanitizeRuntimeConfigForResponse(await readRuntimeConfig())});
}

export async function POST(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    let body: Record<string, unknown>;
    try {
        body = (await request.json()) as Record<string, unknown>;
    } catch {
        return errorResponse(400, "invalid json body");
    }
    const config = await updateRuntimeConfig(body);
    return NextResponse.json({config: sanitizeRuntimeConfigForResponse(config)});
}
