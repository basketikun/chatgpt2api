import {readFile, writeFile} from "node:fs/promises";
import {existsSync} from "node:fs";
import path from "node:path";

import {trimTrailingSlashes} from "@/server/url";

export type RuntimeConfig = {
    "auth-key": string;
    refresh_account_interval_minute: number;
    proxy: string;
    base_url: string;
    cpa_pools: Array<Record<string, unknown>>;
    sub2api_servers: Array<Record<string, unknown>>;
    [key: string]: unknown;
};

const DEFAULT_CONFIG: RuntimeConfig = {
    "auth-key": "",
    refresh_account_interval_minute: 5,
    proxy: "",
    base_url: "",
    cpa_pools: [],
    sub2api_servers: [],
};

const MIN_REFRESH_INTERVAL_MINUTES = 1;
export const AUTH_KEY_ENV_NAME = "CHATGPT2API_AUTH_KEY";

function resolveConfigPath() {
    const candidates = [
        path.resolve(process.cwd(), "../config.json"),
        path.resolve(process.cwd(), "config.json"),
    ];
    return candidates.find((candidate) => existsSync(candidate)) || candidates[0];
}

const CONFIG_PATH = resolveConfigPath();

function asObject(value: unknown): Record<string, unknown> {
    return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asString(value: unknown, fallback = "") {
    return String(value ?? fallback).trim();
}

function asNumber(value: unknown, fallback: number, options?: {min?: number}) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
        return fallback;
    }
    const normalized = parsed < 0 ? Math.ceil(parsed) : Math.floor(parsed);
    if (typeof options?.min === "number") {
        return Math.max(options.min, normalized);
    }
    return normalized;
}

function asArrayOfObjects(value: unknown) {
    if (!Array.isArray(value)) {
        return [];
    }
    return value.filter((item) => item && typeof item === "object") as Array<Record<string, unknown>>;
}

function isFileNotFoundError(error: unknown) {
    return Boolean(error && typeof error === "object" && "code" in error && error.code === "ENOENT");
}

export function normalizeConfig(raw: unknown): RuntimeConfig {
    const obj = asObject(raw);
    return {
        ...obj,
        "auth-key": asString(obj["auth-key"]),
        refresh_account_interval_minute: asNumber(
            obj.refresh_account_interval_minute,
            DEFAULT_CONFIG.refresh_account_interval_minute,
            {min: MIN_REFRESH_INTERVAL_MINUTES},
        ),
        proxy: asString(obj.proxy),
        base_url: trimTrailingSlashes(asString(obj.base_url)),
        cpa_pools: asArrayOfObjects(obj.cpa_pools),
        sub2api_servers: asArrayOfObjects(obj.sub2api_servers),
    };
}

export async function readRuntimeConfig() {
    try {
        const text = await readFile(CONFIG_PATH, "utf8");
        return normalizeConfig(JSON.parse(text));
    } catch (error) {
        if (!isFileNotFoundError(error)) {
            console.warn("[config] unable to read config, fallback to defaults", {path: CONFIG_PATH, error});
        }
        return {...DEFAULT_CONFIG};
    }
}

export async function writeRuntimeConfig(nextConfig: RuntimeConfig) {
    await writeFile(CONFIG_PATH, `${JSON.stringify(nextConfig, null, 2)}\n`, "utf8");
}

export async function updateRuntimeConfig(patch: Record<string, unknown>) {
    const current = await readRuntimeConfig();
    const nextConfig = normalizeConfig({
        ...current,
        ...asObject(patch),
    });
    if (!nextConfig["auth-key"]) {
        nextConfig["auth-key"] = String(process.env[AUTH_KEY_ENV_NAME] || "").trim() || current["auth-key"];
    }
    await writeRuntimeConfig(nextConfig);
    return nextConfig;
}

export function sanitizeRuntimeConfigForResponse(config: RuntimeConfig): RuntimeConfig {
    return {
        ...config,
        "auth-key": "",
    };
}

export async function readVersion() {
    const candidates = [
        path.resolve(process.cwd(), "../VERSION"),
        path.resolve(process.cwd(), "VERSION"),
    ];
    for (const candidate of candidates) {
        try {
            const version = (await readFile(candidate, "utf8")).trim();
            if (version) {
                return version;
            }
        } catch (error) {
            if (!isFileNotFoundError(error)) {
                console.warn("[config] unable to read version file", {path: candidate, error});
            }
        }
    }
    return "0.0.0";
}
