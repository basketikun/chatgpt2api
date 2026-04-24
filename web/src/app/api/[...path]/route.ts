import {NextRequest} from "next/server";

import {proxyToLegacy} from "@/server/legacy-proxy";

function pathnameFrom(params: Promise<{path: string[]}>) {
    return params.then((value) => `/api/${(value.path || []).join("/")}`);
}

async function handle(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
    return proxyToLegacy(request, await pathnameFrom(context.params));
}

export const GET = handle;
export const POST = handle;
export const DELETE = handle;
export const PUT = handle;
export const PATCH = handle;
