"use client";

import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LOCALE_STORAGE_KEY, SUPPORTED_LOCALES, type Locale } from "@/i18n/config";

export function LocaleToggle() {
  const { t, i18n } = useTranslation("common");

  const handleValueChange = (value: string) => {
    void i18n.changeLanguage(value as Locale);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, value);
    } catch {
      // Storage may be unavailable (private mode, disabled cookies); the
      // language still applies for this session via changeLanguage above.
    }
  };

  return (
    <Select value={i18n.language} onValueChange={handleValueChange}>
      <SelectTrigger
        aria-label={t("language.label")}
        className="h-8 w-auto gap-1 border-none bg-transparent px-2 text-sm text-stone-500 shadow-none transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {SUPPORTED_LOCALES.map((locale) => (
          <SelectItem key={locale} value={locale}>
            {t(`language.${locale}`)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
