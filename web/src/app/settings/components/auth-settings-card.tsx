"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LoaderCircle, Save, Shield, Ticket, Users } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { fetchAuthSettings, updateAuthSettings, type AuthSettings } from "@/lib/api";

function normalizeSettings(settings: AuthSettings): AuthSettings {
  return {
    ...settings,
    email_domain_whitelist: Array.isArray(settings.email_domain_whitelist) ? settings.email_domain_whitelist : [],
    smtp_password: "",
  };
}

export function AuthSettingsCard() {
  const didLoadRef = useRef(false);
  const [settings, setSettings] = useState<AuthSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    const load = async () => {
      try {
        const data = await fetchAuthSettings();
        setSettings(normalizeSettings(data.settings));
      } catch (error) {
        toast.error(error instanceof Error ? error.message : "加载认证设置失败");
      } finally {
        setIsLoading(false);
      }
    };
    void load();
  }, []);

  const patch = (updates: Partial<AuthSettings>) => {
    setSettings((current) => (current ? { ...current, ...updates } : current));
  };

  const handleSave = async () => {
    if (!settings) return;
    setIsSaving(true);
    try {
      const data = await updateAuthSettings({
        ...settings,
        email_domain_whitelist: settings.email_domain_whitelist,
        default_image_quota: Number(settings.default_image_quota) || 0,
        default_image_concurrency: Number(settings.default_image_concurrency) || 1,
        verify_code_ttl_seconds: Number(settings.verify_code_ttl_seconds) || 900,
        verify_send_cooldown_seconds: Number(settings.verify_send_cooldown_seconds) || 60,
        verify_max_attempts: Number(settings.verify_max_attempts) || 5,
        smtp_port: Number(settings.smtp_port) || 587,
      });
      setSettings(normalizeSettings(data.settings));
      toast.success("认证设置已保存");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存认证设置失败");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
        <CardContent className="flex justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-stone-400" />
        </CardContent>
      </Card>
    );
  }

  if (!settings) return null;

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-6 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-emerald-50">
              <Shield className="size-5 text-emerald-700" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">注册与认证设置</h2>
              <p className="text-sm text-stone-500">配置邮箱验证、邀请码、优惠码、默认图片额度和 SMTP。</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" className="h-9 rounded-xl border-stone-200 bg-white">
              <Link href="/admin/users">
                <Users className="size-4" />
                用户管理
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-9 rounded-xl border-stone-200 bg-white">
              <Link href="/admin/redeem-codes">
                <Ticket className="size-4" />
                码管理
              </Link>
            </Button>
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" disabled={isSaving} onClick={() => void handleSave()}>
              {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
              保存
            </Button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["开放注册", "registration_enabled"],
            ["邮箱验证", "email_verification_enabled"],
            ["邀请码必填", "invitation_required"],
            ["启用优惠码", "promo_codes_enabled"],
          ].map(([label, key]) => (
            <label key={key} className="flex items-center justify-between rounded-2xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
              {label}
              <Checkbox
                checked={Boolean(settings[key as keyof AuthSettings])}
                onCheckedChange={(checked) => patch({ [key]: Boolean(checked) } as Partial<AuthSettings>)}
              />
            </label>
          ))}
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-2">
            <label className="text-sm text-stone-700">站点名称</label>
            <Input value={settings.site_name} onChange={(event) => patch({ site_name: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">默认图片额度</label>
            <Input value={String(settings.default_image_quota)} onChange={(event) => patch({ default_image_quota: Number(event.target.value) || 0 })} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">默认图片并发</label>
            <Input value={String(settings.default_image_concurrency)} onChange={(event) => patch({ default_image_concurrency: Number(event.target.value) || 1 })} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">验证码冷却秒数</label>
            <Input value={String(settings.verify_send_cooldown_seconds)} onChange={(event) => patch({ verify_send_cooldown_seconds: Number(event.target.value) || 60 })} className="h-10 rounded-xl border-stone-200 bg-white" />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm text-stone-700">邮箱后缀白名单</label>
            <Textarea
              value={settings.email_domain_whitelist.join("\n")}
              onChange={(event) =>
                patch({
                  email_domain_whitelist: event.target.value
                    .split(/[\n,]/)
                    .map((item) => item.trim().toLowerCase())
                    .filter(Boolean),
                })
              }
              placeholder="example.com，每行一个；留空则不限制"
              className="min-h-24 rounded-xl border-stone-200 bg-white font-mono text-xs"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <label className="text-sm text-stone-700">SMTP Host</label>
              <Input value={settings.smtp_host} onChange={(event) => patch({ smtp_host: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">SMTP Port</label>
              <Input value={String(settings.smtp_port)} onChange={(event) => patch({ smtp_port: Number(event.target.value) || 587 })} className="h-10 rounded-xl border-stone-200 bg-white" />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">SMTP Username</label>
              <Input value={settings.smtp_username} onChange={(event) => patch({ smtp_username: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">SMTP Password</label>
              <Input
                value={settings.smtp_password}
                type="password"
                onChange={(event) => patch({ smtp_password: event.target.value })}
                placeholder={settings.has_smtp_password ? "已配置，留空保留" : "未配置"}
                className="h-10 rounded-xl border-stone-200 bg-white"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <label className="text-sm text-stone-700">SMTP From</label>
              <Input value={settings.smtp_from} onChange={(event) => patch({ smtp_from: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
