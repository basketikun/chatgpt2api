"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import webConfig from "@/constants/common-env";
import { useVersionCheck } from "@/hooks/use-version-check";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function typeVariant(type: string): "success" | "danger" | "info" | "violet" | "outline" {
  if (type === "新增") return "success";
  if (type === "修复") return "danger";
  if (type === "调整") return "info";
  if (type === "文档") return "violet";
  return "outline";
}

export function VersionReleaseDialog({ className }: { className?: string }) {
  const { t } = useI18n();
  const {
    open,
    setOpen,
    openReleaseModal,
    latestVersion,
    releases,
    checking,
    hasNewVersion,
    checkLatestRelease,
  } = useVersionCheck();

  const renderType = (type: string) => {
    if (type === "新增") return t.release.tagNew;
    if (type === "修复") return t.release.tagFix;
    if (type === "调整") return t.release.tagTweak;
    if (type === "文档") return t.release.tagDoc;
    return type;
  };

  return (
    <>
      <button
        type="button"
        className={cn(
          "relative px-1 py-1 text-[11px] font-medium text-stone-500 transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white",
          className,
        )}
        onClick={openReleaseModal}
        title={t.release.checkUpdate}
      >
        v{webConfig.appVersion}
        {hasNewVersion ? (
          <span className="absolute -top-1 -right-1 size-2 rounded-full bg-emerald-500" />
        ) : null}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="w-[min(94vw,680px)] rounded-2xl">
          <DialogHeader>
            <DialogTitle>{t.release.title}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <VersionCard label={t.release.currentVersion} value={webConfig.appVersion} />
            <VersionCard
              label={t.release.latestVersion}
              value={latestVersion}
              action={
                <button
                  type="button"
                  className="text-[11px] text-stone-400 underline-offset-2 hover:text-stone-700 hover:underline dark:hover:text-stone-200"
                  onClick={() => void checkLatestRelease(true)}
                >
                  {checking ? t.release.checking : t.release.checkUpdate}
                </button>
              }
            />
          </div>
          <div className="max-h-[56vh] space-y-5 overflow-y-auto pr-1">
            {releases.map((release) => (
              <div key={release.version} className="border-l border-stone-200 pl-4 dark:border-white/10">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-stone-950 dark:text-stone-100">
                    {release.version === "Unreleased" ? t.release.unreleased : release.version}
                  </span>
                  <span className="text-xs text-stone-500 dark:text-stone-400">{release.date}</span>
                  {release.version === latestVersion ? <Badge variant="success">{t.release.latest}</Badge> : null}
                  {release.version === webConfig.appVersion ? <Badge variant="outline">{t.release.current}</Badge> : null}
                </div>
                <div className="mt-2 space-y-1.5">
                  {release.items.map((item, index) => (
                    <div key={index} className="flex items-start gap-2 text-sm leading-6 text-stone-700 dark:text-stone-300">
                      <Badge variant={typeVariant(item.type)} className="mt-0.5 shrink-0">
                        {renderType(item.type)}
                      </Badge>
                      <span className="min-w-0 flex-1">{item.content}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" asChild>
            <a href="https://github.com/basketikun/chatgpt2api" target="_blank" rel="noreferrer">
              {t.release.goToGithub}
            </a>
          </Button>
        </DialogContent>
      </Dialog>
    </>
  );
}

function VersionCard({
  label,
  value,
  action,
}: {
  label: string;
  value: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-stone-200 bg-white/55 p-3 dark:border-white/10 dark:bg-white/5">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-stone-500 dark:text-stone-400">{label}</div>
        {action}
      </div>
      <div className="mt-1 text-base font-semibold text-stone-950 dark:text-stone-100">{value}</div>
    </div>
  );
}
