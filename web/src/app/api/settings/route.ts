import {NextRequest, NextResponse} from "next/server";

import {isAuthorized} from "@/server/auth";
import {readRuntimeConfig, updateRuntimeConfig} from "@/server/config";
import {errorResponse} from "@/server/http";

export async function GET(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    return NextResponse.json({config: await readRuntimeConfig()});
}

export async function POST(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const config = await updateRuntimeConfig(body);
    return NextResponse.json({config});
}
