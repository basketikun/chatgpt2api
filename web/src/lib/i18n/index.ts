"use client";

import { useEffect } from "react";
import { create } from "zustand";
import { ar } from "./ar";
import { en } from "./en";
import { fa } from "./fa";
import type { Locale, Translations } from "./types";
import { zh } from "./zh";

export * from "./types";

export const LOCALES: { code: Locale; name: string; nativeName: string; dir: "ltr" | "rtl" }[] = [
  { code: "en", name: "English", nativeName: "English", dir: "ltr" },
  { code: "fa", name: "Persian", nativeName: "فارسی", dir: "rtl" },
  { code: "ar", name: "Arabic", nativeName: "العربية", dir: "rtl" },
  { code: "zh", name: "Chinese", nativeName: "简体中文", dir: "ltr" },
];

export const translations: Record<Locale, Translations> = {
  en,
  fa,
  ar,
  zh,
};

const STORAGE_KEY = "chatgpt2api_locale";

function getInitialLocale(): Locale {
  if (typeof window === "undefined") {
    return "en";
  }
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "fa" || stored === "ar" || stored === "zh") {
      return stored;
    }
    // Check browser languages
    const browserLang = navigator.language?.toLowerCase() || "";
    if (browserLang.startsWith("fa")) return "fa";
    if (browserLang.startsWith("ar")) return "ar";
    if (browserLang.startsWith("zh")) return "zh";
  } catch {
    // Ignore localStorage errors
  }
  return "en";
}

export function applyLocaleToDocument(locale: Locale) {
  if (typeof document === "undefined") {
    return;
  }
  const isRtl = locale === "fa" || locale === "ar";
  document.documentElement.lang = locale;
  document.documentElement.dir = isRtl ? "rtl" : "ltr";
  if (isRtl) {
    document.documentElement.classList.add("rtl");
    document.documentElement.classList.remove("ltr");
  } else {
    document.documentElement.classList.add("ltr");
    document.documentElement.classList.remove("rtl");
  }
}

interface I18nState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const useI18nStore = create<I18nState>((set) => ({
  locale: typeof window !== "undefined" ? getInitialLocale() : "en",
  setLocale: (locale: Locale) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      // Ignore storage errors
    }
    applyLocaleToDocument(locale);
    set({ locale });
  },
}));

export function useI18n() {
  const { locale, setLocale } = useI18nStore();

  useEffect(() => {
    applyLocaleToDocument(locale);
  }, [locale]);

  const t = translations[locale] || translations.en;
  const isRtl = locale === "fa" || locale === "ar";
  const dir = isRtl ? "rtl" : "ltr";

  const translateStatus = (status: string): string => {
    switch (status) {
      case "正常":
        return t.accounts.statusActive;
      case "限流":
        return t.accounts.statusLimited;
      case "异常":
        return t.accounts.statusAbnormal;
      case "禁用":
        return t.accounts.statusDisabled;
      default:
        return status;
    }
  };

  return {
    locale,
    setLocale,
    t,
    isRtl,
    dir,
    translateStatus,
  };
}

export function getI18n() {
  const locale = useI18nStore.getState().locale;
  const t = translations[locale] || translations.en;
  return { locale, t };
}
