"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchSetupStatus, setupAdmin } from "@/lib/api";
import { getDefaultRouteForRole, setStoredAuthSession } from "@/store/auth";

export default function SetupPage() {
  const router = useRouter();
  const [isChecking, setIsChecking] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const status = await fetchSetupStatus();
        if (!active) return;
        if (!status.requires_setup) {
          router.replace("/login");
          return;
        }
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "读取安装状态失败");
      } finally {
        if (active) setIsChecking(false);
      }
    };
    void check();
    return () => {
      active = false;
    };
  }, [router]);

  const handleSubmit = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedEmail || !password) {
      toast.error("请输入管理员邮箱和密码");
      return;
    }
    setIsSubmitting(true);
    try {
      const data = await setupAdmin({ email: normalizedEmail, password });
      await setStoredAuthSession({
        key: data.token,
        role: data.role,
        subjectId: data.subject_id,
        name: data.name,
      });
      router.replace(getDefaultRouteForRole(data.role));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "创建管理员失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isChecking) {
    return (
      <div className="grid min-h-[calc(100vh-1rem)] place-items-center">
        <LoaderCircle className="size-5 animate-spin text-stone-400" />
      </div>
    );
  }

  return (
    <div className="grid min-h-[calc(100vh-1rem)] w-full place-items-center px-4 py-6">
      <Card className="w-full max-w-[560px] overflow-hidden rounded-[34px] border-white/80 bg-white/95 shadow-[0_30px_110px_rgba(28,25,23,0.13)]">
        <CardContent className="space-y-7 p-6 sm:p-8">
          <div className="space-y-4 text-center">
            <div className="mx-auto inline-flex size-16 items-center justify-center rounded-[24px] bg-emerald-950 text-white shadow-sm">
              <ShieldCheck className="size-6" />
            </div>
            <div className="space-y-2">
              <div className="text-xs font-semibold tracking-[0.28em] text-emerald-700 uppercase">First Run</div>
              <h1 className="text-3xl font-semibold tracking-tight text-stone-950">创建首个管理员</h1>
              <p className="text-sm leading-6 text-stone-500">
                系统检测到还没有管理员账号。完成后旧密钥登录将不再使用。
              </p>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="space-y-2">
              <label htmlFor="setup-email" className="text-sm font-medium text-stone-700">
                管理员邮箱
              </label>
              <Input
                id="setup-email"
                value={email}
                type="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="admin@example.com"
                className="h-12 rounded-2xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="setup-password" className="text-sm font-medium text-stone-700">
                管理员密码
              </label>
              <Input
                id="setup-password"
                value={password}
                type="password"
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void handleSubmit();
                }}
                placeholder="至少 8 位"
                className="h-12 rounded-2xl border-stone-200 bg-white"
              />
            </div>
          </div>

          <Button
            className="h-12 w-full rounded-2xl bg-emerald-950 text-white hover:bg-emerald-900"
            disabled={isSubmitting}
            onClick={() => void handleSubmit()}
          >
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            创建并进入后台
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
