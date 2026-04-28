"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, LoaderCircle, Plus, Ticket, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { deleteRedeemCode, fetchRedeemCodes, generateRedeemCodes, updateRedeemCode, type RedeemCode, type RedeemCodeType } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

function typeLabel(type: RedeemCodeType) {
  if (type === "image_quota") return "图片额度";
  if (type === "concurrency") return "并发";
  return "邀请码";
}

export default function AdminRedeemCodesPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);
  const didLoadRef = useRef(false);
  const [items, setItems] = useState<RedeemCode[]>([]);
  const [generatedCodes, setGeneratedCodes] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [pendingId, setPendingId] = useState("");
  const [form, setForm] = useState({ type: "image_quota" as RedeemCodeType, value: "10", count: "1" });

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await fetchRedeemCodes();
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载兑换码失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    void load();
  }, []);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const data = await generateRedeemCodes({
        type: form.type,
        value: Number(form.value) || 0,
        count: Number(form.count) || 1,
      });
      setItems(data.items);
      setGeneratedCodes(data.codes.map((item) => String(item.code || "")).filter(Boolean));
      toast.success("兑换码已生成");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "生成兑换码失败");
    } finally {
      setIsGenerating(false);
    }
  };

  const copyCodes = async () => {
    try {
      await navigator.clipboard.writeText(generatedCodes.join("\n"));
      toast.success("已复制");
    } catch {
      toast.error("复制失败");
    }
  };

  const handleToggle = async (item: RedeemCode) => {
    setPendingId(item.id);
    try {
      const data = await updateRedeemCode(item.id, { enabled: !item.enabled });
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "更新兑换码失败");
    } finally {
      setPendingId("");
    }
  };

  const handleDelete = async (item: RedeemCode) => {
    if (!window.confirm(`确认删除 ${item.code_preview} 吗？`)) return;
    setPendingId(item.id);
    try {
      const data = await deleteRedeemCode(item.id);
      setItems(data.items);
      toast.success("兑换码已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除兑换码失败");
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
        <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Redeem Codes</div>
        <h1 className="text-2xl font-semibold tracking-tight">兑换码管理</h1>
      </div>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-4 p-5">
          <div className="grid gap-3 lg:grid-cols-[0.9fr_0.7fr_0.7fr_auto]">
            <select value={form.type} onChange={(event) => setForm((current) => ({ ...current, type: event.target.value as RedeemCodeType }))} className="h-10 rounded-xl border border-stone-200 bg-white px-3 text-sm">
              <option value="image_quota">图片额度</option>
              <option value="concurrency">图片并发</option>
              <option value="invitation">邀请码</option>
            </select>
            <Input value={form.value} onChange={(event) => setForm((current) => ({ ...current, value: event.target.value }))} disabled={form.type === "invitation"} placeholder="数值" className="h-10 rounded-xl border-stone-200 bg-white" />
            <Input value={form.count} onChange={(event) => setForm((current) => ({ ...current, count: event.target.value }))} placeholder="生成数量" className="h-10 rounded-xl border-stone-200 bg-white" />
            <Button className="h-10 rounded-xl bg-stone-950 text-white hover:bg-stone-800" disabled={isGenerating} onClick={() => void handleGenerate()}>
              {isGenerating ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}
              生成
            </Button>
          </div>
          {generatedCodes.length > 0 ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="font-medium">明文码仅展示一次</span>
                <Button variant="outline" className="h-8 rounded-xl border-emerald-200 bg-white text-emerald-800" onClick={() => void copyCodes()}>
                  <Copy className="size-4" />
                  复制全部
                </Button>
              </div>
              <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-white/80 p-3 font-mono text-xs">
                {generatedCodes.join("\n")}
              </pre>
            </div>
          ) : null}
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
              <Ticket className="mx-auto mb-2 size-6 text-stone-300" />
              暂无兑换码
            </div>
          ) : (
            items.map((item) => (
              <div key={item.id} className="flex flex-col gap-3 rounded-2xl border border-stone-200 bg-white p-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm text-stone-900">{item.code_preview}</span>
                    <Badge variant={item.enabled ? "success" : "secondary"} className="rounded-md">
                      {item.enabled ? "启用" : "禁用"}
                    </Badge>
                    {item.used ? (
                      <Badge variant="secondary" className="rounded-md">
                        已使用
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-1 text-xs text-stone-500">{typeLabel(item.type)} {item.type === "invitation" ? "" : `+${item.value}`}</div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" className="h-9 rounded-xl border-stone-200 bg-white" disabled={pendingId === item.id || item.used} onClick={() => void handleToggle(item)}>
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
