export function trimTrailingSlashes(value: string) {
    return value.replace(/\/+$/, "");
}
