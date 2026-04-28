"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LoaderCircle, MailCheck, Ticket } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchPublicSettings, registerUser, sendVerifyCode, type PublicSettings } from "@/lib/api";
import { useRedirectIfAuthenticated } from "@/lib/use-auth-guard";
import { getDefaultRouteForRole, setStoredAuthSession } from "@/store/auth";

export default function RegisterPage() {
  const router = useRouter();
  const { isCheckingAuth } = useRedirectIfAuthenticated();
  const [settings, setSettings] = useState<PublicSettings | null>(null);
  const [isLoadingSettings, setIsLoadingSettings] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [invitationCode, setInvitationCode] = useState("");
  const [promoCode, setPromoCode] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const data = await fetchPublicSettings();
        if (active) setSettings(data.settings);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "读取注册设置失败");
      } finally {
        if (active) setIsLoadingSettings(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  const normalizedEmail = email.trim().toLowerCase();
  const emailVerificationEnabled = Boolean(settings?.email_verification_enabled);

  const handleSendCode = async () => {
    if (!normalizedEmail) {
      toast.error("请先输入邮箱");
      return;
    }
    setIsSendingCode(true);
    try {
      await sendVerifyCode(normalizedEmail);
      toast.success("验证码已发送");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "发送验证码失败");
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleRegister = async () => {
    if (!normalizedEmail || !password) {
      toast.error("请输入邮箱和密码");
      return;
    }
    if (emailVerificationEnabled && !verificationCode.trim()) {
      toast.error("请输入邮箱验证码");
      return;
    }
    if (settings?.invitation_required && !invitationCode.trim()) {
      toast.error("请输入邀请码");
      return;
    }

    setIsSubmitting(true);
    try {
      const data = await registerUser({
        email: normalizedEmail,
        password,
        verification_code: verificationCode.trim(),
        invitation_code: invitationCode.trim(),
        promo_code: promoCode.trim(),
      });
      await setStoredAuthSession({
        key: data.token,
        role: data.role,
        subjectId: data.subject_id,
        name: data.name,
      });
      router.replace(getDefaultRouteForRole(data.role));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "注册失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isCheckingAuth || isLoadingSettings) {
    return (
      <div className="grid min-h-[calc(100vh-1rem)] place-items-center">
        <LoaderCircle className="size-5 animate-spin text-stone-400" />
      </div>
    );
  }

  if (settings && !settings.registration_enabled) {
    return (
      <div className="grid min-h-[calc(100vh-1rem)] place-items-center px-4">
        <Card className="w-full max-w-[520px] rounded-[30px] border-white/80 bg-white/95 shadow-sm">
          <CardContent className="space-y-4 p-8 text-center">
            <Ticket className="mx-auto size-9 text-stone-400" />
            <h1 className="text-2xl font-semibold tracking-tight text-stone-950">注册暂未开放</h1>
            <p className="text-sm text-stone-500">请联系管理员创建账号，或稍后再试。</p>
            <Button asChild className="rounded-2xl bg-stone-950 text-white hover:bg-stone-800">
              <Link href="/login">返回登录</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid min-h-[calc(100vh-1rem)] w-full place-items-center px-4 py-6">
      <Card className="w-full max-w-[590px] rounded-[34px] border-white/80 bg-white/95 shadow-[0_30px_110px_rgba(28,25,23,0.12)]">
        <CardContent className="space-y-7 p-6 sm:p-8">
          <div className="space-y-4 text-center">
            <div className="mx-auto inline-flex size-16 items-center justify-center rounded-[24px] bg-stone-950 text-white">
              <MailCheck className="size-6" />
            </div>
            <div className="space-y-2">
              <div className="text-xs font-semibold tracking-[0.28em] text-stone-500 uppercase">
                {settings?.site_name || "chatgpt2api"}
              </div>
              <h1 className="text-3xl font-semibold tracking-tight text-stone-950">创建用户账号</h1>
              <p className="text-sm leading-6 text-stone-500">注册后可直接进入画图页，图片请求按次数扣减额度。</p>
            </div>
          </div>

          <div className="grid gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">邮箱</label>
              <Input
                value={email}
                type="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@example.com"
                className="h-12 rounded-2xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">密码</label>
              <Input
                value={password}
                type="password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="至少 8 位"
                className="h-12 rounded-2xl border-stone-200 bg-white"
              />
            </div>
            {emailVerificationEnabled ? (
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700">邮箱验证码</label>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <Input
                    value={verificationCode}
                    onChange={(event) => setVerificationCode(event.target.value)}
                    placeholder="6 位验证码"
                    className="h-12 rounded-2xl border-stone-200 bg-white"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    className="h-12 rounded-2xl border-stone-200 bg-white px-5"
                    disabled={isSendingCode}
                    onClick={() => void handleSendCode()}
                  >
                    {isSendingCode ? <LoaderCircle className="size-4 animate-spin" /> : null}
                    发送验证码
                  </Button>
                </div>
              </div>
            ) : null}
            {settings?.invitation_required ? (
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700">邀请码</label>
                <Input
                  value={invitationCode}
                  onChange={(event) => setInvitationCode(event.target.value)}
                  placeholder="INV-..."
                  className="h-12 rounded-2xl border-stone-200 bg-white"
                />
              </div>
            ) : null}
            {settings?.promo_codes_enabled ? (
              <div className="space-y-2">
                <label className="text-sm font-medium text-stone-700">优惠码（可选）</label>
                <Input
                  value={promoCode}
                  onChange={(event) => setPromoCode(event.target.value)}
                  placeholder="WELCOME"
                  className="h-12 rounded-2xl border-stone-200 bg-white"
                />
              </div>
            ) : null}
          </div>

          <Button
            className="h-12 w-full rounded-2xl bg-stone-950 text-white hover:bg-stone-800"
            disabled={isSubmitting}
            onClick={() => void handleRegister()}
          >
            {isSubmitting ? <LoaderCircle className="size-4 animate-spin" /> : null}
            注册并登录
          </Button>

          <div className="text-center text-sm text-stone-500">
            已有账号？
            <Link href="/login" className="ml-1 font-medium text-stone-950 hover:underline">
              返回登录
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
