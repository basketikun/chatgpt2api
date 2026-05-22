"use client";

import { useState } from "react";
import { Link2, LoaderCircle, PlugZap, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { testProxy, type ProxyTestResult } from "@/lib/api";

import { useSettingsStore } from "../store";

export function ProxySettingsCard() {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<ProxyTestResult | null>(null);
  const config = useSettingsStore((state) => state.config);
  const isLoadingConfig = useSettingsStore((state) => state.isLoadingConfig);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setProxy = useSettingsStore((state) => state.setProxy);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  const proxy = config?.proxy ?? "";

  const handleTest = async () => {
    const candidate = proxy.trim();
    if (!candidate) {
      toast.error("请先填写Địa chỉ proxy");
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    try {
      const data = await testProxy(candidate);
      setTestResult(data.result);
      if (data.result.ok) {
        toast.success(`代理可用（${data.result.latency_ms} ms，HTTP ${data.result.status}）`);
      } else {
        toast.error(`代理不可用：${data.result.error ?? "未知错误"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Kiểm tra proxythất bại");
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <Card className="rounded-2xl card-3d card-tint-sky">
      <CardContent className="space-y-6 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
              <Link2 className="size-5 text-stone-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">Proxy toàn cục</h2>
              <p className="text-sm text-stone-500">Cấu hình proxy cho các request đi ra, lưu lại có hiệu lực ngay.</p>
            </div>
          </div>
          <Badge variant={proxy.trim() ? "success" : "secondary"} className="w-fit rounded-md px-2.5 py-1">
            {proxy.trim() ? "Đã cấu hình" : "Chưa cấu hình"}
          </Badge>
        </div>

        {isLoadingConfig ? (
          <div className="flex items-center justify-center py-10">
            <LoaderCircle className="size-5 animate-spin text-stone-500" />
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <label className="text-sm font-medium text-stone-700">Địa chỉ proxy</label>
              <Input
                value={proxy}
                onChange={(event) => {
                  setProxy(event.target.value);
                  setTestResult(null);
                }}
                placeholder="http://user:pass@127.0.0.1:7890"
                className="h-11 rounded-xl border-stone-200 bg-white"
              />
              <p className="text-sm text-stone-500">
                Để trống nếu không dùng proxy. Nhập địa chỉ đầy đủ, VD: `http://127.0.0.1:7890`、`http://tên:mật khẩu@127.0.0.1:7890` 或 `socks5://127.0.0.1:7890`。
              </p>
            </div>

            {testResult ? (
              <div
                className={`rounded-xl border px-4 py-3 text-sm leading-6 ${
                  testResult.ok
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-rose-200 bg-rose-50 text-rose-800"
                }`}
              >
                {testResult.ok
                  ? `代理可用：HTTP ${testResult.status}，用时 ${testResult.latency_ms} ms`
                  : `代理不可用：${testResult.error ?? "未知错误"}（用时 ${testResult.latency_ms} ms）`}
              </div>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                className="h-10 rounded-xl border-stone-200 bg-white px-5 text-stone-700"
                onClick={() => void handleTest()}
                disabled={isTesting || isLoadingConfig}
              >
                {isTesting ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
                Kiểm tra proxy
              </Button>
              <Button
                className="h-10 rounded-xl bg-stone-900 px-5 text-white hover:bg-stone-800"
                onClick={() => void saveConfig()}
                disabled={isSavingConfig}
              >
                {isSavingConfig ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
                Lưu
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}


