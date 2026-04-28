"use client";

import { useEffect, useRef, useState } from "react";
import { Gift, LoaderCircle, TicketCheck } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchMe, fetchRedeemHistory, redeemCode, type ManagedUser, type RedeemCode } from "@/lib/api";
import { useAuthGuard } from "@/lib/use-auth-guard";

function typeLabel(type: string) {
  if (type === "image_quota") return "图片额度";
  if (type === "concurrency") return "图片并发";
  return "邀请码";
}

export default function RedeemPage() {
  const { isCheckingAuth, session } = useAuthGuard();
  const didLoadRef = useRef(false);
  const [user, setUser] = useState<ManagedUser | null>(null);
  const [items, setItems] = useState<RedeemCode[]>([]);
  const [code, setCode] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = async () => {
    setIsLoading(true);
    try {
      const [me, history] = await Promise.all([fetchMe(), fetchRedeemHistory()]);
      setUser(me.user);
      setItems(history.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载兑换信息失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    void load();
  }, []);

  const handleRedeem = async () => {
    const normalizedCode = code.trim();
    if (!normalizedCode) {
      toast.error("请输入兑换码");
      return;
    }
    setIsSubmitting(true);
    try {
      const data = await redeemCode(normalizedCode);
      setUser(data.user);
      setCode("");
      const history = await fetchRedeemHistory();
      setItems(history.items);
      toast.success("兑换成功");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "兑换失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isCheckingAuth || !session) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <LoaderCircle className="size-5 animate-spin text-stone-400" />
      </div>
    );
  }

  return (
    <section className="mx-auto grid w-full max-w-[980px] gap-5">
      <div className="space-y-1">
        <div className="text-xs font-semibold tracking-[0.18em] text-stone-500 uppercase">Redeem</div>
        <h1 className="text-2xl font-semibold tracking-tight">兑换中心</h1>
      </div>

      <Card className="overflow-hidden rounded-[30px] border-white/80 bg-white/90 shadow-sm">
        <CardContent className="grid gap-6 p-6 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[24px] bg-stone-950 p-6 text-white">
            <Gift className="size-8 text-emerald-200" />
            <div className="mt-8 text-sm text-stone-300">当前图片额度</div>
            <div className="mt-1 text-5xl font-semibold tracking-tight">{user?.role === "admin" ? "不限" : user?.image_quota ?? "—"}</div>
            <div className="mt-5 rounded-2xl bg-white/10 px-4 py-3 text-sm text-stone-200">
              图片并发：{user?.role === "admin" ? "不限" : user?.image_concurrency ?? "—"}
            </div>
          </div>
          <div className="space-y-4 self-center">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-stone-950">输入兑换码</h2>
              <p className="mt-1 text-sm text-stone-500">支持图片额度码和并发码；邀请码仅注册时使用。</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
              <Input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void handleRedeem();
                }}
                placeholder="IMG-..."
                className="h-12 rounded-2xl border-stone-200 bg-white font-mono"
              />
              <Button className="h-12 rounded-2xl bg-stone-950 px-6 text-white hover:bg-stone-800" disabled={isSubmitting} onClick={() => void handleRedeem()}>
                {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : <TicketCheck className="size-4" />}
                兑换
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="space-y-3 p-5">
          <h2 className="text-lg font-semibold tracking-tight">兑换记录</h2>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <LoaderCircle className="size-5 animate-spin text-stone-400" />
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-xl bg-stone-50 px-6 py-8 text-center text-sm text-stone-500">暂无兑换记录</div>
          ) : (
            items.map((item) => (
              <div key={item.id} className="flex flex-col gap-2 rounded-2xl border border-stone-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="font-mono text-sm text-stone-900">{item.code_preview}</div>
                  <div className="mt-1 text-xs text-stone-500">{item.used_at || item.created_at}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="rounded-md">
                    {typeLabel(item.type)}
                  </Badge>
                  <span className="text-sm font-semibold text-stone-800">+{item.value}</span>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </section>
  );
}
