"use client";

import { Save, MessageCircle, Cloud } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { useSettingsStore } from "../store";

export function TelegramCloudflareCard() {
  const config = useSettingsStore((state) => state.config);
  const isSavingConfig = useSettingsStore((state) => state.isSavingConfig);
  const setField = useSettingsStore((state) => state.setField);
  const saveConfig = useSettingsStore((state) => state.saveConfig);

  return (
    <Card>
      <CardContent className="space-y-4 pt-4">
        {/* Telegram Section */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <MessageCircle className="size-4 text-blue-500" /> Telegram Bot
          </h4>
          <div>
            <label className="text-xs text-muted-foreground">Bot Token (từ @BotFather)</label>
            <Input
              value={String(config?.telegram_bot_token || "")}
              onChange={(e) => setField("telegram_bot_token", e.target.value)}
              placeholder="123456:ABC-DEF1234ghikl..."
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Webhook URL</label>
            <Input
              value={String(config?.telegram_webhook_url || "")}
              onChange={(e) => setField("telegram_webhook_url", e.target.value)}
              placeholder="https://your-domain.com"
            />
            <p className="text-[10px] text-muted-foreground mt-1">
              Domain cần HTTPS (qua Cloudflare Tunnel hoặc public IP)
            </p>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">AI Model cho Telegram</label>
            <Input
              value={String(config?.telegram_ai_model || "")}
              onChange={(e) => setField("telegram_ai_model", e.target.value)}
              placeholder="cx/auto (để trống = dùng mặc định)"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Chat IDs (cách nhau dấu phẩy, trống = cho phép tất cả)</label>
            <Input
              value={(config?.telegram_chat_ids || []).join(", ")}
              onChange={(e) => {
                const ids = e.target.value.split(",").map((s: string) => s.trim()).filter(Boolean);
                setField("telegram_chat_ids", ids);
              }}
              placeholder="123456789, 987654321"
            />
          </div>
        </div>

        <hr className="border-border" />

        {/* Cloudflare Tunnel Section */}
        <div className="space-y-3">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <Cloud className="size-4 text-orange-500" /> Cloudflare Tunnel
          </h4>
          <div>
            <label className="text-xs text-muted-foreground">Tunnel Token</label>
            <Input
              value={String(config?.cloudflare_tunnel_token || "")}
              onChange={(e) => setField("cloudflare_tunnel_token", e.target.value)}
              placeholder="eyJhIjoi..."
              type="password"
            />
            <p className="text-[10px] text-muted-foreground mt-1">
              Paste token từ Cloudflare Zero Trust → Tunnels. Lưu xong tunnel tự chạy.
            </p>
          </div>
        </div>

        <Button
          onClick={async () => {
            await saveConfig();
            toast.success("Đã lưu cấu hình Telegram & Cloudflare");
          }}
          disabled={isSavingConfig}
          className="w-full"
          size="sm"
        >
          <Save className="size-3.5 mr-1.5" />
          {isSavingConfig ? "Đang lưu..." : "Lưu cấu hình"}
        </Button>
      </CardContent>
    </Card>
  );
}
