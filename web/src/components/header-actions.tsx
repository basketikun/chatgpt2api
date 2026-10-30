"use client";

import { LocaleToggle } from "@/components/locale-toggle";
import { ThemeToggle } from "@/components/theme-toggle";
import { VersionReleaseDialog } from "@/components/version-release-dialog";
import { cn } from "@/lib/utils";

export function HeaderActions({ className, showGithubText = true }: { className?: string; showGithubText?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2 sm:gap-3", className)}>
      <LocaleToggle />
      <ThemeToggle />
      <a
        href="https://github.com/basketikun/chatgpt2api"
        target="_blank"
        rel="noreferrer"
        className="inline-flex h-8 items-center justify-center gap-1.5 text-sm text-stone-500 transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white"
        aria-label="GitHub repository"
      >
        <img src="/github.svg" alt="" className="size-4" />
        {showGithubText ? <span className="hidden sm:inline">GitHub</span> : null}
      </a>
      <VersionReleaseDialog />
    </div>
  );
}
