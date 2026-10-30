"use client";

import { useEffect } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";

import i18n, { FALLBACK_LOCALE, SUPPORTED_LOCALES, type Locale } from "./config";

// zh keeps the pre-existing zh-CN html lang tag; en and vi have no region variant here.
const LANG_TAGS: Partial<Record<Locale, string>> = { zh: "zh-CN" };

function detectLocale(): Locale {
  const detected = i18n.services.languageDetector?.detect();
  const candidates = Array.isArray(detected) ? detected : [detected];
  for (const candidate of candidates) {
    if (typeof candidate !== "string") continue;
    const base = candidate.split("-")[0].toLowerCase();
    const match = SUPPORTED_LOCALES.find((locale) => locale === base);
    if (match) return match;
  }
  return FALLBACK_LOCALE;
}

// React 19 hoists a <title> rendered anywhere in the tree into <head>, so this
// stays authoritative on locale change and route change instead of racing
// Next's static metadata title for ownership of document.title.
function DocumentTitle() {
  const { t } = useTranslation();
  return <title>{t("app.title")}</title>;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const locale = detectLocale();
    if (locale !== i18n.language) void i18n.changeLanguage(locale);

    const syncLang = (lng: string) => {
      document.documentElement.lang = LANG_TAGS[lng as Locale] || lng;
    };
    syncLang(i18n.language);
    i18n.on("languageChanged", syncLang);
    return () => i18n.off("languageChanged", syncLang);
  }, []);

  return (
    <I18nextProvider i18n={i18n}>
      <DocumentTitle />
      {children}
    </I18nextProvider>
  );
}
