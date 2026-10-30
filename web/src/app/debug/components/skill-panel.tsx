"use client";

import { useEffect, useMemo, useState } from "react";
import { Copy, Download } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import webConfig from "@/constants/common-env";
import { fetchSettingsConfig } from "@/lib/api";
import { getStoredAuthSession } from "@/store/auth";

export function SkillPanel() {
  const { t, i18n } = useTranslation("debug");
  const [browserBaseUrl, setBrowserBaseUrl] = useState("");
  const [configuredBaseUrl, setConfiguredBaseUrl] = useState("");
  const [authKey, setAuthKey] = useState("");

  useEffect(() => {
    setBrowserBaseUrl(window.location.origin);
    void fetchSettingsConfig().then((data) => setConfiguredBaseUrl(String(data.config.base_url || "").replace(/\/$/, ""))).catch(() => undefined);
    void getStoredAuthSession().then((session) => setAuthKey(session?.key || ""));
  }, []);

  const apiBaseUrl = configuredBaseUrl || webConfig.apiUrl.replace(/\/$/, "") || browserBaseUrl;
  // These two documents must render in a fixed language regardless of the active UI
  // locale, so they are read with getFixedT instead of the component's own t().
  // zh/debug.json is authoritative for skillPanel.zh*, en/debug.json for skillPanel.en*; the same keys in the other locale files are unread copies kept for check-locales.mjs parity and must be synced by hand.
  const tZh = i18n.getFixedT("zh", "debug");
  const tEn = i18n.getFixedT("en", "debug");
  const skillZh = useMemo(() => tZh("skillPanel.zhTemplate", { apiBaseUrl, authKey }), [tZh, apiBaseUrl, authKey]);
  const skillEn = useMemo(() => tEn("skillPanel.enTemplate", { apiBaseUrl, authKey }), [tEn, apiBaseUrl, authKey]);
  const zhPrompt = useMemo(() => tZh("skillPanel.zhInstallPrompt", { skillDoc: skillZh }), [tZh, skillZh]);
  const enPrompt = useMemo(() => tEn("skillPanel.enInstallPrompt", { skillDoc: skillEn }), [tEn, skillEn]);

  const copyText = async (text: string) => {
    await navigator.clipboard.writeText(text);
    toast.success(t("skillPanel.copied"));
  };

  const downloadSkill = (text: string) => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "SKILL.md";
    link.click();
    URL.revokeObjectURL(url);
  };

  const versions = [
    { title: t("skillPanel.zhTitle"), desc: t("skillPanel.zhDescription"), prompt: zhPrompt, skill: skillZh },
    { title: "English install prompt", desc: "Copy and send this to Codex or Claude to install locally.", prompt: enPrompt, skill: skillEn },
  ];

  return (
    <section className="grid items-stretch gap-4 lg:grid-cols-2">
      {versions.map((item) => (
        <div key={item.title} className="flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-white/[0.04]">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200/70 bg-slate-50/80 p-4 dark:border-white/10 dark:bg-white/[0.03]">
            <div>
              <h2 className="font-medium text-slate-900 dark:text-slate-100">{item.title}</h2>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{item.desc}</p>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => downloadSkill(item.skill)}>
                <Download />
                {t("actions.download")}
              </Button>
              <Button size="sm" className="cursor-pointer" onClick={() => void copyText(item.prompt)}>
                <Copy />
                {t("actions.copy")}
              </Button>
            </div>
          </div>
          <pre className="flex-1 whitespace-pre-wrap p-4 font-mono text-sm leading-6">
            {item.prompt}
          </pre>
        </div>
      ))}
    </section>
  );
}
