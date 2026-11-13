"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, ListChecks, LoaderCircle, RefreshCw, Rss, SearchX } from "lucide-react";
import { toast } from "sonner";

import { SearchInput } from "@/components/search-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { SegmentedControl } from "@/components/ui/segmented-control";
import {
  fetchProxySubscription,
  importProxySubscriptionNodes,
  refreshProxySubscription,
  type ProxyCoreApplyResult,
  type ProxySubscriptionDetail,
  type ProxySubscriptionNode,
  type ProxySubscriptionsPayload,
} from "@/lib/api";
import {
  describeRefreshResult,
  filterSubscriptionNodes,
  isManualSubscription,
  isNodeSelectable,
  nodeModeLabel,
  subscriptionLabel,
  type NodeModeFilter,
} from "@/lib/proxy-pool";
import { cn } from "@/lib/utils";

export type NodePickerTarget = {
  id: string;
  /** 新建订阅时接口已经带回了节点列表，直接用，不再请求一次 */
  initial?: ProxySubscriptionDetail;
};

type ImportSummary = {
  added: number;
  assigned: number;
  skipped: Array<{ key: string; reason: string }>;
  coreApply: ProxyCoreApplyResult | null;
};

type ProxySubscriptionNodePickerProps = {
  target: NodePickerTarget | null;
  onClose: () => void;
  /** 导入 / 拉取之后订阅列表和代理池都可能变了 */
  onChanged: (data: ProxySubscriptionsPayload) => void;
};

export function ProxySubscriptionNodePicker({ target, onClose, onChanged }: ProxySubscriptionNodePickerProps) {
  return (
    <Dialog open={Boolean(target)} onOpenChange={(open) => (!open ? onClose() : null)}>
      {target ? <NodePickerContent key={target.id} target={target} onClose={onClose} onChanged={onChanged} /> : null}
    </Dialog>
  );
}

function NodeStatus({ node }: { node: ProxySubscriptionNode }) {
  if (node.imported) {
    return (
      <Badge variant="success" className="px-1.5 py-0 text-[10.5px]">
        已导入
      </Badge>
    );
  }
  if (!node.available) {
    return (
      <span
        className={cn("block truncate text-xs", node.mode === "core" ? "text-warning" : "text-muted-foreground")}
        title={node.reason || undefined}
      >
        {node.reason || "不可导入"}
      </span>
    );
  }
  return node.mode === "core" ? (
    <Badge variant="violet" className="px-1.5 py-0 text-[10.5px]" title="经 mihomo 内核转成本地 HTTP 代理">
      经内核
    </Badge>
  ) : (
    <span className="text-xs text-muted-foreground">直连</span>
  );
}

function NodePickerContent({
  target,
  onClose,
  onChanged,
}: {
  target: NodePickerTarget;
  onClose: () => void;
  onChanged: (data: ProxySubscriptionsPayload) => void;
}) {
  const [detail, setDetail] = useState<ProxySubscriptionDetail | null>(target.initial ?? null);
  const [loadError, setLoadError] = useState("");
  const [isLoading, setIsLoading] = useState(!target.initial);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<NodeModeFilter>("all");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [summary, setSummary] = useState<ImportSummary | null>(null);

  const isBusy = isImporting || isRefreshing;

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchProxySubscription(target.id);
      setDetail(data.item);
      setLoadError("");
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "加载节点失败");
    } finally {
      setIsLoading(false);
    }
  }, [target.id]);

  useEffect(() => {
    if (!target.initial) {
      void load();
    }
  }, [load, target.initial]);

  const nodes = useMemo(() => detail?.nodes ?? [], [detail]);
  const visible = useMemo(() => filterSubscriptionNodes(nodes, query, mode), [nodes, query, mode]);
  const visibleSelectable = useMemo(() => visible.filter(isNodeSelectable), [visible]);
  const allVisibleSelected = visibleSelectable.length > 0 && visibleSelectable.every((node) => selected.has(node.key));

  const modeOptions = useMemo(() => {
    const count = (value: NodeModeFilter) => (value === "all" ? nodes.length : nodes.filter((node) => node.mode === value).length);
    return (["all", "direct", "core", "unsupported"] as const).map((value) => ({
      value,
      label: (
        <>
          {value === "all" ? "全部" : nodeModeLabel[value]}
          <span className="tabular-nums opacity-70">{count(value)}</span>
        </>
      ),
    }));
  }, [nodes]);

  const toggle = (node: ProxySubscriptionNode, next?: boolean) => {
    if (!isNodeSelectable(node) || isBusy) {
      return;
    }
    setSelected((current) => {
      const copy = new Set(current);
      if (next ?? !copy.has(node.key)) {
        copy.add(node.key);
      } else {
        copy.delete(node.key);
      }
      return copy;
    });
  };

  /** 只作用于当前筛选出来的节点 */
  const setVisibleSelected = (next: boolean) => {
    setSelected((current) => {
      const copy = new Set(current);
      for (const node of visibleSelectable) {
        if (next) {
          copy.add(node.key);
        } else {
          copy.delete(node.key);
        }
      }
      return copy;
    });
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const data = await refreshProxySubscription(target.id);
      setDetail(data.item);
      setLoadError("");
      onChanged({ items: data.items, core: data.core });
      // 节点列表变了：丢掉已经不能再选的勾选
      const selectable = new Set(data.item.nodes.filter(isNodeSelectable).map((node) => node.key));
      setSelected((current) => new Set([...current].filter((key) => selectable.has(key))));
      if (data.result.ok) {
        toast.success(`已重新拉取：${describeRefreshResult(data.result)}`);
      } else {
        toast.error(describeRefreshResult(data.result));
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "拉取订阅失败");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleImport = async () => {
    const keys = nodes.filter((node) => selected.has(node.key)).map((node) => node.key);
    if (keys.length === 0) {
      return;
    }
    setIsImporting(true);
    try {
      const data = await importProxySubscriptionNodes(target.id, keys);
      setDetail(data.item);
      setSelected(new Set());
      onChanged({ items: data.items, core: data.core });
      const skipped = Array.isArray(data.skipped) ? data.skipped : [];
      const coreFailed = data.core_apply?.ok === false;
      const assignedText = data.assigned > 0 ? `，已为 ${data.assigned} 个未绑定账号分配代理` : "";
      if (skipped.length === 0 && !coreFailed) {
        toast.success(`已导入 ${data.added} 个节点${assignedText}`);
        onClose();
        return;
      }
      setSummary({ added: data.added, assigned: data.assigned, skipped, coreApply: data.core_apply });
      if (data.added > 0) {
        toast.warning(`已导入 ${data.added} 个节点${skipped.length ? `，跳过 ${skipped.length} 个` : ""}${coreFailed ? "，内核配置未生效" : ""}`);
      } else {
        toast.error(skipped.length ? `没有导入节点，跳过 ${skipped.length} 个` : "内核配置应用失败");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "导入节点失败");
    } finally {
      setIsImporting(false);
    }
  };

  const label = detail ? subscriptionLabel(detail) : "";
  // 「手动添加的节点」没有订阅地址，不能重新拉取
  const isManual = Boolean(detail && isManualSubscription(detail));
  const coreBlocked = nodes.filter((node) => node.mode === "core" && !node.available && !node.imported).length;

  return (
    <DialogContent
      className="flex max-h-[min(88vh,820px)] w-[min(94vw,880px)] flex-col"
      onInteractOutside={(event) => (isBusy ? event.preventDefault() : undefined)}
      onEscapeKeyDown={(event) => (isBusy ? event.preventDefault() : undefined)}
    >
      <DialogHeader className="gap-2 pr-8">
        <DialogTitle className="truncate">选择节点{label ? ` · ${label}` : ""}</DialogTitle>
        <DialogDescription className="text-sm leading-6">
          勾选要导入代理池的节点。HTTP / SOCKS5 节点直接导入；ss / vmess / vless / trojan 等节点需要启用 mihomo 内核。导入后跟随订阅刷新自动更新。
        </DialogDescription>
      </DialogHeader>

      {detail?.last_error ? (
        <div className="rounded-xl bg-destructive/10 px-3.5 py-2 text-xs leading-5 break-all text-destructive">
          最近一次拉取失败：{detail.last_error}
        </div>
      ) : null}
      {coreBlocked > 0 ? (
        <div className="rounded-xl bg-warning/12 px-3.5 py-2 text-xs leading-5 text-warning">
          有 {coreBlocked} 个节点需要 mihomo 内核才能导入：在「订阅」页下方展开「mihomo 内核」，启动 proxy-core 并启用后再来导入。
        </div>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <SearchInput
            size="sm"
            value={query}
            onValueChange={setQuery}
            placeholder="搜索名称、类型、地址"
            className="w-full sm:w-56"
          />
          <SegmentedControl size="sm" value={mode} onValueChange={setMode} options={modeOptions} aria-label="按导入方式筛选" />
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setVisibleSelected(!allVisibleSelected)}
            disabled={isBusy || visibleSelectable.length === 0}
          >
            <ListChecks className="size-3.5" />
            {allVisibleSelected ? "取消全选" : `全选可导入${visibleSelectable.length ? ` ${visibleSelectable.length}` : ""}`}
          </Button>
          {isManual ? null : (
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="重新拉取订阅"
              title="重新拉取订阅"
              onClick={() => void handleRefresh()}
              disabled={isBusy || isLoading}
            >
              <RefreshCw className={cn("size-4", isRefreshing && "animate-spin")} />
            </Button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-border">
        {isLoading && !detail ? (
          <EmptyState icon={<LoaderCircle className="animate-spin" />} title="正在加载节点" className="py-12" />
        ) : loadError && !detail ? (
          <EmptyState
            icon={<SearchX />}
            title="加载节点失败"
            description={loadError}
            className="py-12"
            action={
              <Button variant="outline" size="sm" onClick={() => void load()}>
                <RefreshCw className="size-4" />
                重试
              </Button>
            }
          />
        ) : nodes.length === 0 ? (
          <EmptyState
            icon={<Rss />}
            title={isManual ? "还没有手动添加的节点" : "订阅里还没有节点"}
            description={
              isManual
                ? "在「批量添加」里粘贴分享链接或 Base64 订阅内容后会出现在这里。"
                : "拉取失败或订阅为空，确认地址和 User-Agent 后重新拉取。"
            }
            className="py-12"
          />
        ) : visible.length === 0 ? (
          <EmptyState icon={<SearchX />} title="没有匹配的节点" description="换个关键词或筛选条件试试。" className="py-12" />
        ) : (
          <div className="max-h-[min(52vh,520px)] overflow-auto">
            <div role="table" aria-label="订阅节点" className="min-w-[640px] text-[13px]">
              <div
                role="row"
                className="sticky top-0 z-10 grid grid-cols-[36px_minmax(0,1.6fr)_92px_minmax(0,1.3fr)_minmax(0,1fr)] items-center border-b border-border bg-popover px-2 text-xs font-medium text-muted-foreground [&>div]:px-1.5 [&>div]:py-2"
              >
                <div role="columnheader" aria-label="勾选" />
                <div role="columnheader">名称</div>
                <div role="columnheader">类型</div>
                <div role="columnheader">服务器</div>
                <div role="columnheader">状态</div>
              </div>
              {visible.map((node) => {
                const selectable = isNodeSelectable(node);
                const checked = node.imported || selected.has(node.key);
                return (
                  <div
                    key={node.key}
                    role="row"
                    aria-disabled={!selectable || undefined}
                    onClick={() => toggle(node)}
                    className={cn(
                      "grid grid-cols-[36px_minmax(0,1.6fr)_92px_minmax(0,1.3fr)_minmax(0,1fr)] items-center border-b border-border/70 px-2 transition-colors last:border-b-0 [&>div]:px-1.5 [&>div]:py-2",
                      selectable ? "cursor-pointer hover:bg-accent/60" : "cursor-default",
                      !node.available && !node.imported && "text-muted-foreground",
                      selected.has(node.key) && "bg-primary/5",
                    )}
                  >
                    {/* 复选框自己处理点击，别再冒泡到整行的切换上 */}
                    <div role="cell" className="flex" onClick={(event) => event.stopPropagation()}>
                      <Checkbox
                        checked={checked}
                        disabled={!selectable || isBusy}
                        onCheckedChange={(next) => toggle(node, next === true)}
                        aria-label={`选择 ${node.name}`}
                      />
                    </div>
                    <div role="cell" className="truncate text-foreground/90" title={node.name}>
                      {node.name}
                    </div>
                    <div role="cell">
                      <span className="rounded-md border border-border bg-field px-1.5 py-0.5 font-mono text-[11px] text-foreground/80">
                        {node.type}
                      </span>
                    </div>
                    <div role="cell" className="truncate font-mono text-xs text-foreground/70" title={`${node.server}:${node.port}`}>
                      {node.server}:{node.port}
                    </div>
                    <div role="cell" className="min-w-0">
                      <NodeStatus node={node} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {summary ? (
        <div className="space-y-2 rounded-xl border border-border bg-field/50 px-3.5 py-3 text-xs">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-foreground/80">
            <span>
              新增 <span className="font-semibold text-success tabular-nums">{summary.added}</span>
            </span>
            <span>
              跳过 <span className="font-semibold tabular-nums">{summary.skipped.length}</span>
            </span>
            {summary.assigned > 0 ? (
              <span>
                分配账号 <span className="font-semibold tabular-nums">{summary.assigned}</span>
              </span>
            ) : null}
          </div>
          {summary.skipped.length > 0 ? (
            <ul className="max-h-28 space-y-1 overflow-y-auto">
              {summary.skipped.map((item, index) => (
                <li key={`${item.key}-${index}`} className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
                  <span className="shrink-0 break-all text-foreground/80 sm:max-w-[55%]">{item.key}</span>
                  <span className="break-all text-muted-foreground">{item.reason}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {summary.coreApply?.ok === false ? (
            <p className="rounded-lg bg-warning/12 px-2.5 py-1.5 leading-5 break-all text-warning">
              节点已加入代理池，但 mihomo 内核配置没有生效：{summary.coreApply.error || "未知错误"}。确认 proxy-core 已启动后，在「mihomo 内核」里点「重新应用」。
            </p>
          ) : null}
        </div>
      ) : null}

      <DialogFooter className="items-center sm:justify-between">
        <span className="text-xs text-muted-foreground tabular-nums">
          {detail ? `共 ${nodes.length} 个节点，已导入 ${nodes.filter((node) => node.imported).length} 个` : null}
          {selected.size > 0 ? `，已选 ${selected.size} 个` : null}
        </span>
        <div className="flex flex-col-reverse gap-2 sm:flex-row">
          <Button variant="secondary" onClick={onClose} disabled={isBusy}>
            {summary ? "关闭" : "取消"}
          </Button>
          <Button onClick={() => void handleImport()} disabled={isBusy || selected.size === 0}>
            {isImporting ? <LoaderCircle className="size-4 animate-spin" /> : <Download className="size-4" />}
            导入{selected.size > 0 ? ` ${selected.size} 个` : ""}
          </Button>
        </div>
      </DialogFooter>
    </DialogContent>
  );
}
