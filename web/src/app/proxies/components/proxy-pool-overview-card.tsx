"use client";

import { LoaderCircle, Network } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import type { ProxyPoolSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

export const POOL_HINT =
  "建议先批量录入全部代理再开启；已绑定的账号不会自动迁移，只有删除代理才会改绑；绑定代理禁用或异常时临时借用其他代理";

type ProxyPoolOverviewCardProps = {
  enabled: boolean;
  summary: ProxyPoolSummary | null;
  isSaving: boolean;
  disabled?: boolean;
  onToggle: (next: boolean) => void;
};

function SummaryTile({ label, value, tone }: { label: string; value: number | null; tone?: "danger" | "warning" | "success" }) {
  const toneClass =
    value && tone === "danger"
      ? "text-destructive"
      : value && tone === "warning"
        ? "text-warning"
        : value && tone === "success"
          ? "text-success"
          : "text-foreground";
  return (
    <div className="min-w-0 space-y-1 bg-card px-4 py-3">
      <div className="truncate text-xs text-muted-foreground">{label}</div>
      <div className={cn("text-lg leading-none font-semibold tabular-nums", toneClass)}>
        {value == null ? "—" : value}
      </div>
    </div>
  );
}

/** 代理池总开关 + 汇总数字 */
export function ProxyPoolOverviewCard({ enabled, summary, isSaving, disabled, onToggle }: ProxyPoolOverviewCardProps) {
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <Network className="size-4" />
          </div>
          <div className="min-w-0 space-y-1">
            <CardTitle className="flex flex-wrap items-center gap-2">
              启用代理池
              <Badge variant={enabled ? "success" : "secondary"}>{enabled ? "已开启" : "未开启"}</Badge>
            </CardTitle>
            <CardDescription>{POOL_HINT}</CardDescription>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 pt-0.5">
          {isSaving ? <LoaderCircle className="size-4 animate-spin text-muted-foreground" /> : null}
          <Switch checked={enabled} onCheckedChange={onToggle} disabled={disabled || isSaving} aria-label="启用代理池" />
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-px bg-border p-0 sm:grid-cols-3 2xl:grid-cols-6">
        <SummaryTile label="代理总数" value={summary?.total ?? null} />
        <SummaryTile label="已启用" value={summary?.enabled ?? null} />
        <SummaryTile label="健康" value={summary?.healthy ?? null} tone="success" />
        <SummaryTile label="异常" value={summary?.unhealthy ?? null} tone="danger" />
        <SummaryTile label="已绑定账号" value={summary?.bound_accounts ?? null} />
        <SummaryTile label="未绑定账号" value={summary?.unbound_accounts ?? null} tone={enabled ? "warning" : undefined} />
      </CardContent>
    </Card>
  );
}
