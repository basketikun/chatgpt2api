"use client";

import { ListChecks, LoaderCircle, Pencil, Plus, RefreshCw, Rss, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import type { ProxySubscriptionSummary } from "@/lib/api";
import {
  formatProxyTime,
  formatRefreshInterval,
  isManualSubscription,
  subscriptionExpire,
  subscriptionLabel,
  subscriptionTraffic,
} from "@/lib/proxy-pool";
import { cn } from "@/lib/utils";

type ProxySubscriptionsCardProps = {
  items: ProxySubscriptionSummary[];
  isLoading: boolean;
  loadError: string;
  coreEnabled: boolean;
  refreshingIds: Set<string>;
  onAdd: () => void;
  onRetry: () => void;
  onPick: (item: ProxySubscriptionSummary) => void;
  onRefresh: (item: ProxySubscriptionSummary) => void;
  onEdit: (item: ProxySubscriptionSummary) => void;
  onDelete: (item: ProxySubscriptionSummary) => void;
};

function Stat({ label, value, className, title }: { label: string; value: number; className?: string; title?: string }) {
  return (
    <span className="whitespace-nowrap" title={title}>
      {label} <span className={cn("font-semibold text-foreground/90 tabular-nums", className)}>{value}</span>
    </span>
  );
}

function SubscriptionRow({
  item,
  coreEnabled,
  isRefreshing,
  onPick,
  onRefresh,
  onEdit,
  onDelete,
}: {
  item: ProxySubscriptionSummary;
  coreEnabled: boolean;
  isRefreshing: boolean;
} & Pick<ProxySubscriptionsCardProps, "onPick" | "onRefresh" | "onEdit" | "onDelete">) {
  const label = subscriptionLabel(item);
  // 手动添加的节点（批量添加里粘贴的分享链接）：没有地址、不能刷新，也没有流量信息
  const manual = isManualSubscription(item);
  const traffic = manual ? null : subscriptionTraffic(item.userinfo);
  const expire = manual ? null : subscriptionExpire(item.userinfo);
  const coreBlocked = !coreEnabled && item.core_count > 0;

  return (
    <li className="flex flex-col gap-3 px-3.5 py-3 lg:flex-row lg:items-start lg:justify-between">
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="truncate text-sm font-medium text-foreground" title={label}>
            {label}
          </span>
          {manual ? (
            <Badge variant="outline" className="px-1.5 py-0 text-[10.5px] text-muted-foreground" title="批量添加里粘贴的分享链接汇总在这里">
              手动添加
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="px-1.5 py-0 text-[10.5px] text-muted-foreground"
              title={item.refresh_interval_hours > 0 ? "按这个间隔自动拉取并同步节点" : "不自动刷新，需要手动点「刷新」"}
            >
              {formatRefreshInterval(item.refresh_interval_hours)}
            </Badge>
          )}
          {item.missing_count > 0 ? (
            <Badge
              variant="warning"
              className="px-1.5 py-0 text-[10.5px]"
              title="订阅中已移除或未启用内核，这些代理已自动禁用，账号临时借用其他代理"
            >
              {item.missing_count} 个不可用
            </Badge>
          ) : null}
        </div>
        {manual ? (
          <div className="text-xs text-muted-foreground">手动添加 · 在「批量添加」里粘贴分享链接或 Base64 订阅内容会加到这里</div>
        ) : label !== item.masked_url ? (
          <div className="truncate font-mono text-xs text-muted-foreground" title={item.masked_url}>
            {item.masked_url}
          </div>
        ) : null}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex flex-wrap gap-x-2">
            <Stat label="节点" value={item.node_count} />
            <span aria-hidden="true">·</span>
            <Stat label="可直连" value={item.direct_count} />
            <Stat
              label="需内核"
              value={item.core_count}
              className={coreBlocked ? "text-warning" : undefined}
              title={coreBlocked ? "需要启用 mihomo 内核才能导入" : "经 mihomo 内核转成本地 HTTP 代理"}
            />
            <Stat label="不支持" value={item.unsupported_count} />
          </span>
          <Stat label="已导入" value={item.imported_count} className={item.imported_count > 0 ? "text-success" : undefined} />
          {traffic ? (
            <span className="whitespace-nowrap" title="已用 = 上传 + 下载">
              流量 <span className="font-mono text-foreground/80">{traffic.text}</span>
              {traffic.percent != null ? (
                <span
                  className={cn(
                    "ml-1 tabular-nums",
                    traffic.percent >= 95 ? "text-destructive" : traffic.percent >= 80 ? "text-warning" : undefined,
                  )}
                >
                  {traffic.percent}%
                </span>
              ) : null}
            </span>
          ) : null}
          {expire ? (
            <span
              className={cn(
                "whitespace-nowrap",
                expire.expired ? "text-destructive" : expire.daysLeft <= 7 ? "text-warning" : undefined,
              )}
            >
              {expire.expired ? "已于" : "到期"} <span className="font-mono">{expire.date}</span>
              {expire.expired ? " 到期" : expire.daysLeft <= 30 ? `（剩 ${expire.daysLeft} 天）` : null}
            </span>
          ) : null}
          <span className="whitespace-nowrap">
            {manual ? "最近添加" : "最近拉取"} <span className="font-mono text-foreground/80">{formatProxyTime(item.last_fetched_at)}</span>
          </span>
        </div>
        {item.last_error ? (
          <div className="text-xs leading-5 break-all text-destructive">拉取失败：{item.last_error}</div>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button variant="outline" size="sm" onClick={() => onPick(item)} disabled={isRefreshing}>
          <ListChecks className="size-3.5" />
          选择节点
        </Button>
        {manual ? null : (
          <Button
            variant="ghost"
            size="icon-sm"
            className="size-8 rounded-md text-muted-foreground"
            aria-label={`刷新 ${label}`}
            title="立即拉取并同步节点"
            onClick={() => onRefresh(item)}
            disabled={isRefreshing}
          >
            {isRefreshing ? <LoaderCircle className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
          </Button>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-8 rounded-md text-muted-foreground"
          aria-label={`编辑 ${label}`}
          title="编辑"
          onClick={() => onEdit(item)}
          disabled={isRefreshing}
        >
          <Pencil className="size-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          className="size-8 rounded-md text-destructive hover:text-destructive"
          aria-label={`删除 ${label}`}
          title="删除"
          onClick={() => onDelete(item)}
          disabled={isRefreshing}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </div>
    </li>
  );
}

/** 订阅列表：节点构成、导入数、流量 / 到期、最近拉取 */
export function ProxySubscriptionsCard({
  items,
  isLoading,
  loadError,
  coreEnabled,
  refreshingIds,
  onAdd,
  onRetry,
  onPick,
  onRefresh,
  onEdit,
  onDelete,
}: ProxySubscriptionsCardProps) {
  return (
    <Card className="min-w-0 overflow-hidden">
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
            <Rss className="size-4" />
          </div>
          <div className="min-w-0 space-y-1">
            <CardTitle>订阅</CardTitle>
            <CardDescription>
              添加 Clash / V2Ray 订阅后勾选节点导入代理池；导入的代理跟随订阅刷新自动更新，节点消失时自动禁用。批量添加里粘贴的分享链接归在「手动添加的节点」。删除订阅会一并删除它导入的代理。
            </CardDescription>
          </div>
        </div>
        <Button size="sm" className="shrink-0" onClick={onAdd}>
          <Plus className="size-4" />
          添加订阅
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        {loadError && items.length > 0 ? (
          <div className="border-b border-border bg-destructive/10 px-3.5 py-2 text-xs text-destructive">
            刷新失败：{loadError}，显示的是上一次的数据。
          </div>
        ) : null}
        {items.length > 0 ? (
          <ul className="divide-y divide-border">
            {items.map((item) => (
              <SubscriptionRow
                key={item.id}
                item={item}
                coreEnabled={coreEnabled}
                isRefreshing={refreshingIds.has(item.id)}
                onPick={onPick}
                onRefresh={onRefresh}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </ul>
        ) : isLoading ? (
          <EmptyState icon={<LoaderCircle className="animate-spin" />} title="正在加载订阅" />
        ) : loadError ? (
          <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
            <p className="text-sm text-destructive">{loadError}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>
              <RefreshCw className="size-4" />
              重试
            </Button>
          </div>
        ) : (
          <EmptyState
            icon={<Rss />}
            title="还没有订阅"
            description="粘贴机场的 Clash 或 V2Ray 订阅地址，再挑选要用的节点。"
            action={
              <Button size="sm" onClick={onAdd}>
                <Plus className="size-4" />
                添加订阅
              </Button>
            }
          />
        )}
      </CardContent>
    </Card>
  );
}
