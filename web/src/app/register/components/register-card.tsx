"use client";

import { useState } from "react";

import { AlertTriangle, LoaderCircle, Plus, Play, RotateCcw, Save, Square, Trash2, UserPlus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { RegisterProxyInputMode } from "@/lib/api";

import { useSettingsStore } from "../../settings/store";

export function RegisterCard() {
  const config = useSettingsStore((state) => state.registerConfig);
  const isLoading = useSettingsStore((state) => state.isLoadingRegister);
  const isSaving = useSettingsStore((state) => state.isSavingRegister);
  const setProxy = useSettingsStore((state) => state.setRegisterProxy);
  const setProxyInputMode = useSettingsStore((state) => state.setRegisterProxyInputMode);
  const setProxyUrl = useSettingsStore((state) => state.setRegisterProxyUrl);
  const setProxyListText = useSettingsStore((state) => state.setRegisterProxyListText);
  const setProxyRefreshInterval = useSettingsStore((state) => state.setRegisterProxyRefreshInterval);
  const setTotal = useSettingsStore((state) => state.setRegisterTotal);
  const setThreads = useSettingsStore((state) => state.setRegisterThreads);
  const setMode = useSettingsStore((state) => state.setRegisterMode);
  const setTargetQuota = useSettingsStore((state) => state.setRegisterTargetQuota);
  const setTargetAvailable = useSettingsStore((state) => state.setRegisterTargetAvailable);
  const setCheckInterval = useSettingsStore((state) => state.setRegisterCheckInterval);
  const setMailField = useSettingsStore((state) => state.setRegisterMailField);
  const setMailApiUseRegisterProxy = useSettingsStore((state) => state.setRegisterMailApiUseRegisterProxy);
  const addProvider = useSettingsStore((state) => state.addRegisterProvider);
  const updateProvider = useSettingsStore((state) => state.updateRegisterProvider);
  const deleteProvider = useSettingsStore((state) => state.deleteRegisterProvider);
  const save = useSettingsStore((state) => state.saveRegister);
  const toggle = useSettingsStore((state) => state.toggleRegister);
  const reset = useSettingsStore((state) => state.resetRegister);
  const resetOutlookPool = useSettingsStore((state) => state.resetOutlookPool);
  const resetProxyBlacklist = useSettingsStore((state) => state.resetProxyBlacklist);
  const [proxyBlacklistDialogOpen, setProxyBlacklistDialogOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-stone-200 bg-white/80 p-10">
        <LoaderCircle className="size-5 animate-spin text-stone-400" />
      </div>
    );
  }

  if (!config) return null;

  const stats = config.stats || { success: 0, fail: 0, done: 0, running: 0, threads: config.threads };
  const providers = config.mail.providers || [];
  const logs = config.logs || [];
  const proxyMode = config.proxy_input_mode || "single";
  const proxySourceLabel = proxyMode === "url" ? "URL 列表" : proxyMode === "text" ? "手动列表" : "单代理";
  const currentProxy = String(stats.current_proxy || (proxyMode === "single" ? config.proxy : "") || "").trim();
  const proxyBlacklistCount = Math.max(0, Number(stats.proxy_blacklist_count || 0));
  const canResetProxyBlacklist = !config.enabled && proxyBlacklistCount > 0 && (proxyMode === "url" || proxyMode === "text");
  const updateProviderType = (index: number, type: string) => {
    updateProvider(index, {
      type,
      enable: true,
      ...(type === "cloudmail_gen" ? { api_base: "", admin_email: "", admin_password: "", domain: [], subdomain: [], email_prefix: "" } : {}),
      ...(type === "cloudflare_temp_email" ? { api_base: "", admin_password: "", domain: [] } : {}),
      ...(type === "tempmail_lol" ? { api_key: "", domain: [] } : {}),
      ...(type === "moemail" ? { api_base: "", api_key: "", domain: [] } : {}),
      ...(type === "inbucket" ? { api_base: "", domain: [], random_subdomain: true } : {}),
      ...(type === "duckmail" ? { api_key: "", default_domain: "duckmail.sbs" } : {}),
      ...(type === "gptmail" ? { api_key: "", default_domain: "" } : {}),
      ...(type === "yyds_mail" ? { api_base: "https://maliapi.215.im/v1", api_key: "", domain: [], subdomain: "", wildcard: false } : {}),
      ...(type === "ddg_mail" ? { ddg_token: "", cf_inbox_jwt: "", cf_domain: [], admin_password: "" } : {}),
      ...(type === "outlook_token" ? { mailboxes: "", mode: "graph", imap_host: "outlook.office365.com", message_limit: 10 } : {}),
    });
  };

  return (
    <div className="grid h-[calc(100vh-132px)] min-h-[640px] items-stretch gap-0 overflow-hidden rounded-xl border border-stone-200 bg-white/70 xl:grid-cols-2">
      <section className="space-y-4 overflow-y-auto border-b border-stone-200 p-4 xl:border-r xl:border-b-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-md bg-stone-100">
                <UserPlus className="size-5 text-stone-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold tracking-tight">注册配置</h2>
              </div>
            </div>
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" onClick={() => void save()} disabled={isSaving || config.enabled}>
              {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
              保存配置
            </Button>
          </div>

          <div className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-800">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>如果注册日志出现 Cloudflare 拦截，可在设置页启用 FlareSolverr 清障；相关 Docker 容器需要先启动。</span>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <label className="text-sm text-stone-700">注册模式</label>
              <Select value={config.mode || "total"} onValueChange={(value) => setMode(value as "total" | "quota" | "available")} disabled={config.enabled}>
                <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="total">注册总数</SelectItem>
                  <SelectItem value="quota">号池剩余额度</SelectItem>
                  <SelectItem value="available">可用账号数量</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">注册总数</label>
              <Input value={String(config.total)} onChange={(event) => setTotal(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled || config.mode !== "total"} />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">线程数</label>
              <Input value={String(config.threads)} onChange={(event) => setThreads(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">代理来源</label>
              <Select value={proxyMode} onValueChange={(value) => setProxyInputMode(value as RegisterProxyInputMode)} disabled={config.enabled}>
                <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="single">单代理</SelectItem>
                  <SelectItem value="url">代理列表 URL</SelectItem>
                  <SelectItem value="text">手动代理列表</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {canResetProxyBlacklist ? (
              <div className="space-y-2">
                <label className="text-sm text-stone-700">代理黑名单</label>
                <Button type="button" variant="outline" className="h-10 w-full rounded-xl border-stone-200 bg-white text-stone-700" onClick={() => setProxyBlacklistDialogOpen(true)} disabled={isSaving}>
                  <Trash2 className="size-4" />
                  重置黑名单
                </Button>
              </div>
            ) : null}
            {proxyMode === "single" ? (
              <div className="space-y-2">
                <label className="text-sm text-stone-700">注册代理</label>
                <Input value={config.proxy} onChange={(event) => setProxy(event.target.value)} placeholder="http://127.0.0.1:7890" className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
              </div>
            ) : null}
            {proxyMode === "url" ? (
              <>
                <div className="space-y-2 md:col-span-2">
                  <label className="text-sm text-stone-700">代理列表 URL</label>
                  <Input value={config.proxy_url || ""} onChange={(event) => setProxyUrl(event.target.value)} placeholder="https://example.com/proxies.txt" className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                </div>
                <div className="space-y-2">
                  <label className="text-sm text-stone-700">刷新秒数</label>
                  <Input value={String(config.proxy_refresh_interval || "")} onChange={(event) => setProxyRefreshInterval(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                </div>
              </>
            ) : null}
            {proxyMode === "text" ? (
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm text-stone-700">代理列表</label>
                <Textarea value={config.proxy_list_text || ""} onChange={(event) => setProxyListText(event.target.value)} placeholder="每行一个代理，支持 http://、socks5:// 或 ip:port" className="min-h-24 rounded-xl border-stone-200 bg-white font-mono text-xs" disabled={config.enabled} />
              </div>
            ) : null}
            <div className="space-y-2">
              <label className="text-sm text-stone-700">目标剩余额度</label>
              <Input value={String(config.target_quota || "")} onChange={(event) => setTargetQuota(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled || config.mode !== "quota"} />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">目标可用账号</label>
              <Input value={String(config.target_available || "")} onChange={(event) => setTargetAvailable(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled || config.mode !== "available"} />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">检查间隔（秒）</label>
              <Input value={String(config.check_interval || "")} onChange={(event) => setCheckInterval(event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled || config.mode === "total"} />
            </div>
          </div>

          <Dialog open={proxyBlacklistDialogOpen} onOpenChange={setProxyBlacklistDialogOpen}>
            <DialogContent showCloseButton={false} className="rounded-2xl p-6">
              <DialogHeader className="gap-2">
                <DialogTitle>重置代理黑名单</DialogTitle>
                <DialogDescription className="text-sm leading-6">
                  当前代理黑名单里有 {proxyBlacklistCount} 条记录。清理后会忘记这些代理的失败、冷却和评分状态，下一轮会重新评估代理。
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="pt-2">
                <DialogClose asChild>
                  <Button type="button" variant="outline" className="rounded-xl border-stone-200 bg-white" disabled={isSaving}>
                    取消
                  </Button>
                </DialogClose>
                <Button
                  type="button"
                  className="rounded-xl bg-stone-950 text-white hover:bg-stone-800"
                  disabled={isSaving}
                  onClick={async () => {
                    await resetProxyBlacklist();
                    setProxyBlacklistDialogOpen(false);
                  }}
                >
                  {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                  确认清理
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <div className="space-y-3 border-t border-stone-200 pt-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold text-stone-800">邮箱配置</h3>
                <p className="mt-1 text-xs text-stone-500">可配置多个 provider，按启用顺序轮换。</p>
              </div>
              <Button type="button" variant="outline" className="h-9 rounded-xl border-stone-200 bg-white px-3 text-stone-700" onClick={addProvider} disabled={config.enabled}>
                <Plus className="size-4" />
                添加
              </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">请求超时</label>
                <Input value={String(config.mail.request_timeout || "")} onChange={(event) => setMailField("request_timeout", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">等待验证码超时</label>
                <Input value={String(config.mail.wait_timeout || "")} onChange={(event) => setMailField("wait_timeout", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">轮询间隔</label>
                <Input value={String(config.mail.wait_interval || "")} onChange={(event) => setMailField("wait_interval", event.target.value)} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
              </div>
            </div>

            <label className="flex items-start gap-3 rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700">
              <Checkbox checked={config.mail.api_use_register_proxy !== false} onCheckedChange={(checked) => setMailApiUseRegisterProxy(Boolean(checked))} disabled={config.enabled} />
              <span className="space-y-1">
                <span className="block font-medium text-stone-800">邮箱服务后台 API 使用注册代理</span>
                <span className="block text-xs leading-5 text-stone-500">关闭后邮箱平台 API 直连，注册 OpenAI/Auth0 请求仍使用注册代理。</span>
              </span>
            </label>

            <div className="space-y-3">
              {providers.map((provider, index) => {
                const type = String(provider.type || "tempmail_lol");
                const domains = Array.isArray(provider.domain) ? provider.domain.map(String).join("\n") : "";
                const subdomains = Array.isArray(provider.subdomain) ? provider.subdomain.map(String).join("\n") : "";
                return (
                  <div key={index} className="space-y-3 border-t border-stone-200 pt-3 first:border-t-0 first:pt-0">
                    <div className="flex items-center justify-between gap-3">
                      <label className="flex items-center gap-3 text-sm text-stone-700">
                        <Checkbox checked={Boolean(provider.enable)} onCheckedChange={(checked) => updateProvider(index, { enable: Boolean(checked) })} disabled={config.enabled} />
                        启用
                      </label>
                      <button type="button" className="rounded-lg p-2 text-stone-400 transition hover:bg-rose-50 hover:text-rose-500 disabled:opacity-50" onClick={() => deleteProvider(index)} disabled={config.enabled || providers.length <= 1} title="删除 provider">
                        <Trash2 className="size-4" />
                      </button>
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <label className="text-sm text-stone-700">类型</label>
                        <Select value={type} onValueChange={(value) => updateProviderType(index, value)} disabled={config.enabled}>
                          <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="cloudmail_gen">cloudmail_gen</SelectItem>
                            <SelectItem value="cloudflare_temp_email">cloudflare_temp_email</SelectItem>
                            <SelectItem value="tempmail_lol">tempmail_lol</SelectItem>
                            <SelectItem value="moemail">moemail</SelectItem>
                            <SelectItem value="inbucket">inbucket_mail</SelectItem>
                            <SelectItem value="duckmail">duckmail</SelectItem>
                            <SelectItem value="gptmail">gptmail(未测试)</SelectItem>
                            <SelectItem value="yyds_mail">yyds_mail</SelectItem>
                            <SelectItem value="ddg_mail">ddg_mail (DDG邮箱+CF中转)</SelectItem>
                            <SelectItem value="outlook_token">outlook_token (Outlook/Hotmail 邮箱池)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      {type === "cloudmail_gen" || type === "cloudflare_temp_email" || type === "moemail" || type === "inbucket" || type === "yyds_mail" || type === "ddg_mail" ? (
                        <>
                          <div className="space-y-2">
                            <label className="text-sm text-stone-700">{type === "cloudmail_gen" ? "CloudMail URL" : "API Base"}</label>
                            <Input value={String(provider.api_base || "")} onChange={(event) => updateProvider(index, { api_base: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                          </div>
                          {type === "cloudmail_gen" ? (
                            <>
                              <div className="space-y-2">
                                <label className="text-sm text-stone-700">管理员邮箱</label>
                                <Input value={String(provider.admin_email || "")} onChange={(event) => updateProvider(index, { admin_email: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                              </div>
                              <div className="space-y-2">
                                <label className="text-sm text-stone-700">管理员密码</label>
                                <Input value={String(provider.admin_password || "")} onChange={(event) => updateProvider(index, { admin_password: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                              </div>
                            </>
                          ) : null}
                          {type === "cloudflare_temp_email" || type === "ddg_mail" ? (
                            <div className="space-y-2">
                              <label className="text-sm text-stone-700">Admin Password</label>
                              <Input value={String(provider.admin_password || "")} onChange={(event) => updateProvider(index, { admin_password: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                            </div>
                          ) : null}
                        </>
                      ) : null}
                      {type === "ddg_mail" ? (
                        <>
                        <div className="space-y-2">
                          <label className="text-sm text-stone-700">DDG Token <span className="text-red-400">*</span></label>
                          <Input value={String(provider.ddg_token || "")} onChange={(event) => updateProvider(index, { ddg_token: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} placeholder="DuckDuckGo Email Protection 的 Bearer Token" />
                        </div>
                        <div className="space-y-2">
                          <label className="text-sm text-stone-700">CF Inbox JWT <span className="text-red-400">*</span></label>
                          <Input value={String(provider.cf_inbox_jwt || "")} onChange={(event) => updateProvider(index, { cf_inbox_jwt: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} placeholder="CF 临时邮箱后端的固定收件箱 JWT（DDG 转发目标）" />
                        </div>
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                          <p className="font-medium mb-1">使用说明</p>
                          <ol className="list-decimal list-inside space-y-0.5">
                            <li>先在 <a href="https://duckduckgo.com/email/" target="_blank" className="underline">DuckDuckGo Email Protection</a> 登录并设置转发目标为 CF 收件箱地址</li>
                            <li>DDG Token 从浏览器 DevTools → Network → quack.duckduckgo.com 请求中获取 <code className="bg-amber-100 px-1 rounded">Authorization: Bearer</code></li>
                            <li>CF Inbox JWT 从 CF 临时邮箱后端创建固定收件箱后获取</li>
                            <li>所有 @duck.com 别名收到的邮件会转发到同一个 CF 收件箱，系统按 To: 头自动匹配</li>
                          </ol>
                        </div>
                        </>
                      ) : null}
                      {type === "inbucket" ? (
                        <label className="flex items-center gap-3 pt-8 text-sm text-stone-700">
                          <Checkbox checked={Boolean(provider.random_subdomain ?? true)} onCheckedChange={(checked) => updateProvider(index, { random_subdomain: Boolean(checked) })} disabled={config.enabled} />
                          启用随机子域名
                        </label>
                      ) : null}
                      {type === "tempmail_lol" || type === "moemail" || type === "duckmail" || type === "gptmail" || type === "yyds_mail" ? (
                        <div className="space-y-2">
                          <label className="text-sm text-stone-700">API Key</label>
                          <Input value={String(provider.api_key || "")} onChange={(event) => updateProvider(index, { api_key: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                        </div>
                      ) : null}
                      {type === "duckmail" || type === "gptmail" ? (
                        <div className="space-y-2">
                          <label className="text-sm text-stone-700">Default Domain</label>
                          <Input value={String(provider.default_domain || "")} onChange={(event) => updateProvider(index, { default_domain: event.target.value })} placeholder={type === "duckmail" ? "duckmail.sbs" : ""} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                        </div>
                      ) : null}
                      {type === "yyds_mail" ? (
                        <>
                          <div className="space-y-2">
                            <label className="text-sm text-stone-700">Subdomain</label>
                            <Input value={String(provider.subdomain || "")} onChange={(event) => updateProvider(index, { subdomain: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                          </div>
                          <label className="flex items-center gap-3 pt-8 text-sm text-stone-700">
                            <Checkbox checked={Boolean(provider.wildcard)} onCheckedChange={(checked) => updateProvider(index, { wildcard: Boolean(checked) })} disabled={config.enabled} />
                            Wildcard
                          </label>
                        </>
                      ) : null}
                      {type === "outlook_token" ? (
                        <>
                          <div className="space-y-2">
                            <label className="text-sm text-stone-700">读取方式</label>
                            <Select value={String(provider.mode || "graph")} onValueChange={(value) => updateProvider(index, { mode: value })} disabled={config.enabled}>
                              <SelectTrigger className="h-10 rounded-xl border-stone-200 bg-white">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="graph">Graph API</SelectItem>
                                <SelectItem value="imap">IMAP (XOAUTH2)</SelectItem>
                                <SelectItem value="auto">自动 (Graph→IMAP)</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                          {String(provider.mode || "graph") !== "graph" ? (
                            <div className="space-y-2">
                              <label className="text-sm text-stone-700">IMAP Host</label>
                              <Input value={String(provider.imap_host || "outlook.office365.com")} onChange={(event) => updateProvider(index, { imap_host: event.target.value })} className="h-10 rounded-xl border-stone-200 bg-white" disabled={config.enabled} />
                            </div>
                          ) : null}
                        </>
                      ) : null}
                    </div>

                    {type === "outlook_token" ? (() => {
                      const stats = (provider.mailboxes_stats || {}) as Record<string, number>;
                      const savedCount = Number(provider.mailboxes_count || 0);
                      const preview = Array.isArray(provider.mailboxes_preview) ? (provider.mailboxes_preview as string[]) : [];
                      const pendingCount = String(provider.mailboxes || "").split(/\r?\n/).filter((line) => line.includes("----") && line.split("----").length >= 4).length;
                      return (
                        <div className="space-y-2">
                          <label className="flex items-center justify-between text-sm text-stone-700">
                            <span>邮箱池导入 <span className="text-red-400">*</span></span>
                            <span className="text-xs text-stone-400">已保存 {savedCount} 个{pendingCount ? ` · 待导入 ${pendingCount} 个` : ""}</span>
                          </label>
                          <Textarea value={String(provider.mailboxes || "")} onChange={(event) => updateProvider(index, { mailboxes: event.target.value })} placeholder={"每行一个邮箱，格式：\n邮箱----密码----client_id----refresh_token\n（出于安全，已保存的密码/refresh_token 不会回显；此处仅用于新增或覆盖）"} className="min-h-32 rounded-xl border-stone-200 bg-white font-mono text-xs" disabled={config.enabled} />
                          <div className="flex flex-wrap items-center gap-1.5 text-xs">
                            <span className="rounded-md bg-stone-100 px-2 py-1 text-stone-600">未使用 {stats.unused ?? 0}</span>
                            <span className="rounded-md bg-blue-50 px-2 py-1 text-blue-600">占用中 {stats.in_use ?? 0}</span>
                            <span className="rounded-md bg-emerald-50 px-2 py-1 text-emerald-700">已用 {stats.used ?? 0}</span>
                            <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-700">token失效 {stats.token_invalid ?? 0}</span>
                            <span className="rounded-md bg-rose-50 px-2 py-1 text-rose-600">失败 {stats.failed ?? 0}</span>
                          </div>
                          {preview.length ? (
                            <p className="text-xs text-stone-400">已保存邮箱（脱敏）：{preview.slice(0, 8).join("、")}{preview.length > 8 ? ` 等 ${preview.length} 个` : ""}</p>
                          ) : null}
                          <div className="flex flex-wrap items-center gap-2">
                            <Button type="button" variant="outline" className="h-8 rounded-lg border-stone-200 bg-white px-3 text-xs text-stone-700" onClick={() => void resetOutlookPool("failed")} disabled={config.enabled}>
                              清除失败/占用状态
                            </Button>
                            <Button type="button" variant="outline" className="h-8 rounded-lg border-amber-200 bg-white px-3 text-xs text-amber-700 hover:bg-amber-50" onClick={() => { if (window.confirm("确定要从 Outlook 邮箱池中删除所有未使用邮箱吗？此操作会移除这些已保存凭据。")) void resetOutlookPool("unused"); }} disabled={config.enabled}>
                              清空未使用
                            </Button>
                            <Button type="button" variant="outline" className="h-8 rounded-lg border-rose-200 bg-white px-3 text-xs text-rose-600 hover:bg-rose-50" onClick={() => { if (window.confirm("确定要重置整个 Outlook 邮箱池状态吗？所有邮箱会被标记为可重新使用。")) void resetOutlookPool("all"); }} disabled={config.enabled}>
                              重置全部状态
                            </Button>
                          </div>
                          <p className="text-xs text-stone-500">每个邮箱仅成功注册一次（状态记录在 data/outlook_token_used.json）。失败的邮箱会被标记原因，可用上方按钮释放后重试。</p>
                        </div>
                      );
                    })() : null}

                    {type === "cloudmail_gen" || type === "tempmail_lol" || type === "cloudflare_temp_email" || type === "moemail" || type === "inbucket" || type === "yyds_mail" || type === "ddg_mail" ? (
                      <div className="space-y-2">
                        <label className="text-sm text-stone-700">{type === "cloudmail_gen" ? "邮箱域名" : type === "inbucket" ? "基础域名列表" : "Domain"}</label>
                        <Textarea value={domains} onChange={(event) => updateProvider(index, { domain: event.target.value.split(/[\n,]/).map((item) => item.trim()) })} placeholder={type === "cloudmail_gen" ? "每行一个域名，留空则使用服务默认域名" : type === "inbucket" ? "每行一个基础域名，系统会自动生成随机子域名" : type === "moemail" ? "每行一个域名" : "每行一个域名，留空则使用服务默认域名"} className="min-h-20 rounded-xl border-stone-200 bg-white font-mono text-xs" disabled={config.enabled} />
                      </div>
                    ) : null}
                    {type === "cloudmail_gen" ? (
                      <div className="space-y-2">
                        <label className="text-sm text-stone-700">子域名（支持多个）</label>
                        <Textarea value={subdomains} onChange={(event) => updateProvider(index, { subdomain: event.target.value.split(/[\n,]/).map((item) => item.trim()) })} placeholder="每行一个子域名前缀，留空则直接使用主域名" className="min-h-20 rounded-xl border-stone-200 bg-white font-mono text-xs" disabled={config.enabled} />
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>

      </section>

      <section className="flex min-h-0 flex-col p-4">
        <div className="space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold tracking-tight">运行结果</h2>
                <p className="mt-1 text-sm text-stone-500">SSE 实时推送当前状态。</p>
              </div>
              <Badge variant={config.enabled ? "success" : "secondary"} className="rounded-md">
                {config.enabled ? "运行中" : "已停止"}
              </Badge>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {[
                ["成功 / 成功率", `${stats.success} / ${stats.success_rate || 0}%`],
                ["失败", stats.fail],
                ["完成", stats.done],
                ["运行 / 线程", `${stats.running} / ${stats.threads}`],
                ["运行时间", `${stats.elapsed_seconds || 0}s`],
                ["平均注册单个", `${stats.avg_seconds || 0}s`],
                ["当前额度", stats.current_quota || 0],
                ["正常账号", stats.current_available || 0],
              ].map(([label, value]) => (
                <div key={label} className="border border-stone-200 bg-white/70 px-3 py-2">
                  <div className="text-xs text-stone-400">{label}</div>
                  <div className="mt-1 text-base font-semibold text-stone-800">{value}</div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="border border-stone-200 bg-white/70 px-3 py-2">
                <div className="text-xs text-stone-400">代理来源</div>
                <div className="mt-1 text-sm font-semibold text-stone-800">{proxySourceLabel}</div>
              </div>
              <div className="border border-stone-200 bg-white/70 px-3 py-2">
                <div className="text-xs text-stone-400">代理池数量</div>
                <div className="mt-1 text-sm font-semibold text-stone-800">{stats.proxy_pool_count ?? (proxyMode === "single" && config.proxy.trim() ? 1 : 0)}</div>
              </div>
            </div>
            <div className="border border-stone-200 bg-white/70 px-3 py-2">
              <div className="text-xs text-stone-400">当前代理</div>
              <div className="mt-1 truncate font-mono text-sm font-semibold text-stone-800" title={currentProxy || "默认出站"}>
                {currentProxy || "默认出站"}
              </div>
            </div>
            {stats.proxy_pool_last_error ? (
              <div className="border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {stats.proxy_pool_last_error}
              </div>
            ) : null}
            <div className="grid grid-cols-3 gap-2">
              <Button className="h-10 rounded-xl bg-stone-950 px-3 text-white hover:bg-stone-800" onClick={() => void toggle()} disabled={isSaving}>
                {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : config.enabled ? <Square className="size-4" /> : <Play className="size-4" />}
                {config.enabled ? "停止" : "启动"}
              </Button>
              <Button variant="outline" className="h-10 rounded-xl border-stone-200 bg-white px-3 text-stone-700" onClick={() => void reset()} disabled={isSaving || config.enabled}>
                <RotateCcw className="size-4" />
                重置
              </Button>
              <Button variant="outline" className="h-10 rounded-xl border-stone-200 bg-white px-3 text-stone-700" onClick={() => void save()} disabled={isSaving || config.enabled}>
                <Save className="size-4" />
                保存
              </Button>
            </div>
            <div className="flex items-center gap-2 border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <AlertTriangle className="size-4 shrink-0" />
              启动之前注意先保存配置。
            </div>
        </div>

        <div className="mt-4 flex min-h-0 flex-1 flex-col space-y-3 overflow-hidden border-t border-stone-200 pt-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-stone-900">实时日志</h3>
                <p className="mt-1 text-xs text-amber-700">遇到 HTTP 状态码 400 等错误，基本是邮箱滥用被封，需要更换新的域名邮箱。</p>
              </div>
              <Badge variant="secondary" className="rounded-md">
                {logs.length}
              </Badge>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto border border-stone-200 bg-white/70 p-3 font-mono text-xs leading-6">
              {logs.length === 0 ? (
                <div className="text-stone-500">暂无日志</div>
              ) : (
                logs.slice().reverse().map((item, index) => (
                  <div key={`${item.time}-${index}`} className={item.level === "red" ? "text-rose-600" : item.level === "green" ? "text-emerald-700" : item.level === "yellow" ? "text-amber-700" : "text-stone-700"}>
                    <span className="text-stone-400">{new Date(item.time).toLocaleTimeString()}</span>
                    <span className="pl-2">{item.text}</span>
                  </div>
                ))
              )}
            </div>
        </div>
      </section>
    </div>
  );
}
