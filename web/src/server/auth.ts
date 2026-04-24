import {readRuntimeConfig} from "@/server/config";
import {readBearerToken} from "@/server/http";

export async function isAuthorized(authorization: string | null) {
    const token = readBearerToken(authorization);
    const config = await readRuntimeConfig();
    const configuredAuthKey = String(process.env.CHATGPT2API_AUTH_KEY || config["auth-key"] || "").trim();
    return Boolean(configuredAuthKey) && token === configuredAuthKey;
}
