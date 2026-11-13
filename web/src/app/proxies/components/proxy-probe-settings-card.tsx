"use client";

import { useState } from "react";
import { Activity, LoaderCircle, RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import type { ProxyPoolSettings } from "@/lib/api";

type ProbeField = "probe_interval_secs" | "failure_threshold" | "recovery_successes";

// 取值范围与后端 _SETTINGS_LIMITS 保持一致（超出范围后端会静默截断，这里提前提示）
const probeFields: { key: ProbeField; label: string; unit: string; min: number; max: number; title: string }[] = [
  { key: "probe_interval_secs", label: "探测间隔", unit: "秒", min: 10, max: 3600, title: "后台对已启用代理发起健康探测的间隔" },
  { key: "failure_threshold", label: "失败阈值", unit: "次", min: 1, max: 20, title: "连续出现这么多次代理失败后标记为异常" },
  { key: "recovery_successes", label: "恢复次数", unit: "次", min: 1, max: 20, title: "异常代理需要连续探测成功这么多次才恢复健康" },
];

type ProxyProbeSettingsCardProps = {
  settings: ProxyPoolSettings | null;
  isSaving: boolean;
  onSave: (updates: Partial<ProxyPoolSettings>) => Promise<boolean>;
};

/** 健康探测参数：间隔、失败阈值、恢复次数 */
export function ProxyProbeSettingsCard({ settings, isSaving, onSave }: ProxyProbeSettingsCardProps) {
  // 只有改过的字段才放进草稿；没改时直接显示服务端的值，轮询刷新不会覆盖正在编辑的输入
  const [draft, setDraft] = useState<Partial<Record<ProbeField, string>>>({});

  const valueOf = (key: ProbeField) => draft[key] ?? (settings ? String(settings[key]) : "");
  const isDirty = settings ? probeFields.some(({ key }) => key in draft && draft[key] !== String(settings[key])) : false;

  const handleSave = async () => {
    if (!settings) {
      return;
    }
    const updates: Partial<ProxyPoolSettings> = {};
    for (const { key, label, min, max } of probeFields) {
      if (!(key in draft)) {
        continue;
      }
      const raw = (draft[key] ?? "").trim();
      const value = Number(raw);
      if (!raw || !Number.isInteger(value) || value < min || value > max) {
        toast.error(`${label}需要是 ${min}–${max} 之间的整数`);
        return;
      }
      if (value !== settings[key]) {
        updates[key] = value;
      }
    }
    if (Object.keys(updates).length === 0) {
      setDraft({});
      return;
    }
    const ok = await onSave(updates);
    if (ok) {
      setDraft({});
    }
  };

  return (
    <Card className="min-w-0">
      <CardHeader className="flex-row items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
          <Activity className="size-4" />
        </div>
        <div className="min-w-0 space-y-1">
          <CardTitle>健康探测</CardTitle>
          <CardDescription>后台定时探测已启用的代理；连续失败达到阈值标记为异常，连续探测成功达到次数后恢复。</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2.5">
          {probeFields.map(({ key, label, unit, min, max, title }) => (
            <Field key={key} className="min-w-0 gap-1.5">
              <FieldLabel htmlFor={`proxy-pool-${key}`} title={title} className="truncate">
                {label}
                <span className="ml-1 font-normal text-muted-foreground">{unit}</span>
              </FieldLabel>
              <Input
                id={`proxy-pool-${key}`}
                type="number"
                inputMode="numeric"
                min={min}
                max={max}
                step={1}
                value={valueOf(key)}
                title={`${title}（${min}–${max}）`}
                disabled={!settings || isSaving}
                onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void handleSave();
                  }
                }}
                className="h-9 font-mono text-[13px] tabular-nums"
              />
            </Field>
          ))}
        </div>
        <div className="flex justify-end gap-1.5">
          {isDirty ? (
            <Button variant="ghost" size="sm" onClick={() => setDraft({})} disabled={isSaving}>
              <RotateCcw className="size-3.5" />
              还原
            </Button>
          ) : null}
          <Button size="sm" onClick={() => void handleSave()} disabled={!settings || !isDirty || isSaving}>
            {isSaving ? <LoaderCircle className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
            保存
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
