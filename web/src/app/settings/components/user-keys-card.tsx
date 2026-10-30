"use client";

import { useEffect, useRef, useState } from "react";
import { Ban, CheckCircle2, Copy, KeyRound, LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { createUserKey, deleteUserKey, fetchUserKeys, updateUserKey, type UserKey } from "@/lib/api";

function formatDateTime(value?: string | null) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function UserKeysCard() {
  const { t } = useTranslation("settings");
  const { t: tCommon } = useTranslation("common");
  const didLoadRef = useRef(false);
  const [items, setItems] = useState<UserKey[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set());
  const [revealedKey, setRevealedKey] = useState("");
  const [deletingItem, setDeletingItem] = useState<UserKey | null>(null);
  const [editingItem, setEditingItem] = useState<UserKey | null>(null);
  const [editName, setEditName] = useState("");
  const [editKey, setEditKey] = useState("");

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await fetchUserKeys();
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("userKeys.toasts.loadFailed"));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) {
      return;
    }
    didLoadRef.current = true;
    void load();
  }, []);

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const data = await createUserKey(name.trim());
      setItems(data.items);
      setRevealedKey(data.key);
      setName("");
      setIsDialogOpen(false);
      toast.success(t("userKeys.toasts.createSuccess"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("userKeys.toasts.createFailed"));
    } finally {
      setIsCreating(false);
    }
  };

  const setItemPending = (id: string, isPending: boolean) => {
    setPendingIds((current) => {
      const next = new Set(current);
      if (isPending) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const handleToggle = async (item: UserKey) => {
    setItemPending(item.id, true);
    try {
      const data = await updateUserKey(item.id, { enabled: !item.enabled });
      setItems(data.items);
      toast.success(item.enabled ? t("userKeys.toasts.disableSuccess") : t("userKeys.toasts.enableSuccess"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("userKeys.toasts.updateFailed"));
    } finally {
      setItemPending(item.id, false);
    }
  };

  const handleDelete = async () => {
    if (!deletingItem) {
      return;
    }
    const item = deletingItem;
    setItemPending(item.id, true);
    try {
      const data = await deleteUserKey(item.id);
      setItems(data.items);
      setDeletingItem(null);
      toast.success(t("userKeys.toasts.deleteSuccess"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("userKeys.toasts.deleteFailed"));
    } finally {
      setItemPending(item.id, false);
    }
  };

  const openEditDialog = (item: UserKey) => {
    setEditingItem(item);
    setEditName(item.name);
    setEditKey("");
  };

  const handleEdit = async () => {
    if (!editingItem) {
      return;
    }
    const item = editingItem;
    const trimmedName = editName.trim();
    const trimmedKey = editKey.trim();
    if (trimmedName === item.name && !trimmedKey) {
      setEditingItem(null);
      return;
    }
    setItemPending(item.id, true);
    try {
      const data = await updateUserKey(item.id, {
        ...(trimmedName !== item.name ? { name: trimmedName } : {}),
        ...(trimmedKey ? { key: trimmedKey } : {}),
      });
      setItems(data.items);
      setEditingItem(null);
      setEditKey("");
      toast.success(trimmedKey ? t("userKeys.toasts.editKeySuccess") : t("userKeys.toasts.editNameSuccess"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("userKeys.toasts.updateFailed"));
    } finally {
      setItemPending(item.id, false);
    }
  };

  const handleCopy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t("userKeys.toasts.copySuccess"));
    } catch {
      toast.error(t("userKeys.toasts.copyFailed"));
    }
  };

  return (
    <>
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-6 p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
                <KeyRound className="size-5 text-stone-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">{t("userKeys.header.title")}</h2>
                <p className="text-sm text-stone-500">{t("userKeys.header.description")}</p>
              </div>
            </div>
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" onClick={() => setIsDialogOpen(true)}>
              <Plus className="size-4" />
              {t("userKeys.header.createButton")}
            </Button>
          </div>

          {revealedKey ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-900">
              <div className="font-medium">{t("userKeys.revealedKey.title")}</div>
              <div className="mt-3 flex flex-col gap-3 rounded-lg border border-emerald-200 bg-white/80 p-3 md:flex-row md:items-center md:justify-between">
                <code className="break-all font-mono text-[13px]">{revealedKey}</code>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-emerald-200 bg-white px-4 text-emerald-700"
                  onClick={() => void handleCopy(revealedKey)}
                >
                  <Copy className="size-4" />
                  {t("userKeys.revealedKey.copyButton")}
                </Button>
              </div>
            </div>
          ) : null}

          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <LoaderCircle className="size-5 animate-spin text-stone-400" />
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-xl bg-stone-50 px-6 py-10 text-center text-sm text-stone-500">
              {t("userKeys.empty.description")}
            </div>
          ) : (
            <div className="space-y-3">
              {items.map((item) => {
                const isPending = pendingIds.has(item.id);
                return (
                  <div key={item.id} className="flex flex-col gap-3 rounded-xl border border-stone-200 bg-white px-4 py-4 md:flex-row md:items-center md:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="truncate text-sm font-medium text-stone-800">{item.name}</div>
                        <Badge variant={item.enabled ? "success" : "secondary"} className="rounded-md">
                          {item.enabled ? t("userKeys.item.badge.enabled") : t("userKeys.item.badge.disabled")}
                        </Badge>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
                        <span>{t("userKeys.item.createdAt", { date: formatDateTime(item.created_at) })}</span>
                        <span>{t("userKeys.item.lastUsedAt", { date: formatDateTime(item.last_used_at) })}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                        onClick={() => openEditDialog(item)}
                        disabled={isPending}
                      >
                        {isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Pencil className="size-4" />}
                        {t("userKeys.item.editButton")}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                        onClick={() => void handleToggle(item)}
                        disabled={isPending}
                      >
                        {isPending ? (
                          <LoaderCircle className="size-4 animate-spin" />
                        ) : item.enabled ? (
                          <Ban className="size-4" />
                        ) : (
                          <CheckCircle2 className="size-4" />
                        )}
                        {item.enabled ? t("userKeys.item.actions.disable") : t("userKeys.item.actions.enable")}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-rose-200 bg-white px-4 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                        onClick={() => setDeletingItem(item)}
                        disabled={isPending}
                      >
                        {isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                        {t("userKeys.item.deleteButton")}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{t("userKeys.createDialog.title")}</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {t("userKeys.createDialog.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">{t("userKeys.createDialog.nameLabel")}</label>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("userKeys.namePlaceholder")}
              className="h-11 rounded-xl border-stone-200 bg-white"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setIsDialogOpen(false)}
              disabled={isCreating}
            >
              {tCommon("canvasDialog.cancel")}
            </Button>
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleCreate()}
              disabled={isCreating}
            >
              {isCreating ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
              {t("userKeys.createDialog.createButton")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deletingItem)} onOpenChange={(open) => (!open ? setDeletingItem(null) : null)}>
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{t("userKeys.deleteDialog.title")}</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {t("userKeys.deleteDialog.description", { name: deletingItem?.name })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => setDeletingItem(null)}
              disabled={deletingItem ? pendingIds.has(deletingItem.id) : false}
            >
              {tCommon("canvasDialog.cancel")}
            </Button>
            <Button
              type="button"
              className="h-10 rounded-xl bg-rose-600 px-5 text-white hover:bg-rose-700"
              onClick={() => void handleDelete()}
              disabled={deletingItem ? pendingIds.has(deletingItem.id) : false}
            >
              {deletingItem && pendingIds.has(deletingItem.id) ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              {t("userKeys.deleteDialog.confirmButton")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(editingItem)}
        onOpenChange={(open) => {
          if (!open) {
            setEditingItem(null);
            setEditKey("");
          }
        }}
      >
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>{t("userKeys.editDialog.title")}</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              {t("userKeys.editDialog.description")}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">{t("userKeys.editDialog.nameLabel")}</label>
              <Input
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                placeholder={t("userKeys.namePlaceholder")}
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">{t("userKeys.editDialog.newKeyLabel")}</label>
              <Input
                value={editKey}
                onChange={(event) => setEditKey(event.target.value)}
                placeholder={t("userKeys.editDialog.newKeyPlaceholder")}
                className="h-11 rounded-xl border-stone-200 bg-white font-mono"
              />
              <p className="text-xs leading-5 text-stone-500">
                {t("userKeys.editDialog.newKeyHint")}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              className="h-10 rounded-xl bg-stone-100 px-5 text-stone-700 hover:bg-stone-200"
              onClick={() => {
                setEditingItem(null);
                setEditKey("");
              }}
              disabled={editingItem ? pendingIds.has(editingItem.id) : false}
            >
              {tCommon("canvasDialog.cancel")}
            </Button>
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleEdit()}
              disabled={editingItem ? pendingIds.has(editingItem.id) : false}
            >
              {editingItem && pendingIds.has(editingItem.id) ? <LoaderCircle className="size-4 animate-spin" /> : <Pencil className="size-4" />}
              {t("userKeys.editDialog.saveButton")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
