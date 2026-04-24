import {NextRequest} from "next/server";

import {proxyToLegacy} from "@/server/legacy-proxy";

function pathnameFrom(params: Promise<{path: string[]}>) {
    return params.then((value) => `/v1/${(value.path || []).join("/")}`);
}

export async function GET(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
    return proxyToLegacy(request, await pathnameFrom(context.params));
}

export async function POST(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
    return proxyToLegacy(request, await pathnameFrom(context.params));
}

export async function DELETE(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
    return proxyToLegacy(request, await pathnameFrom(context.params));
}

export async function PUT(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
    return proxyToLegacy(request, await pathnameFrom(context.params));
}

export async function PATCH(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
    return proxyToLegacy(request, await pathnameFrom(context.params));
}
