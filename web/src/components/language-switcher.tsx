"use client";

import { useState } from "react";
import { Check, Globe } from "lucide-react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { LOCALES, useI18n, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useI18n();
  const [open, setOpen] = useState(false);

  const currentLocaleObj = LOCALES.find((l) => l.code === locale) || LOCALES[0];

  const handleSelect = (code: Locale) => {
    setLocale(code);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex h-8 items-center justify-center gap-1.5 rounded-lg px-2 text-xs font-medium text-stone-500 transition hover:bg-stone-100 hover:text-stone-900 dark:text-stone-300 dark:hover:bg-white/10 dark:hover:text-white",
            className,
          )}
          aria-label="Select Language"
          title="Language / زبان / اللغة"
        >
          <Globe className="size-4 shrink-0" />
          <span className="hidden text-xs sm:inline">{currentLocaleObj.nativeName}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-40 rounded-xl p-1 shadow-lg">
        <div className="flex flex-col gap-0.5">
          {LOCALES.map((item) => {
            const isSelected = item.code === locale;
            return (
              <button
                key={item.code}
                type="button"
                onClick={() => handleSelect(item.code)}
                className={cn(
                  "flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                  isSelected
                    ? "bg-stone-950 text-white dark:bg-white dark:text-stone-950"
                    : "text-stone-700 hover:bg-stone-100 dark:text-stone-200 dark:hover:bg-white/10",
                )}
              >
                <span>{item.nativeName}</span>
                {isSelected ? <Check className="size-3.5" /> : null}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
