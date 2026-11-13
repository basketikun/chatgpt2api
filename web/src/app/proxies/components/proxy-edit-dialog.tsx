"use client";

import { useState } from "react";
import { LoaderCircle, Save } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
import { updateProxyPoolEntry, type ProxyPoolItem, type ProxyPoolPayload } from "@/lib/api";

type ProxyEditDialogProps = {
  /** 打开时的快照；轮询刷新不会改动表单 */
  item: ProxyPoolItem | null;
  onClose: () => void;
  onSaved: (data: ProxyPoolPayload) => void;
};

/** 用 key 让每次打开都按当前条目重新初始化表单 */
export function ProxyEditDialog({ item, onClose, onSaved }: ProxyEditDialogProps) {
  return (
    <Dialog open={Boolean(item)} onOpenChange={(open) => (!open ? onClose() : null)}>
      {item ? <ProxyEditForm key={item.id} item={item} onClose={onClose} onSaved={onSaved} /> : null}
    </Dialog>
  );
}

function ProxyEditForm({ item, onClose, onSaved }: { item: ProxyPoolItem; onClose: () => void; onSaved: (data: ProxyPoolPayload) => void }) {
  const [name, setName] = useState(item.name ?? "");
  const [url, setUrl] = useState(item.url ?? "");
  const [enabled, setEnabled] = useState(item.enabled);
  const [isSaving, setIsSaving] = useState(false);
  // 订阅导入的代理地址由订阅维护（后端拒绝修改），只能改名称和启用状态
  const fromSubscription = Boolean(item.subscription_id);

  const handleSave = async () => {
    const nextName = name.trim();
    const nextUrl = url.trim();
    if (!nextUrl) {
      toast.error("代理地址不能为空");
      return;
    }
    const updates: { name?: string; url?: string; enabled?: boolean } = {};
    if (nextName !== (item.name ?? "").trim()) updates.name = nextName;
    if (!fromSubscription && nextUrl !== (item.url ?? "").trim()) updates.url = nextUrl;
    if (enabled !== item.enabled) updates.enabled = enabled;
    if (Object.keys(updates).length === 0) {
      onClose();
      return;
    }
    setIsSaving(true);
    try {
      const data = await updateProxyPoolEntry(item.id, updates);
      onSaved(data);
      toast.success("代理已更新");
      onClose();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "更新代理失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <DialogContent
      showCloseButton={false}
      className="max-w-lg"
      onInteractOutside={(event) => (isSaving ? event.preventDefault() : undefined)}
      onEscapeKeyDown={(event) => (isSaving ? event.preventDefault() : undefined)}
    >
      <DialogHeader className="gap-2">
        <DialogTitle>编辑代理</DialogTitle>
        <DialogDescription className="text-sm leading-6">
          {fromSubscription
            ? `这个代理从订阅${item.subscription_name?.trim() ? `「${item.subscription_name.trim()}」` : ""}导入，地址由订阅维护，这里只能修改名称和启用状态。`
            : "修改地址（例如更换密码）不会改变账号绑定，但会重置这个代理的健康状态。"}
        </DialogDescription>
      </DialogHeader>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          void handleSave();
        }}
      >
        <Field>
          <FieldLabel htmlFor="proxy-pool-edit-name">名称</FieldLabel>
          <Input
            id="proxy-pool-edit-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="可选，例如：美国住宅 01"
            disabled={isSaving}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="proxy-pool-edit-url">代理地址</FieldLabel>
          <Input
            id="proxy-pool-edit-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="http://user:pass@1.2.3.4:8080"
            spellCheck={false}
            autoComplete="off"
            className="font-mono text-xs"
            disabled={isSaving || fromSubscription}
            readOnly={fromSubscription}
            aria-describedby="proxy-pool-edit-url-hint"
          />
          <p id="proxy-pool-edit-url-hint" className="text-xs leading-5 text-muted-foreground">
            {fromSubscription
              ? item.via_core
                ? "订阅导入的地址由订阅维护，不能手动修改；这是 mihomo 内核为该节点分配的本地端口。"
                : "订阅导入的地址由订阅维护，不能手动修改；要换节点请在订阅里重新选择。"
              : "完整地址包含凭据，仅在这里显示。"}
          </p>
        </Field>
        <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-field/50 px-3.5 py-2.5">
          <div className="min-w-0 space-y-0.5">
            <div className="text-[13px] font-medium text-foreground/80">启用</div>
            <div className="text-xs leading-5 text-muted-foreground">禁用后不再分配新账号，已绑定的账号会临时借用其他代理。</div>
          </div>
          <Switch checked={enabled} onCheckedChange={setEnabled} disabled={isSaving} aria-label="启用代理" />
        </div>
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={onClose} disabled={isSaving}>
            取消
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            保存
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  );
}
