"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, Plus, Save, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createManagedUser, deleteManagedUser, fetchManagedUsers, updateManagedUser, type AuthRole, type ManagedUser } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

export default function AdminUsersPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  const didLoadRef = useRef(false);
  const [items, setItems] = useState<ManagedUser[]>([]);
  const [query, setQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [pendingId, setPendingId] = useState("");
  const [form, setForm] = useState({
    email: "",
    password: "",
    role: "user" as AuthRole,
    image_quota: "0",
    image_concurrency: "1",
  });

  const filteredItems = useMemo(() => items, [items]);

  const load = async (nextQuery = query) => {
    setIsLoading(true);
    try {
      const data = await fetchManagedUsers(nextQuery);
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载用户失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    void load("");
  }, []);

  const handleCreate = async () => {
    if (!form.email.trim() || !form.password) {
      toast.error("请输入邮箱和密码");
      return;
    }
    setIsCreating(true);
    try {
      const data = await createManagedUser({
        email: form.email.trim().toLowerCase(),
        password: form.password,
        role: form.role,
        enabled: true,
        image_quota: Number(form.image_quota) || 0,
        image_concurrency: Number(form.image_concurrency) || 1,
      });
      setItems(data.items);
      setForm({ email: "", password: "", role: "user", image_quota: "0", image_concurrency: "1" });
      toast.success("用户已创建");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建用户失败");
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggle = async (item: ManagedUser) => {
    setPendingId(item.id);
    try {
      const data = await updateManagedUser(item.id, { enabled: !item.enabled });
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "更新用户失败");
    } finally {
      setPendingId("");
    }
  };

  const handleQuotaSave = async (item: ManagedUser, quota: string, concurrency: string) => {
    setPendingId(item.id);
    try {
      const data = await updateManagedUser(item.id, {
        image_quota: Number(quota) || 0,
        image_concurrency: Number(concurrency) || 1,
      });
      setItems(data.items);
      toast.success("用户额度已更新");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存额度失败");
    } finally {
      setPendingId("");
    }
  };

  const handleDelete = async (item: ManagedUser) => {
    if (!window.confirm(`确认删除 ${item.email} 吗？`)) return;
    setPendingId(item.id);
    try {
      const data = await deleteManagedUser(item.id);
      setItems(data.items);
      toast.success("用户已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除用户失败");
    } finally {
      setPendingId("");
    }
  };

  if (isCheckingAuth || !session || session.role !== "admin") {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <LoaderCircle className="size-5 animate-spin text-stone-400" />
      </div>
    );
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Users</div>
          <h1 className="text-2xl font-semibold tracking-tight">用户管理</h1>
        </div>
        <div className="flex gap-2">
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索邮箱" className="h-10 w-64 rounded-xl border-stone-200 bg-white" />
          <Button variant="outline" className="h-10 rounded-xl border-stone-200 bg-white" onClick={() => void load(query)}>
            搜索
          </Button>
        </div>
      </div>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="grid gap-3 p-5 lg:grid-cols-[1.5fr_1fr_0.6fr_0.6fr_auto]">
          <Input value={form.email} onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))} placeholder="邮箱" className="h-10 rounded-xl border-stone-200 bg-white" />
          <Input value={form.password} type="password" onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} placeholder="密码" className="h-10 rounded-xl border-stone-200 bg-white" />
          <select value={form.role} onChange={(event) => setForm((current) => ({ ...current, role: event.target.value as AuthRole }))} className="h-10 rounded-xl border border-stone-200 bg-white px-3 text-sm">
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
          <Input value={form.image_quota} onChange={(event) => setForm((current) => ({ ...current, image_quota: event.target.value }))} placeholder="图片额度" className="h-10 rounded-xl border-stone-200 bg-white" />
          <Button className="h-10 rounded-xl bg-stone-950 text-white hover:bg-stone-800" disabled={isCreating} onClick={() => void handleCreate()}>
            {isCreating ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
            创建
          </Button>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-3 p-5">
          {isLoading ? (
            <div className="flex justify-center py-10">
              <LoaderCircle className="size-5 animate-spin text-stone-400" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="rounded-xl bg-stone-50 px-6 py-10 text-center text-sm text-stone-500">
              <Users className="mx-auto mb-2 size-6 text-stone-300" />
              暂无用户
            </div>
          ) : (
            filteredItems.map((item) => (
              <UserRow
                key={item.id}
                item={item}
                isPending={pendingId === item.id}
                onToggle={() => void handleToggle(item)}
                onDelete={() => void handleDelete(item)}
                onSave={(quota, concurrency) => void handleQuotaSave(item, quota, concurrency)}
              />
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function UserRow({
  item,
  isPending,
  onToggle,
  onDelete,
  onSave,
}: {
  item: ManagedUser;
  isPending: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onSave: (quota: string, concurrency: string) => void;
}) {
  const [quota, setQuota] = useState(String(item.image_quota));
  const [concurrency, setConcurrency] = useState(String(item.image_concurrency));

  useEffect(() => {
    setQuota(String(item.image_quota));
    setConcurrency(String(item.image_concurrency));
  }, [item.image_quota, item.image_concurrency]);

  return (
    <div className="grid gap-3 rounded-2xl border border-stone-200 bg-white p-4 xl:grid-cols-[minmax(0,1.5fr)_0.8fr_0.8fr_auto] xl:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <div className="truncate text-sm font-semibold text-stone-900">{item.email}</div>
          <Badge variant={item.role === "admin" ? "default" : "secondary"} className="rounded-md">
            {item.role === "admin" ? "管理员" : "普通用户"}
          </Badge>
          <Badge variant={item.enabled ? "success" : "secondary"} className="rounded-md">
            {item.enabled ? "启用" : "禁用"}
          </Badge>
        </div>
        <div className="mt-1 text-xs text-stone-500">创建 {formatDate(item.created_at)}，最近登录 {formatDate(item.last_login_at)}</div>
      </div>
      <Input value={quota} onChange={(event) => setQuota(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" />
      <Input value={concurrency} onChange={(event) => setConcurrency(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" />
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" className="h-9 rounded-xl border-stone-200 bg-white" disabled={isPending} onClick={() => onSave(quota, concurrency)}>
          {isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
          保存
        </Button>
        <Button variant="outline" className="h-9 rounded-xl border-stone-200 bg-white" disabled={isPending} onClick={onToggle}>
          {item.enabled ? "禁用" : "启用"}
        </Button>
        <Button variant="outline" className="h-9 rounded-xl border-rose-200 bg-white text-rose-600 hover:bg-rose-50" disabled={isPending} onClick={onDelete}>
          <Trash2 className="size-4" />
        </Button>
      </div>
    </div>
  );
}
