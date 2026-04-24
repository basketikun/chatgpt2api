import {NextRequest} from "next/server";

import {proxyToLegacy} from "@/server/legacy-proxy";

export async function POST(request: NextRequest) {
    return proxyToLegacy(request, "/api/proxy/test");
}
