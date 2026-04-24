import {NextRequest, NextResponse} from "next/server";

import {isAuthorized} from "@/server/auth";
import {readVersion} from "@/server/config";
import {errorResponse} from "@/server/http";

export async function POST(request: NextRequest) {
    const ok = await isAuthorized(request.headers.get("authorization"));
    if (!ok) {
        return errorResponse(401, "authorization is invalid");
    }
    return NextResponse.json({
        ok: true,
        version: await readVersion(),
    });
}
