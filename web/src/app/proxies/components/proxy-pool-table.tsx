"use client";

import { useMemo } from "react";
import { ArrowDownLeft, ArrowUpRight, LoaderCircle, Network, Pencil, PlugZap, Plus, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Switch } from "@/components/ui/switch";
import type { ProxyPoolItem } from "@/lib/api";
import { duplicateExitIps, formatProxyTime, getProxyHealthMeta, proxySourceLabel } from "@/lib/proxy-pool";
import { cn } from "@/lib/utils";

type ProxyPoolTableProps = {
  items: ProxyPoolItem[];
  isLoading: boolean;
  pendingIds: Set<string>;
  testingIds: Set<string>;
  onToggle: (item: ProxyPoolItem, enabled: boolean) => void;
  onTest: (item: ProxyPoolItem) => void;
  onEdit: (item: ProxyPoolItem) => void;
  onDelete: (item: ProxyPoolItem) => void;
  onAdd: () => void;
};

function healthTitle(item: ProxyPoolItem) {
  const health = item.health;
  const meta = getProxyHealthMeta(health?.state);
  const lines = [
    `状态：${meta.label}`,
    health?.consecutive_failures ? `连续失败：${health.consecutive_failures} 次` : null,
    `最近探测：${formatProxyTime(health?.last_probe_at)}`,
    `最近成功：${formatProxyTime(health?.last_ok_at)}`,
    health?.last_error_at ? `最近失败：${formatProxyTime(health.last_error_at)}` : null,
    health?.last_error ? health.last_error : null,
  ].filter((line): line is string => Boolean(line));
  return lines.join("\n");
}

function HealthCell({ item }: { item: ProxyPoolItem }) {
  const health = item.health;
  const meta = getProxyHealthMeta(health?.state);
  return (
    <span
      tabIndex={0}
      title={healthTitle(item)}
      className="inline-flex rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      aria-label={`健康状态 ${meta.label}${health?.last_error ? `，最近错误 ${health.last_error}` : ""}`}
    >
      <Badge variant={meta.variant} className="px-2 py-0 text-[11.5px]">
        <span aria-hidden="true" className={cn("size-1.5 rounded-full", meta.dotClass)} />
        {meta.label}
        {health?.consecutive_failures && health.state !== "unhealthy" ? (
          <span className="tabular-nums opacity-80">×{health.consecutive_failures}</span>
        ) : null}
      </Badge>
    </span>
  );
}

/** 带悬浮说明的小标签；用原生 title 提供悬浮说明 */
function HintBadge({
  label,
  hint,
  variant,
  className,
}: {
  label: string;
  hint: string;
  variant: "warning" | "outline" | "violet";
  className?: string;
}) {
  return (
    <span
      tabIndex={0}
      title={hint}
      className="inline-flex min-w-0 shrink-0 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      aria-label={`${label}：${hint}`}
    >
      <Badge variant={variant} className={cn("px-1.5 py-0 text-[10.5px]", className)}>
        {label}
      </Badge>
    </span>
  );
}

const MISSING_HINT = "订阅中已移除或未启用内核，已自动禁用，账号临时借用其他代理";
const DUPLICATE_EXIT_HINT = "多个代理出口 IP 相同，均分效果会打折扣";

function SourceTags({ item }: { item: ProxyPoolItem }) {
  if (item.source === "subscription" || item.subscription_id) {
    const name = item.subscription_name?.trim();
    return (
      <>
        <Badge
          variant="outline"
          className="block max-w-[150px] min-w-0 shrink truncate px-1.5 py-0 text-[10.5px] text-muted-foreground"
          title={`从订阅${name ? `「${name}」` : ""}导入，地址由订阅维护`}
        >
          {name ? `订阅 · ${name}` : "订阅"}
        </Badge>
        {item.via_core ? (
          <Badge variant="violet" className="shrink-0 px-1.5 py-0 text-[10.5px]" title="经 mihomo 内核转成本地 HTTP 代理">
            内核
          </Badge>
        ) : null}
      </>
    );
  }
  if (item.source === "manual" || !proxySourceLabel[item.source]) {
    return null;
  }
  return (
    <Badge
      variant="outline"
      className="shrink-0 px-1.5 py-0 text-[10.5px] text-muted-foreground"
      title={item.source === "legacy_account" ? "开启代理池时从账号上原有的代理迁移而来" : "随账号导入时加入"}
    >
      {proxySourceLabel[item.source]}
    </Badge>
  );
}

function BorrowCell({ item }: { item: ProxyPoolItem }) {
  const borrowingIn = item.borrowing_count ?? 0;
  const borrowedOut = item.borrowed_out_count ?? 0;
  return (
    <span className="inline-flex items-center gap-2.5 font-mono text-xs">
      <span
        className={cn("inline-flex items-center gap-0.5", borrowingIn > 0 ? "font-semibold text-info" : "text-muted-foreground")}
        title={`借入：其他代理的 ${borrowingIn} 个账号正在临时使用本代理`}
      >
        <ArrowDownLeft className="size-3" aria-hidden="true" />
        {borrowingIn}
      </span>
      <span
        className={cn("inline-flex items-center gap-0.5", borrowedOut > 0 ? "font-semibold text-warning" : "text-muted-foreground")}
        title={`借出：本代理绑定的 ${borrowedOut} 个账号正在临时使用其他代理`}
      >
        <ArrowUpRight className="size-3" aria-hidden="true" />
        {borrowedOut}
      </span>
    </span>
  );
}

function formatLatency(latency?: number | null) {
  if (latency == null) {
    return { text: "—", className: "text-muted-foreground" };
  }
  const className = latency >= 3000 ? "text-destructive" : latency >= 1500 ? "text-warning" : "text-foreground/80";
  return { text: `${Math.round(latency)} ms`, className };
}

export function ProxyPoolTable({
  items,
  isLoading,
  pendingIds,
  testingIds,
  onToggle,
  onTest,
  onEdit,
  onDelete,
  onAdd,
}: ProxyPoolTableProps) {
  const duplicateIps = useMemo(() => duplicateExitIps(items), [items]);

  if (items.length === 0) {
    return isLoading ? (
      <EmptyState icon={<LoaderCircle className="animate-spin" />} title="正在加载代理池" description="从后端同步代理列表和健康状态。" />
    ) : (
      <EmptyState
        icon={<Network />}
        title="代理池里还没有代理"
        description="点击「批量添加」一次粘贴多个代理，一行一个。"
        action={
          <Button size="sm" onClick={onAdd}>
            <Plus className="size-4" />
            批量添加
          </Button>
        }
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1080px] text-left text-[13px] tabular-nums">
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b border-border [&>th]:h-8 [&>th]:px-2.5 [&>th]:font-medium [&>th]:whitespace-nowrap">
            <th className="!pl-3.5">名称</th>
            <th>地址</th>
            <th>启用</th>
            <th>健康</th>
            <th className="text-right">延迟</th>
            <th>出口 IP</th>
            <th className="text-right">绑定账号</th>
            <th title="借入 / 借出：绑定代理禁用或异常时，账号会临时借用其他代理">借用 入 / 出</th>
            <th className="w-[112px] !pr-3.5 text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const isPending = pendingIds.has(item.id);
            const isTesting = testingIds.has(item.id);
            const latency = formatLatency(item.health?.latency_ms);
            const displayName = item.name?.trim();
            const rowLabel = displayName || item.masked_url;

            return (
              <tr
                key={item.id}
                className={cn(
                  "group border-b border-border/70 text-foreground/80 transition-colors last:border-b-0 hover:bg-accent/60 [&>td]:h-10 [&>td]:px-2.5 [&>td]:whitespace-nowrap",
                  !item.enabled && "text-muted-foreground",
                )}
              >
                <td className="!pl-3.5">
                  <div className="flex max-w-[320px] items-center gap-1.5">
                    <span
                      className={cn("min-w-0 truncate", displayName ? "text-foreground" : "text-muted-foreground")}
                      title={displayName || undefined}
                    >
                      {displayName || "未命名"}
                    </span>
                    <SourceTags item={item} />
                  </div>
                </td>
                <td>
                  <span className="block max-w-[260px] truncate font-mono text-xs" title={item.masked_url}>
                    {item.masked_url}
                  </span>
                </td>
                <td>
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={item.enabled}
                      onCheckedChange={(next) => onToggle(item, next)}
                      disabled={isPending}
                      aria-label={`${item.enabled ? "禁用" : "启用"} ${rowLabel}`}
                    />
                    {item.missing ? <HintBadge label="节点不可用" hint={MISSING_HINT} variant="warning" /> : null}
                  </div>
                </td>
                <td>
                  <HealthCell item={item} />
                </td>
                <td className={cn("text-right font-mono text-xs", latency.className)}>{latency.text}</td>
                <td>
                  {item.health?.exit_ip ? (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="font-mono text-xs text-foreground/80">{item.health.exit_ip}</span>
                      {item.enabled && duplicateIps.has(item.health.exit_ip.trim()) ? (
                        <HintBadge
                          label="出口重复"
                          hint={`${DUPLICATE_EXIT_HINT}（${duplicateIps.get(item.health.exit_ip.trim())} 个已启用的代理共用这个出口）`}
                          variant="warning"
                        />
                      ) : null}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
                <td className="text-right font-mono text-xs">
                  <span className={item.bound_count > 0 ? "font-semibold text-foreground" : "text-muted-foreground"}>
                    {item.bound_count}
                  </span>
                </td>
                <td>
                  <BorrowCell item={item} />
                </td>
                <td className="!pr-3.5">
                  <div className="flex items-center justify-end gap-0.5">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="size-7 rounded-md text-muted-foreground"
                      aria-label={`测试 ${rowLabel}`}
                      title="立即测试并更新健康状态"
                      onClick={() => onTest(item)}
                      disabled={isTesting}
                    >
                      {isTesting ? <LoaderCircle className="size-3.5 animate-spin" /> : <PlugZap className="size-3.5" />}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="size-7 rounded-md text-muted-foreground"
                      aria-label={`编辑 ${rowLabel}`}
                      title="编辑"
                      onClick={() => onEdit(item)}
                      disabled={isPending}
                    >
                      <Pencil className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="size-7 rounded-md text-destructive hover:text-destructive"
                      aria-label={`删除 ${rowLabel}`}
                      title="删除"
                      onClick={() => onDelete(item)}
                      disabled={isPending}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
