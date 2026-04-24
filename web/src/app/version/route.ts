import {NextResponse} from "next/server";

import {readVersion} from "@/server/config";

export async function GET() {
    return NextResponse.json({version: await readVersion()});
}
