// Keep the storage key and locale list in sync with src/i18n/config.ts.
// An inline script cannot import modules, so the values are repeated here.
const localeScript = `
(() => {
  try {
    const supported = ["zh", "en", "vi"];
    const langTags = { zh: "zh-CN" };
    const stored = localStorage.getItem("chatgpt2api-locale");
    const navLangs = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language];
    const candidates = stored ? [stored].concat(navLangs) : navLangs;
    let locale = "zh";
    for (const candidate of candidates) {
      if (typeof candidate !== "string") continue;
      const base = candidate.split("-")[0].toLowerCase();
      if (supported.includes(base)) {
        locale = base;
        break;
      }
    }
    document.documentElement.lang = langTags[locale] || locale;
  } catch {
    document.documentElement.lang = "zh-CN";
  }
})();
`;

export function LocaleScript() {
  return <script dangerouslySetInnerHTML={{ __html: localeScript }} />;
}
