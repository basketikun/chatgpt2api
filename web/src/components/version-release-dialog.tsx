"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

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
import { cn } from "@/lib/utils";

function typeVariant(type: string): "success" | "danger" | "info" | "violet" | "outline" {
  if (type === "新增") return "success";
  if (type === "修复") return "danger";
  if (type === "调整") return "info";
  if (type === "文档") return "violet";
  return "outline";
}

const CHANGELOG_TYPE_KEYS: Record<string, string> = {
  "新增": "versionDialog.typeNew",
  "修复": "versionDialog.typeFix",
  "调整": "versionDialog.typeUpdate",
  "文档": "versionDialog.typeDocs",
};

export function VersionReleaseDialog({ className }: { className?: string }) {
  const { t } = useTranslation("common");
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

  return (
    <>
      <button
        type="button"
        className={cn(
          "relative px-1 py-1 text-[11px] font-medium text-stone-500 transition hover:text-stone-900 dark:text-stone-300 dark:hover:text-white",
          className,
        )}
        onClick={openReleaseModal}
        title={t("versionDialog.viewUpdates")}
      >
        v{webConfig.appVersion}
        {hasNewVersion ? (
          <span className="absolute -top-1 -right-1 size-2 rounded-full bg-emerald-500" />
        ) : null}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="w-[min(94vw,680px)] rounded-2xl">
          <DialogHeader>
            <DialogTitle>{t("versionDialog.title")}</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <VersionCard label={t("versionDialog.currentVersion")} value={webConfig.appVersion} />
            <VersionCard
              label={t("versionDialog.latestVersion")}
              value={latestVersion}
              action={
                <button
                  type="button"
                  className="text-[11px] text-stone-400 underline-offset-2 hover:text-stone-700 hover:underline dark:hover:text-stone-200"
                  onClick={() => void checkLatestRelease(true)}
                >
                  {checking ? t("versionDialog.checking") : t("versionDialog.checkUpdate")}
                </button>
              }
            />
          </div>
          <div className="max-h-[56vh] space-y-5 overflow-y-auto pr-1">
            {releases.map((release) => (
              <div key={release.version} className="border-l border-stone-200 pl-4 dark:border-white/10">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-stone-950 dark:text-stone-100">
                    {release.version === "Unreleased" ? t("versionDialog.unreleased") : release.version}
                  </span>
                  <span className="text-xs text-stone-500 dark:text-stone-400">{release.date}</span>
                  {release.version === latestVersion ? <Badge variant="success">{t("versionDialog.latest")}</Badge> : null}
                  {release.version === webConfig.appVersion ? <Badge variant="outline">{t("versionDialog.current")}</Badge> : null}
                </div>
                <div className="mt-2 space-y-1.5">
                  {release.items.map((item, index) => {
                    const typeKey = CHANGELOG_TYPE_KEYS[item.type];
                    return (
                      <div key={index} className="flex items-start gap-2 text-sm leading-6 text-stone-700 dark:text-stone-300">
                        <Badge variant={typeVariant(item.type)} className="mt-0.5 shrink-0">
                          {typeKey ? t(typeKey) : item.type}
                        </Badge>
                        <span className="min-w-0 flex-1">{item.content}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          <Button variant="outline" size="sm" asChild>
            <a href="https://github.com/basketikun/chatgpt2api" target="_blank" rel="noreferrer">
              {t("versionDialog.githubUpdate")}
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
