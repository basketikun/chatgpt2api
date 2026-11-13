"use client";

import { useState } from "react";
import { ChevronDown, LoaderCircle, Plus, Save } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  createProxySubscription,
  updateProxySubscription,
  type ProxySubscriptionDetail,
  type ProxySubscriptionInput,
  type ProxySubscriptionRefreshResult,
  type ProxySubscriptionsPayload,
  type ProxySubscriptionSummary,
} from "@/lib/api";
import {
  DEFAULT_SUBSCRIPTION_REFRESH_HOURS,
  DEFAULT_SUBSCRIPTION_USER_AGENT,
  isManualSubscription,
  MANUAL_SUBSCRIPTION_NAME,
  MAX_SUBSCRIPTION_REFRESH_HOURS,
  parseRefreshHours,
} from "@/lib/proxy-pool";
import { cn } from "@/lib/utils";

export type ProxySubscriptionCreated = ProxySubscriptionsPayload & {
  item: ProxySubscriptionDetail;
  result: ProxySubscriptionRefreshResult;
};

type ProxySubscriptionFormDialogProps = {
  open: boolean;
  /** 编辑时打开那一刻的快照（轮询不会改动表单）；为空表示新建 */
  subscription: ProxySubscriptionSummary | null;
  onClose: () => void;
  onCreated: (data: ProxySubscriptionCreated) => void;
  onUpdated: (data: ProxySubscriptionsPayload, refetchNeeded: boolean) => void;
};

/** 新建 / 编辑订阅；用 key 让每次打开都按当前订阅重新初始化表单 */
export function ProxySubscriptionFormDialog({ open, subscription, onClose, onCreated, onUpdated }: ProxySubscriptionFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => (!next ? onClose() : null)}>
      {open ? (
        <ProxySubscriptionForm
          key={subscription?.id ?? "new"}
          subscription={subscription}
          onClose={onClose}
          onCreated={onCreated}
          onUpdated={onUpdated}
        />
      ) : null}
    </Dialog>
  );
}

function ProxySubscriptionForm({
  subscription,
  onClose,
  onCreated,
  onUpdated,
}: Omit<ProxySubscriptionFormDialogProps, "open">) {
  const isEdit = Boolean(subscription);
  // 「手动添加的节点」没有地址，也不能刷新：只能改名称
  const isManual = Boolean(subscription && isManualSubscription(subscription));
  const [name, setName] = useState(subscription?.name ?? "");
  const [url, setUrl] = useState(subscription?.url ?? "");
  const [hours, setHours] = useState(String(subscription?.refresh_interval_hours ?? DEFAULT_SUBSCRIPTION_REFRESH_HOURS));
  const [userAgent, setUserAgent] = useState(subscription?.user_agent || DEFAULT_SUBSCRIPTION_USER_AGENT);
  const [showAdvanced, setShowAdvanced] = useState(
    Boolean(subscription && subscription.user_agent && subscription.user_agent !== DEFAULT_SUBSCRIPTION_USER_AGENT),
  );
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async () => {
    const nextName = name.trim();
    if (subscription && isManual) {
      if (nextName === (subscription.name ?? "").trim()) {
        onClose();
        return;
      }
      setIsSaving(true);
      try {
        const data = await updateProxySubscription(subscription.id, { name: nextName });
        onUpdated({ items: data.items, core: data.core }, false);
        onClose();
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "更新订阅失败");
      } finally {
        setIsSaving(false);
      }
      return;
    }
    const nextUrl = url.trim();
    const nextUserAgent = userAgent.trim() || DEFAULT_SUBSCRIPTION_USER_AGENT;
    if (!/^https?:\/\//i.test(nextUrl)) {
      toast.error("订阅地址必须是 http(s) 链接");
      return;
    }
    const nextHours = parseRefreshHours(hours);
    if (nextHours === null) {
      toast.error(`自动刷新间隔需要是 0–${MAX_SUBSCRIPTION_REFRESH_HOURS} 之间的整数`);
      return;
    }

    setIsSaving(true);
    try {
      if (!subscription) {
        const data = await createProxySubscription({
          name: nextName,
          url: nextUrl,
          user_agent: nextUserAgent,
          refresh_interval_hours: nextHours,
        });
        onCreated(data);
        onClose();
        return;
      }
      const updates: Partial<ProxySubscriptionInput> = {};
      if (nextName !== (subscription.name ?? "").trim()) updates.name = nextName;
      if (nextUrl !== subscription.url) updates.url = nextUrl;
      if (nextUserAgent !== (subscription.user_agent || DEFAULT_SUBSCRIPTION_USER_AGENT)) updates.user_agent = nextUserAgent;
      if (nextHours !== subscription.refresh_interval_hours) updates.refresh_interval_hours = nextHours;
      if (Object.keys(updates).length === 0) {
        onClose();
        return;
      }
      const data = await updateProxySubscription(subscription.id, updates);
      onUpdated({ items: data.items, core: data.core }, updates.url !== undefined || updates.user_agent !== undefined);
      onClose();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : isEdit ? "更新订阅失败" : "添加订阅失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <DialogContent
      showCloseButton={false}
      className="w-[min(92vw,560px)]"
      onInteractOutside={(event) => (isSaving ? event.preventDefault() : undefined)}
      onEscapeKeyDown={(event) => (isSaving ? event.preventDefault() : undefined)}
    >
      <DialogHeader className="gap-2">
        <DialogTitle>{isEdit ? "编辑订阅" : "添加订阅"}</DialogTitle>
        <DialogDescription className="text-sm leading-6">
          {isManual
            ? "这里汇总了批量添加里粘贴的分享链接，没有订阅地址，也不会自动刷新，只能修改名称。"
            : isEdit
              ? "修改地址或 User-Agent 后点「刷新」拉取新节点；已导入的代理按节点名称对账，名称不变的条目和账号绑定保持不变。"
              : "支持 Clash（YAML）和 V2Ray（Base64 / 分享链接）订阅。添加后立即拉取一次，再勾选要导入代理池的节点。"}
        </DialogDescription>
      </DialogHeader>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSubmit();
        }}
      >
        <Field>
          <FieldLabel htmlFor="proxy-subscription-name">名称</FieldLabel>
          <Input
            id="proxy-subscription-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={isManual ? MANUAL_SUBSCRIPTION_NAME : "可选，例如：机场 A"}
            maxLength={64}
            disabled={isSaving}
            autoFocus={isManual}
          />
        </Field>
        {isManual ? null : (
          <>
            <Field>
              <FieldLabel htmlFor="proxy-subscription-url">订阅地址</FieldLabel>
              <Input
                id="proxy-subscription-url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/api/v1/client/subscribe?token=..."
                spellCheck={false}
                autoComplete="off"
                className="font-mono text-xs"
                disabled={isSaving}
                autoFocus={!isEdit}
              />
              <p className="text-xs leading-5 text-muted-foreground">地址里通常带有 token，完整地址只在这里显示。</p>
            </Field>
            <Field>
              <FieldLabel htmlFor="proxy-subscription-hours">
                自动刷新间隔
                <span className="ml-1 font-normal text-muted-foreground">小时</span>
              </FieldLabel>
              <Input
                id="proxy-subscription-hours"
                type="number"
                inputMode="numeric"
                min={0}
                max={MAX_SUBSCRIPTION_REFRESH_HOURS}
                step={1}
                value={hours}
                onChange={(event) => setHours(event.target.value)}
                className="w-32 font-mono text-[13px] tabular-nums"
                disabled={isSaving}
              />
              <p className="text-xs leading-5 text-muted-foreground">
                0–{MAX_SUBSCRIPTION_REFRESH_HOURS}，0 表示只手动刷新。刷新时已导入的代理跟着节点更新；订阅里消失的节点会自动禁用，回来后自动恢复。
              </p>
            </Field>

            <div className="rounded-xl border border-border bg-field/50">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 rounded-xl px-3.5 py-2.5 text-left text-[13px] font-medium text-foreground/80 outline-none transition-colors hover:bg-accent/60 focus-visible:ring-4 focus-visible:ring-ring/40"
                aria-expanded={showAdvanced}
                aria-controls="proxy-subscription-advanced"
                onClick={() => setShowAdvanced((current) => !current)}
              >
                高级设置
                <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", showAdvanced && "rotate-180")} />
              </button>
              {showAdvanced ? (
                <div id="proxy-subscription-advanced" className="border-t border-border px-3.5 pt-3 pb-3.5">
                  <Field>
                    <FieldLabel htmlFor="proxy-subscription-ua">User-Agent</FieldLabel>
                    <Input
                      id="proxy-subscription-ua"
                      value={userAgent}
                      onChange={(event) => setUserAgent(event.target.value)}
                      placeholder={DEFAULT_SUBSCRIPTION_USER_AGENT}
                      spellCheck={false}
                      autoComplete="off"
                      className="font-mono text-xs"
                      disabled={isSaving}
                    />
                    <p className="text-xs leading-5 text-muted-foreground">
                      不少机场按 User-Agent 返回不同格式，默认 {DEFAULT_SUBSCRIPTION_USER_AGENT} 会拿到 Clash 配置；留空即用默认值。
                    </p>
                  </Field>
                </div>
              ) : null}
            </div>
          </>
        )}

        <DialogFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={isSaving}>
            取消
          </Button>
          <Button type="submit" disabled={isSaving || (!isManual && !url.trim())}>
            {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : isEdit ? <Save className="size-4" /> : <Plus className="size-4" />}
            {isEdit ? "保存" : isSaving ? "正在拉取…" : "添加并拉取"}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
