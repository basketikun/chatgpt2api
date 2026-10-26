"use client";

import { ExternalLink, LoaderCircle, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n";

import { useSettingsStore } from "../store";

export function ThirdPartyAppsCard() {
  const { tText } = useI18n();
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setInfiniteCanvasField = useSettingsStore((state) => state.setInfiniteCanvasField);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  if (isLoadingConfig || !config?.third_party_apps) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  const canvas = config.third_party_apps.infinite_canvas;

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-5 p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-base font-semibold text-stone-900">
              <ExternalLink className="size-5 text-stone-500" />
              {tText("无限画布入口")}
            </div>
            <p className="mt-1 text-xs leading-6 text-stone-500">{tText("开启后会在顶部导航显示入口，跳转时自动附带本项目地址和当前密钥。")}</p>
          </div>
          <span className={`rounded-full px-3 py-1 text-xs ${canvas.enabled ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500"}`}>
            {canvas.enabled ? tText("已启用") : tText("未启用")}
          </span>
        </div>

        <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3">
          <label className="flex items-center gap-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(canvas.enabled)}
              onCheckedChange={(checked) => setInfiniteCanvasField("enabled", Boolean(checked))}
            />
            {tText("启用无限画布")}
          </label>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">{tText("无限画布地址")}</label>
            <Input
              value={canvas.url}
              onChange={(event) => setInfiniteCanvasField("url", event.target.value)}
              placeholder="https://canvas.best"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs leading-5 text-stone-500">
              {tText("顶部入口跳转时会追加 apiKey 和 baseUrl 参数；关闭后顶部导航不显示无限画布。")}
            </p>
            <p className="text-xs leading-5 text-amber-700">
              {tText("该入口仅供个人测试使用；长期使用建议自行本机部署无限画布。")}
            </p>
          </div>
        </div>

        <div className="flex justify-end">
          <Button className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800" onClick={() => void saveConfig()} disabled={isSavingConfig}>
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            {tText("保存")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
