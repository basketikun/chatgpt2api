"use client";

import { LoaderCircle, PlugZap, Save } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { testProxy, type ProxyTestResult } from "@/lib/api";

import { useSettingsStore } from "../store";

export function ConfigCard() {
  const [isTestingProxy, setIsTestingProxy] = useState(false);
  const [proxyTestResult, setProxyTestResult] = useState<ProxyTestResult | null>(null);
  const logLevelOptions = ["debug", "info", "warning", "error"];
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setRefreshAccountIntervalMinute = useSettingsStore((state) => state.setRefreshAccountIntervalMinute);
  const setImageRetentionDays = useSettingsStore((state) => state.setImageRetentionDays);
  const setImagePollTimeoutSecs = useSettingsStore((state) => state.setImagePollTimeoutSecs);
  const setImageAccountConcurrency = useSettingsStore((state) => state.setImageAccountConcurrency);
  const setAutoRemoveInvalidAccounts = useSettingsStore((state) => state.setAutoRemoveInvalidAccounts);
  const setAutoRemoveRateLimitedAccounts = useSettingsStore((state) => state.setAutoRemoveRateLimitedAccounts);
  const setKarpathyMode = useSettingsStore((state) => state.setKarpathyMode);
  const setAutoRefreshEnabled = useSettingsStore((state) => state.setAutoRefreshEnabled);
  const setLogLevel = useSettingsStore((state) => state.setLogLevel);
  const setProxy = useSettingsStore((state) => state.setProxy);
  const setBaseUrl = useSettingsStore((state) => state.setBaseUrl);
  const setGlobalSystemPrompt = useSettingsStore((state) => state.setGlobalSystemPrompt);
  const setSensitiveWordsText = useSettingsStore((state) => state.setSensitiveWordsText);
  const setAIReviewField = useSettingsStore((state) => state.setAIReviewField);
  const setField = useSettingsStore((state) => state.setField);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  const handleTestProxy = async () => {
    const candidate = String(config?.proxy || "").trim();
    if (!candidate) {
      toast.error("Vui lòng nhập địa chỉ proxy");
      return;
    }
    setIsTestingProxy(true);
    setProxyTestResult(null);
    try {
      const data = await testProxy(candidate);
      setProxyTestResult(data.result);
      if (data.result.ok) {
        toast.success(`Proxy khả dụng（${data.result.latency_ms} ms，HTTP ${data.result.status}）`);
      } else {
        toast.error(`Proxy không khả dụng：${data.result.error ?? "Lỗi không rõ"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Kiểm tra proxy thất bại");
    } finally {
      setIsTestingProxy(false);
    }
  };

  if (isLoadingConfig) {
    return (
      <div className="rounded-[16px] card-main">
        <div className="flex items-center justify-center p-10">
          <LoaderCircle className="size-5 animate-spin text-slate-400" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-[16px] card-main">
      <div className="border-b border-black/[0.04] bg-slate-50/50 px-6 py-4">
        <h2 className="text-[15px] font-bold text-slate-900">Cấu hình hệ thống</h2>
        <p className="text-[13px] text-slate-500 mt-0.5">Proxy, rate limit, tự động xóa tài khoản và kiểm duyệt AI</p>
      </div>
      <div className="space-y-4 p-6">
        <div className="rounded-[10px] border border-indigo-100 bg-indigo-50/50 px-4 py-3 text-[13px] leading-6 text-indigo-700">
          Mã khóa đăng nhập quản trị viên tiếp tục được đọc từ cấu hình triển khai và không còn hiển thị trên trang này; nếu bạn cần phân phối cho người khác, vui lòng tạo mã khóa người dùng bình thường bên dưới.
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Khoảng thời gian làm mới tài khoản</label>
            <Input
              value={String(config?.refresh_account_interval_minute || "")}
              onChange={(event) => setRefreshAccountIntervalMinute(event.target.value)}
              placeholder="Phút"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">Tính bằng phút, kiểm soát tần suất tự động làm mới tài khoản.</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Proxy toàn cầu</label>
            <Input
              value={String(config?.proxy || "")}
              onChange={(event) => {
                setProxy(event.target.value);
                setProxyTestResult(null);
              }}
              placeholder="http://127.0.0.1:7890"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">Để trống nếu không sử dụng proxy.</p>
            {proxyTestResult ? (
              <div
                className={`rounded-xl border px-3 py-2 text-xs leading-6 ${
                  proxyTestResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
                }`}
              >
                {proxyTestResult.ok
                  ? `Proxy khả dụng：HTTP ${proxyTestResult.status}，Thời gian phản hồi ${proxyTestResult.latency_ms} ms`
                  : `Proxy không khả dụng：${proxyTestResult.error ?? "Lỗi không rõ"}（Thời gian phản hồi ${proxyTestResult.latency_ms} ms）`}
              </div>
            ) : null}
            <div className="flex justify-end">
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
                onClick={() => void handleTestProxy()}
                disabled={isTestingProxy}
              >
                {isTestingProxy ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                Kiểm tra Proxy
              </Button>
            </div>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Địa chỉ truy cập hình ảnh</label>
            <Input
              value={String(config?.base_url || "")}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://example.com"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">Tiền tố địa chỉ được sử dụng để tạo kết quả hình ảnh.</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Tự động dọn dẹp hình ảnh</label>
            <Input
              value={String(config?.image_retention_days || "")}
              onChange={(event) => setImageRetentionDays(event.target.value)}
              placeholder="30"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">Tự động xóa hình ảnh cục bộ từ bao nhiêu ngày trước.</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Kích thước ảnh mặc định</label>
            <select
              value={String((config as any)?.default_image_size || "1792x1024")}
              onChange={(e) => setField("default_image_size", e.target.value)}
              className="h-10 w-full rounded-xl border border-stone-200 bg-white px-3 text-sm text-stone-700"
            >
              <optgroup label="▸ 16:9 (Landscape)">
                <option value="1792x1024">1792×1024 (16:9) — Mặc định</option>
                <option value="1344x768">1344×768 (16:9)</option>
              </optgroup>
              <optgroup label="▸ 9:16 (Portrait)">
                <option value="1024x1792">1024×1792 (9:16)</option>
                <option value="768x1344">768×1344 (9:16)</option>
              </optgroup>
              <optgroup label="▸ 1:1 (Square)">
                <option value="1024x1024">1024×1024 (1:1)</option>
                <option value="768x768">768×768 (1:1)</option>
                <option value="512x512">512×512 (1:1)</option>
                <option value="256x256">256×256 (1:1)</option>
              </optgroup>
              <optgroup label="▸ 4:3">
                <option value="1792x1344">1792×1344 (4:3)</option>
                <option value="1200x896">1200×896 (4:3)</option>
              </optgroup>
              <optgroup label="▸ 3:2">
                <option value="1536x1024">1536×1024 (3:2)</option>
                <option value="1264x848">1264×848 (3:2)</option>
              </optgroup>
              <optgroup label="▸ Khác">
                <option value="768x1024">768×1024 (3:4)</option>
                <option value="1024x768">1024×768 (4:3)</option>
              </optgroup>
            </select>
            <p className="text-xs text-stone-500">Áp dụng cho tất cả model: GPT, Gemini, NVIDIA, SD, FLUX...</p>
          </div>
          <div className="space-y-2">
            <label className="text-sm text-stone-700">Thời gian chờ thăm dò hình ảnh</label>
            <label className="text-sm text-stone-700">Số luồng hình ảnh trên mỗi tài khoản</label>
            <Input
              value={String(config?.image_account_concurrency || "")}
              onChange={(event) => setImageAccountConcurrency(event.target.value)}
              placeholder="1"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
            <p className="text-xs text-stone-500">Giới hạn số lượng yêu cầu hình ảnh được xử lý đồng thời bởi mỗi tài khoản, mặc định là 3.</p>
          </div>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(config?.auto_remove_invalid_accounts)}
              onCheckedChange={(checked) => setAutoRemoveInvalidAccounts(Boolean(checked))}
            />
            Tự động xóa tài khoản lỗi
          </label>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700">
            <Checkbox
              checked={Boolean(config?.auto_remove_rate_limited_accounts)}
              onCheckedChange={(checked) => setAutoRemoveRateLimitedAccounts(Boolean(checked))}
            />
            Tự động xóa tài khoản bị giới hạn
          </label>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 cursor-pointer">
            <Checkbox
              checked={Boolean((config as any)?.karpathy_mode)}
              onCheckedChange={(checked) => setKarpathyMode(Boolean(checked))}
            />
            <div>
              <p className="font-medium">Karpathy Mode</p>
              <p className="text-xs text-stone-500 mt-0.5">
                AI sẽ suy nghĩ trước khi code, đơn giản hóa, chỉ sửa đúng chỗ cần sửa.
              </p>
            </div>
          </label>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 cursor-pointer">
            <Checkbox
              checked={Boolean((config as any)?.auto_refresh_enabled ?? true)}
              onCheckedChange={(checked) => setAutoRefreshEnabled(Boolean(checked))}
            />
            <div>
              <p className="font-medium">Tự động làm mới tài khoản</p>
              <p className="text-xs text-stone-500 mt-0.5">
                Tự động kiểm tra và làm mới hạn mức token định kỳ mỗi 5 phút (như 9router).
              </p>
            </div>
          </label>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 cursor-pointer">
            <Checkbox
              checked={Boolean((config as any)?.rtk_enabled ?? true)}
              onCheckedChange={(checked) => setField("rtk_enabled", Boolean(checked))}
            />
            <div>
              <p className="font-medium">RTK - Nén tin nhắn (ChatGPT)</p>
              <p className="text-xs text-stone-500 mt-0.5">
                Giảm 60-90% payload cho ChatGPT. Mặc định bật.
              </p>
            </div>
          </label>
          <label className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 text-sm text-stone-700 cursor-pointer">
            <Checkbox
              checked={Boolean((config as any)?.rtk_other_enabled ?? false)}
              onCheckedChange={(checked) => setField("rtk_other_enabled", Boolean(checked))}
            />
            <div>
              <p className="font-medium">RTK - Nén tin nhắn (AI khác)</p>
              <p className="text-xs text-stone-500 mt-0.5">
                Áp dụng RTK cho OpenCode, Gemini, Codex, NVIDIA. Mặc định tắt.
              </p>
            </div>
          </label>
          <div className="space-y-2 rounded-xl border border-stone-200 bg-white px-4 py-3">
            <label className="text-sm font-medium text-stone-700">Model mặc định cho Web Session (OpenAI API)</label>
            <p className="text-xs text-stone-500">Dùng khi chatgpt/auto route qua api.openai.com. Ví dụ: gpt-4o, gpt-4.1-mini.</p>
            <Input
              value={String((config as any)?.openai_default_model ?? "gpt-4o")}
              onChange={(e) => setField("openai_default_model", e.target.value)}
              placeholder="gpt-4o"
              className="h-10 rounded-xl border-stone-200 bg-white"
            />
          </div>
          <div className="space-y-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
            <div>
              <label className="text-sm text-stone-700">Mức độ nhật ký console</label>
              <p className="mt-1 text-xs text-stone-500">Nếu không chọn, mặc định sẽ là info / warning / error.</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {logLevelOptions.map((level) => (
                <label key={level} className="flex items-center gap-2 text-sm capitalize text-stone-700">
                  <Checkbox
                    checked={Boolean(config?.log_levels?.includes(level))}
                    onCheckedChange={(checked) => setLogLevel(level, Boolean(checked))}
                  />
                  {level}
                </label>
              ))}
            </div>
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm text-stone-700">Chỉ thị bổ sung toàn cầu (System Prompt)</label>
            <Textarea
              value={String(config?.global_system_prompt || "")}
              onChange={(event) => setGlobalSystemPrompt(event.target.value)}
              placeholder="Ví dụ: Đầu tiên hãy xác định xem prompt của người dùng có tuân thủ quy định hay không; từ chối trả lời khi gặp các yêu cầu vi phạm pháp luật, khiêu dâm, bạo lực, thù hận, v.v."
              className="min-h-28 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
            />
            <p className="text-xs text-stone-500">Mỗi yêu cầu sẽ được chèn dưới dạng tin nhắn system, có thể được sử dụng để kiểm duyệt prompt của người dùng, tránh nội dung vi phạm, thống nhất các ràng buộc hành vi của mô hình hoặc thiết lập vai trò cố định.</p>
          </div>
          <div className="space-y-2 md:col-span-2">
            <label className="text-sm text-stone-700">Từ nhạy cảm</label>
            <Textarea
              value={(config?.sensitive_words || []).join("\n")}
              onChange={(event) => setSensitiveWordsText(event.target.value)}
              placeholder="Mỗi dòng một từ, nếu khớp sẽ từ chối"
              className="min-h-28 rounded-xl border-stone-200 bg-white font-mono text-xs shadow-none"
            />
            <p className="text-xs text-stone-500">Chỉ cần yêu cầu của người dùng chứa bất kỳ từ nhạy cảm nào, yêu cầu đó sẽ bị từ chối trực tiếp.</p>
          </div>
          <div className="space-y-4 rounded-xl border border-stone-200 bg-white px-4 py-3 md:col-span-2">
            <label className="flex items-center gap-3 text-sm text-stone-700">
              <Checkbox
                checked={Boolean(config?.ai_review?.enabled)}
                onCheckedChange={(checked) => setAIReviewField("enabled", Boolean(checked))}
              />
              Bật kiểm duyệt AI
            </label>
            <p className="text-xs leading-6 text-stone-500">
              Sau khi bật, mô hình kiểm duyệt sẽ được gọi trước khi yêu cầu được gửi đến tài khoản tạo ảnh. Nếu kiểm duyệt không đạt, yêu cầu sẽ bị từ chối trực tiếp, giúp giảm nguy cơ tài khoản bị khóa do các prompt vi phạm.
            </p>
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <label className="text-sm text-stone-700">Base URL</label>
                <Input value={String(config?.ai_review?.base_url || "")} onChange={(event) => setAIReviewField("base_url", event.target.value)} placeholder="https://api.openai.com" className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">API Key</label>
                <Input value={String(config?.ai_review?.api_key || "")} onChange={(event) => setAIReviewField("api_key", event.target.value)} placeholder="sk-..." className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
              <div className="space-y-2">
                <label className="text-sm text-stone-700">Model</label>
                <Input value={String(config?.ai_review?.model || "")} onChange={(event) => setAIReviewField("model", event.target.value)} placeholder="gpt-5.4-mini" className="h-10 rounded-xl border-stone-200 bg-white" />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-sm text-stone-700">Prompt kiểm duyệt</label>
              <Textarea value={String(config?.ai_review?.prompt || "")} onChange={(event) => setAIReviewField("prompt", event.target.value)} placeholder="Xác định xem yêu cầu của người dùng có được phép hay không. Chỉ trả lời ALLOW hoặc REJECT." className="min-h-24 rounded-xl border-stone-200 bg-white text-xs shadow-none" />
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <Button
            className="h-10 rounded-[12px] bg-indigo-600 px-5 text-white hover:bg-indigo-700 shadow-md shadow-indigo-200"
            onClick={() => void saveConfig()}
            disabled={isSavingConfig}
          >
            {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
            Lưu
          </Button>
        </div>
      </div>
    </div>
  );
}


