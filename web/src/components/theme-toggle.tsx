"use client";

import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler";
import { useI18n } from "@/lib/i18n";

export function ThemeToggle() {
  const { tText } = useI18n();
  return (
    <AnimatedThemeToggler
      aria-label={tText("切换主题")}
      title={tText("切换主题")}
      variant="circle"
      className="inline-flex size-8 shrink-0 items-center justify-center text-stone-500 transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white [&_svg]:size-4"
    />
  );
}
