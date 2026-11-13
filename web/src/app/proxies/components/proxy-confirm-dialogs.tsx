"use client";

import { LoaderCircle, Power, PowerOff, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { ProxyPoolItem, ProxyPoolSummary, ProxySubscriptionSummary } from "@/lib/api";
import { proxyPoolLabel, subscriptionLabel } from "@/lib/proxy-pool";

type ProxyDeleteDialogProps = {
  item: ProxyPoolItem | null;
  /** 池里除它以外是否还有代理；没有时绑定的账号只能解除绑定 */
  hasOtherProxies: boolean;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ProxyDeleteDialog({ item, hasOtherProxies, isDeleting, onCancel, onConfirm }: ProxyDeleteDialogProps) {
  const boundCount = item?.bound_count ?? 0;
  return (
    <Dialog open={Boolean(item)} onOpenChange={(open) => (!open && !isDeleting ? onCancel() : null)}>
      <DialogContent showCloseButton={false} className="max-w-md">
        <DialogHeader className="gap-2">
          <DialogTitle>删除代理</DialogTitle>
          <DialogDescription className="text-sm leading-6">
            确认删除代理「{item ? proxyPoolLabel(item) : ""}」吗？
            {boundCount > 0
              ? hasOtherProxies
                ? `删除后将把 ${boundCount} 个账号改绑到其他代理。`
                : `池里没有其他代理可改绑，删除后这 ${boundCount} 个账号会解除绑定。`
              : "当前没有账号绑定这个代理。"}
            {item?.subscription_id ? "之后可以在订阅的「选择节点」里重新导入。" : null}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" onClick={onCancel} disabled={isDeleting}>
            取消
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={isDeleting}>
            {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
            删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type ProxySubscriptionDeleteDialogProps = {
  item: ProxySubscriptionSummary | null;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

/** 删除订阅会连带删除它导入的代理，名下账号改绑到其他代理 */
export function ProxySubscriptionDeleteDialog({ item, isDeleting, onCancel, onConfirm }: ProxySubscriptionDeleteDialogProps) {
  const importedCount = item?.imported_count ?? 0;
  return (
    <Dialog open={Boolean(item)} onOpenChange={(open) => (!open && !isDeleting ? onCancel() : null)}>
      <DialogContent showCloseButton={false} className="max-w-md">
        <DialogHeader className="gap-2">
          <DialogTitle>删除订阅</DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-2 text-sm leading-6">
              <p>确认删除订阅「{item ? subscriptionLabel(item) : ""}」吗？</p>
              {importedCount > 0 ? (
                <p className="rounded-xl bg-warning/12 px-3 py-2 text-warning">
                  将同时删除该订阅导入的 {importedCount} 个代理，名下账号会改绑到其他代理。
                </p>
              ) : (
                <p>该订阅还没有导入代理，删除不影响代理池。</p>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" onClick={onCancel} disabled={isDeleting}>
            取消
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={isDeleting}>
            {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
            删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type ProxyPoolToggleDialogProps = {
  /** 目标状态：true 表示准备开启，false 表示准备关闭，null 表示对话框关闭 */
  target: boolean | null;
  summary: ProxyPoolSummary | null;
  isSaving: boolean;
  onCancel: () => void;
  onConfirm: (next: boolean) => void;
};

export function ProxyPoolToggleDialog({ target, summary, isSaving, onCancel, onConfirm }: ProxyPoolToggleDialogProps) {
  const enabling = target === true;
  const noUsableProxy = (summary?.enabled ?? 0) === 0;
  return (
    <Dialog open={target !== null} onOpenChange={(open) => (!open && !isSaving ? onCancel() : null)}>
      <DialogContent showCloseButton={false} className="max-w-md">
        <DialogHeader className="gap-2">
          <DialogTitle>{enabling ? "开启代理池" : "关闭代理池"}</DialogTitle>
          <DialogDescription asChild>
            <div className="space-y-2 text-sm leading-6">
              {enabling ? (
                <>
                  <p>开启后，账号上原来手填的代理会迁移进池并改为绑定；其余未绑定的账号按绑定数最少的原则均分到可用代理。</p>
                  <p>已绑定的账号之后不会自动迁移，建议先录入全部代理再开启。</p>
                  {noUsableProxy ? (
                    <p className="rounded-xl bg-warning/12 px-3 py-2 text-warning">
                      池里还没有启用的代理，上游请求会继续走原有的代理设置，直到添加代理。
                    </p>
                  ) : null}
                </>
              ) : (
                <p>关闭后上游请求回到原有的代理设置。账号的绑定会保留，重新开启后继续生效。</p>
              )}
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" onClick={onCancel} disabled={isSaving}>
            取消
          </Button>
          <Button
            variant={enabling ? "default" : "destructive"}
            onClick={() => target !== null && onConfirm(target)}
            disabled={isSaving}
          >
            {isSaving ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : enabling ? (
              <Power className="size-4" />
            ) : (
              <PowerOff className="size-4" />
            )}
            {enabling ? "开启" : "关闭"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
