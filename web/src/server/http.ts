import {NextResponse} from "next/server";

export function readBearerToken(authorization: string | null) {
    const [scheme, value] = String(authorization || "").split(" ", 2);
    if (scheme?.toLowerCase() !== "bearer") {
        return "";
    }
    return String(value || "").trim();
}

export function errorResponse(status: number, message: string) {
    return NextResponse.json({detail: {error: message}, error: message}, {status});
}
