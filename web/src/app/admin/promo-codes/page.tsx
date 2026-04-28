"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircle, Percent, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createPromoCode, deletePromoCode, fetchPromoCodes, updatePromoCode, type PromoCode } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

export default function AdminPromoCodesPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  const didLoadRef = useRef(false);
  const [items, setItems] = useState<PromoCode[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [pendingId, setPendingId] = useState("");
  const [form, setForm] = useState({ code: "", image_quota: "5", max_uses: "100" });

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await fetchPromoCodes();
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载优惠码失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    void load();
  }, []);

  const handleCreate = async () => {
    if (!form.code.trim()) {
      toast.error("请输入优惠码");
      return;
    }
    setIsCreating(true);
    try {
      const data = await createPromoCode({
        code: form.code.trim(),
        image_quota: Number(form.image_quota) || 0,
        max_uses: Number(form.max_uses) || 1,
        enabled: true,
      });
      setItems(data.items);
      setForm({ code: "", image_quota: "5", max_uses: "100" });
      toast.success("优惠码已创建");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建优惠码失败");
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggle = async (item: PromoCode) => {
    setPendingId(item.id);
    try {
      const data = await updatePromoCode(item.id, { enabled: !item.enabled });
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "更新优惠码失败");
    } finally {
      setPendingId("");
    }
  };

  const handleDelete = async (item: PromoCode) => {
    if (!window.confirm(`确认删除 ${item.code_preview} 吗？`)) return;
    setPendingId(item.id);
    try {
      const data = await deletePromoCode(item.id);
      setItems(data.items);
      toast.success("优惠码已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除优惠码失败");
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
      <div>
        <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Promo Codes</div>
        <h1 className="text-2xl font-semibold tracking-tight">优惠码管理</h1>
      </div>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="grid gap-3 p-5 lg:grid-cols-[1fr_0.7fr_0.7fr_auto]">
          <Input value={form.code} onChange={(event) => setForm((current) => ({ ...current, code: event.target.value }))} placeholder="WELCOME" className="h-10 rounded-xl border-stone-200 bg-white font-mono" />
          <Input value={form.image_quota} onChange={(event) => setForm((current) => ({ ...current, image_quota: event.target.value }))} placeholder="赠送额度" className="h-10 rounded-xl border-stone-200 bg-white" />
          <Input value={form.max_uses} onChange={(event) => setForm((current) => ({ ...current, max_uses: event.target.value }))} placeholder="最大使用次数" className="h-10 rounded-xl border-stone-200 bg-white" />
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
          ) : items.length === 0 ? (
            <div className="rounded-xl bg-stone-50 px-6 py-10 text-center text-sm text-stone-500">
              <Percent className="mx-auto mb-2 size-6 text-stone-300" />
              暂无优惠码
            </div>
          ) : (
            items.map((item) => (
              <div key={item.id} className="flex flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm text-stone-900">{item.code_preview}</span>
                    <Badge variant={item.enabled ? "success" : "secondary"} className="rounded-md">
                      {item.enabled ? "启用" : "禁用"}
                    </Badge>
                  </div>
                  <div className="mt-1 text-xs text-stone-500">
                    注册赠送 +{item.image_quota}，已用 {item.used_count}/{item.max_uses}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" className="h-9 rounded-xl border-stone-200 bg-white" disabled={pendingId === item.id} onClick={() => void handleToggle(item)}>
                    {pendingId === item.id ? <LoaderCircle className="size-4 animate-spin" /> : null}
                    {item.enabled ? "禁用" : "启用"}
                  </Button>
                  <Button variant="outline" className="h-9 rounded-xl border-rose-200 bg-white text-rose-600 hover:bg-rose-50" disabled={pendingId === item.id} onClick={() => void handleDelete(item)}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}
