"use client";

import { useEffect, useRef, useState } from "react";
import { Ban, CheckCircle2, Copy, KeyRound, LoaderCircle, Pencil, Plus, Trash2 } from "lucide-react";
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
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function UserKeysCard() {
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
      toast.error(error instanceof Error ? error.message : "Failed to load user keys");
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
      toast.success("User key created");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create user key");
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
      toast.success(item.enabled ? "User key disabled" : "User key enabled");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update user key");
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
      toast.success("User key deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete user key");
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
      toast.success(trimmedKey ? "User key updated" : "User name updated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update user key");
    } finally {
      setItemPending(item.id, false);
    }
  };

  const handleCopy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("Copied to clipboard");
    } catch {
      toast.error("Copy failed, please copy manually");
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
                <h2 className="text-lg font-semibold tracking-tight">User Key Management</h2>
                <p className="text-sm text-stone-500">Create dedicated keys for regular users. Regular users can only access the image page, cannot view settings or account pool.</p>
              </div>
            </div>
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" onClick={() => setIsDialogOpen(true)}>
              <Plus className="size-4" />
              Create User Key
            </Button>
          </div>

          {revealedKey ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-900">
              <div className="font-medium">The new key is shown only once, please save immediately:</div>
              <div className="mt-3 flex flex-col gap-3 rounded-lg border border-emerald-200 bg-white/80 p-3 md:flex-row md:items-center md:justify-between">
                <code className="break-all font-mono text-[13px]">{revealedKey}</code>
                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-xl border-emerald-200 bg-white px-4 text-emerald-700"
                  onClick={() => void handleCopy(revealedKey)}
                >
                  <Copy className="size-4" />
                  Copy
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
              No regular user keys yet. Click the button in the upper right to create and distribute to others.
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
                          {item.enabled ? "Enabled" : "Disabled"}
                        </Badge>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-500">
                        <span>Created {formatDateTime(item.created_at)}</span>
                        <span>Last used {formatDateTime(item.last_used_at)}</span>
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
                        Edit
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
                        {item.enabled ? "Disable" : "Enable"}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-xl border-rose-200 bg-white px-4 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                        onClick={() => setDeletingItem(item)}
                        disabled={isPending}
                      >
                        {isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                        Delete
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
            <DialogTitle>Create User Key</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              Optionally fill in a remark name to distinguish between different users. After creation, a raw key will be generated that can only be viewed once.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-sm font-medium text-stone-700">Name (optional)</label>
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g., Designer A, Operations Temp Account"
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
              Cancel
            </Button>
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleCreate()}
              disabled={isCreating}
            >
              {isCreating ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deletingItem)} onOpenChange={(open) => (!open ? setDeletingItem(null) : null)}>
        <DialogContent className="rounded-2xl p-6">
          <DialogHeader className="gap-2">
            <DialogTitle>Delete User Key</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              Confirm deleting user key "{deletingItem?.name}"? After deletion, this key will no longer be able to call the API.
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
              Cancel
            </Button>
            <Button
              type="button"
              className="h-10 rounded-xl bg-rose-600 px-5 text-white hover:bg-rose-700"
              onClick={() => void handleDelete()}
              disabled={deletingItem ? pendingIds.has(deletingItem.id) : false}
            >
              {deletingItem && pendingIds.has(deletingItem.id) ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
              Delete
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
            <DialogTitle>Edit User Key</DialogTitle>
            <DialogDescription className="text-sm leading-6">
              You can modify the remark name. To replace the dedicated key, simply fill in the new raw key. Leave empty to keep the current key unchanged.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Name</label>
              <Input
                value={editName}
                onChange={(event) => setEditName(event.target.value)}
                placeholder="e.g., Designer A, Operations Temp Account"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">New Dedicated Key (optional)</label>
              <Input
                value={editKey}
                onChange={(event) => setEditKey(event.target.value)}
                placeholder="e.g., sk-your-custom-user-key"
                className="h-11 rounded-xl border-stone-200 bg-white font-mono"
              />
              <p className="text-xs leading-5 text-stone-500">
                After saving, the old key will be invalidated immediately and the new key will take effect. The system only stores hashes and will not display the current key.
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
              Cancel
            </Button>
            <Button
              type="button"
              className="h-10 rounded-xl bg-stone-950 px-5 text-white hover:bg-stone-800"
              onClick={() => void handleEdit()}
              disabled={editingItem ? pendingIds.has(editingItem.id) : false}
            >
              {editingItem && pendingIds.has(editingItem.id) ? <LoaderCircle className="size-4 animate-spin" /> : <Pencil className="size-4" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
