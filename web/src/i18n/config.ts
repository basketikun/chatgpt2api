import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import enAccounts from "./locales/en/accounts.json";
import enCommon from "./locales/en/common.json";
import enDebug from "./locales/en/debug.json";
import enImage from "./locales/en/image.json";
import enImageManager from "./locales/en/image-manager.json";
import enLogin from "./locales/en/login.json";
import enLogs from "./locales/en/logs.json";
import enSettings from "./locales/en/settings.json";
import viAccounts from "./locales/vi/accounts.json";
import viCommon from "./locales/vi/common.json";
import viDebug from "./locales/vi/debug.json";
import viImage from "./locales/vi/image.json";
import viImageManager from "./locales/vi/image-manager.json";
import viLogin from "./locales/vi/login.json";
import viLogs from "./locales/vi/logs.json";
import viSettings from "./locales/vi/settings.json";
import zhAccounts from "./locales/zh/accounts.json";
import zhCommon from "./locales/zh/common.json";
import zhDebug from "./locales/zh/debug.json";
import zhImage from "./locales/zh/image.json";
import zhImageManager from "./locales/zh/image-manager.json";
import zhLogin from "./locales/zh/login.json";
import zhLogs from "./locales/zh/logs.json";
import zhSettings from "./locales/zh/settings.json";

export const SUPPORTED_LOCALES = ["zh", "en", "vi"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const FALLBACK_LOCALE: Locale = "zh";

// Mirrors the "chatgpt2api-theme" convention already used by theme-script.tsx.
// locale-script.tsx repeats this literal because an inline script cannot import.
export const LOCALE_STORAGE_KEY = "chatgpt2api-locale";

const resources = {
  zh: { common: zhCommon, logs: zhLogs, login: zhLogin, "image-manager": zhImageManager, debug: zhDebug, image: zhImage, accounts: zhAccounts, settings: zhSettings },
  en: { common: enCommon, logs: enLogs, login: enLogin, "image-manager": enImageManager, debug: enDebug, image: enImage, accounts: enAccounts, settings: enSettings },
  vi: { common: viCommon, logs: viLogs, login: viLogin, "image-manager": viImageManager, debug: viDebug, image: viImage, accounts: viAccounts, settings: viSettings },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    // Pin the initial language to the fallback so the prerendered HTML from
    // `output: 'export'` always matches what React renders on hydration.
    // provider.tsx applies the detected locale after mount instead.
    lng: FALLBACK_LOCALE,
    fallbackLng: FALLBACK_LOCALE,
    supportedLngs: [...SUPPORTED_LOCALES],
    defaultNS: "common",
    detection: {
      order: ["localStorage", "navigator"],
      // init() writes this cache synchronously, before the useEffect below runs, so caching here would overwrite an existing choice with the fallback; locale-toggle.tsx persists explicitly instead.
      caches: [],
      lookupLocalStorage: LOCALE_STORAGE_KEY,
    },
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
  });

export default i18n;
