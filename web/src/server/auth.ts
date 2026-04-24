import {timingSafeEqual} from "node:crypto";

import {AUTH_KEY_ENV_NAME, readRuntimeConfig} from "@/server/config";
import {readBearerToken} from "@/server/http";

function secureTokenEquals(left: string, right: string) {
    const leftBuffer = Buffer.from(left);
    const rightBuffer = Buffer.from(right);
    if (leftBuffer.length !== rightBuffer.length) {
        return false;
    }
    return timingSafeEqual(leftBuffer, rightBuffer);
}

export async function isAuthorized(authorization: string | null) {
    const token = readBearerToken(authorization);
    const config = await readRuntimeConfig();
    const configuredAuthKey = String(process.env[AUTH_KEY_ENV_NAME] || config["auth-key"] || "").trim();
    return Boolean(configuredAuthKey) && secureTokenEquals(token, configuredAuthKey);
}
