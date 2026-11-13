"use client";

import { useState } from "react";
import { toast } from "sonner";

import {
  deleteProxySubscription,
  refreshProxySubscription,
  updateProxyCore,
  type ProxyCoreStatus,
  type ProxyCoreUpdate,
  type ProxySubscriptionsPayload,
  type ProxySubscriptionSummary,
} from "@/lib/api";
import { describeRefreshResult, subscriptionLabel } from "@/lib/proxy-pool";

import { ProxySubscriptionDeleteDialog } from "./proxy-confirm-dialogs";
import { ProxyCoreCard } from "./proxy-core-card";
import { ProxySubscriptionFormDialog, type ProxySubscriptionCreated } from "./proxy-subscription-form-dialog";
import { ProxySubscriptionNodePicker, type NodePickerTarget } from "./proxy-subscription-node-picker";
import { ProxySubscriptionsCard } from "./proxy-subscriptions-card";

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

type FormState = { open: false } | { open: true; subscription: ProxySubscriptionSummary | null };

type ProxySubscriptionsPanelProps = {
  payload: ProxySubscriptionsPayload | null;
  isLoading: boolean;
  loadError: string;
  onReload: () => void;
  /** 订阅写操作的返回：更新订阅列表，并刷新代理池（导入 / 删除 / 刷新都会改动池里的条目） */
  onApply: (data: ProxySubscriptionsPayload) => void;
  /** 内核设置变化会让内核节点恢复 / 禁用，订阅列表和代理池都要重新拉取 */
  onCoreSaved: (core: ProxyCoreStatus) => void;
};

/** 「订阅」标签页：订阅列表 + 可选的 mihomo 内核，以及它们的对话框 */
export function ProxySubscriptionsPanel({ payload, isLoading, loadError, onReload, onApply, onCoreSaved }: ProxySubscriptionsPanelProps) {
  const [form, setForm] = useState<FormState>({ open: false });
  const [pickerTarget, setPickerTarget] = useState<NodePickerTarget | null>(null);
  const [deletingItem, setDeletingItem] = useState<ProxySubscriptionSummary | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [refreshingIds, setRefreshingIds] = useState<Set<string>>(() => new Set());
  const [isSavingCore, setIsSavingCore] = useState(false);

  const items = payload?.items ?? [];
  const core = payload?.core ?? null;
  const coreEnabled = Boolean(core?.settings.enabled);

  const setRefreshing = (id: string, active: boolean) =>
    setRefreshingIds((current) => {
      const next = new Set(current);
      if (active) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });

  const handleRefresh = async (item: Pick<ProxySubscriptionSummary, "id" | "name" | "masked_url">) => {
    const label = subscriptionLabel(item);
    setRefreshing(item.id, true);
    try {
      const data = await refreshProxySubscription(item.id);
      onApply(data);
      const result = data.result;
      if (!result.ok) {
        toast.error(`「${label}」${describeRefreshResult(result)}`);
        return;
      }
      toast.success(`「${label}」已刷新：${describeRefreshResult(result)}`);
      if (result.errors?.length) {
        toast.warning(`${result.errors.length} 个代理没能更新：${result.errors[0]}`);
      }
      if (result.core?.ok === false) {
        toast.warning(`mihomo 内核配置没有生效：${result.core.error || "未知错误"}`);
      }
    } catch (error) {
      toast.error(errorMessage(error, "刷新订阅失败"));
    } finally {
      setRefreshing(item.id, false);
    }
  };

  const handleCreated = (data: ProxySubscriptionCreated) => {
    onApply(data);
    if (data.result.ok) {
      toast.success(`订阅已添加：${describeRefreshResult(data.result)}，勾选要导入的节点`);
    } else {
      toast.error(`订阅已添加，但${describeRefreshResult(data.result)}`);
    }
    setPickerTarget({ id: data.item.id, initial: data.item });
  };

  const handleUpdated = (data: ProxySubscriptionsPayload, refetchNeeded: boolean) => {
    onApply(data);
    const subscription = form.open ? form.subscription : null;
    if (refetchNeeded && subscription) {
      toast.success("订阅已更新", {
        description: "地址或 User-Agent 已修改，重新拉取后节点才会更新。",
        action: { label: "立即刷新", onClick: () => void handleRefresh(subscription) },
      });
    } else {
      toast.success("订阅已更新");
    }
  };

  const handleDelete = async () => {
    if (!deletingItem) {
      return;
    }
    setIsDeleting(true);
    try {
      const data = await deleteProxySubscription(deletingItem.id);
      onApply(data);
      setDeletingItem(null);
      const parts = ["订阅已删除"];
      if (data.removed_proxies) parts.push(`同时删除 ${data.removed_proxies} 个代理`);
      if (data.reassigned) parts.push(`${data.reassigned} 个账号已改绑`);
      toast.success(parts.join("，"));
    } catch (error) {
      toast.error(errorMessage(error, "删除订阅失败"));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSaveCore = async (updates: ProxyCoreUpdate) => {
    const reapply = Object.keys(updates).length === 0;
    setIsSavingCore(true);
    try {
      const data = await updateProxyCore(updates);
      onCoreSaved(data);
      const { settings, status } = data;
      if (settings.enabled && !status.ok) {
        toast.warning(`${reapply ? "已重新应用" : "已保存"}，但无法连接 mihomo 内核：${status.error || "未知错误"}`);
      } else if (settings.enabled && status.last_apply?.ok === false) {
        toast.warning(`${reapply ? "重新应用" : "已保存，但应用"}内核配置失败：${status.last_apply.error || "未知错误"}`);
      } else {
        toast.success(reapply ? "已重新应用内核配置" : "内核设置已保存");
      }
      return true;
    } catch (error) {
      toast.error(errorMessage(error, "保存内核设置失败"));
      return false;
    } finally {
      setIsSavingCore(false);
    }
  };

  // 删除确认里的导入数跟着轮询更新
  const deletingLive = deletingItem ? (items.find((item) => item.id === deletingItem.id) ?? deletingItem) : null;

  return (
    <div className="space-y-3">
      <ProxySubscriptionsCard
        items={items}
        isLoading={isLoading && !payload}
        loadError={loadError}
        coreEnabled={coreEnabled}
        refreshingIds={refreshingIds}
        onAdd={() => setForm({ open: true, subscription: null })}
        onRetry={onReload}
        onPick={(item) => setPickerTarget({ id: item.id })}
        onRefresh={(item) => void handleRefresh(item)}
        onEdit={(item) => setForm({ open: true, subscription: item })}
        onDelete={setDeletingItem}
      />
      <ProxyCoreCard core={core} isSaving={isSavingCore} onSave={handleSaveCore} />

      <ProxySubscriptionFormDialog
        open={form.open}
        subscription={form.open ? form.subscription : null}
        onClose={() => setForm({ open: false })}
        onCreated={handleCreated}
        onUpdated={handleUpdated}
      />
      <ProxySubscriptionNodePicker target={pickerTarget} onClose={() => setPickerTarget(null)} onChanged={onApply} />
      <ProxySubscriptionDeleteDialog
        item={deletingLive}
        isDeleting={isDeleting}
        onCancel={() => setDeletingItem(null)}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}
