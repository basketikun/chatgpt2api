import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const LOCALES_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "i18n", "locales");
const REFERENCE_LOCALE = "zh";

function flatten(value, prefix = "") {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  );
}

// i18next plural suffixes (foo_one, foo_other, ...) differ per locale by design, so strip them before comparing key sets.
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function keysOf(locale) {
  const map = new Map();
  for (const file of readdirSync(join(LOCALES_DIR, locale)).filter((f) => f.endsWith(".json"))) {
    const parsed = JSON.parse(readFileSync(join(LOCALES_DIR, locale, file), "utf-8"));
    const keys = flatten(parsed).map((key) => key.replace(PLURAL_SUFFIX, ""));
    map.set(file, new Set(keys));
  }
  return map;
}

const locales = readdirSync(LOCALES_DIR, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name);

if (!locales.includes(REFERENCE_LOCALE)) {
  console.error(`missing reference locale "${REFERENCE_LOCALE}"`);
  process.exit(1);
}

const reference = keysOf(REFERENCE_LOCALE);
const problems = [];

for (const locale of locales.filter((l) => l !== REFERENCE_LOCALE)) {
  const actual = keysOf(locale);
  for (const [file, expectedKeys] of reference) {
    const actualKeys = actual.get(file);
    if (!actualKeys) {
      problems.push(`${locale}/${file}: file is missing`);
      continue;
    }
    for (const key of expectedKeys) {
      if (!actualKeys.has(key)) problems.push(`${locale}/${file}: missing key "${key}"`);
    }
    for (const key of actualKeys) {
      if (!expectedKeys.has(key)) problems.push(`${locale}/${file}: unexpected key "${key}"`);
    }
  }
  for (const file of actual.keys()) {
    if (!reference.has(file)) problems.push(`${locale}/${file}: file has no ${REFERENCE_LOCALE} counterpart`);
  }
}

if (problems.length > 0) {
  console.error(`locale check failed with ${problems.length} problem(s):`);
  for (const problem of problems) console.error(`  ${problem}`);
  process.exit(1);
}

console.log(`locale check passed for: ${locales.join(", ")}`);
