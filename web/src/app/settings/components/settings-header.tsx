"use client";

import { useI18n } from "@/lib/i18n";

export function SettingsHeader() {
  const { t } = useI18n();
  return (
    <section className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div className="space-y-1">
        <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Settings</div>
        <h1 className="text-2xl font-semibold tracking-tight">{t.settings.title}</h1>
      </div>
    </section>
  );
}
