"use client";

import { useEffect, useRef } from "react";
import { LoaderCircle, Settings, KeyRound, Cpu, Zap, Link, Archive, Plug } from "lucide-react";

import { useAuthGuard } from "@/lib/use-auth-guard";
import { SettingsSection } from "@/components/settings-section";

import { BackupSettingsCard } from "./components/backup-settings-card";
import { HACard } from "./components/ha-card";
import { ConfigCard } from "./components/config-card";
import { GeminiCard } from "./components/gemini-card";
import { NvidiaNimCard } from "./components/nvidia-nim-card";
import { CustomProvidersCard } from "./components/custom-providers-card";
import { CPAPoolDialog } from "./components/cpa-pool-dialog";
import { CPAPoolsCard } from "./components/cpa-pools-card";
import { ImportBrowserDialog } from "./components/import-browser-dialog";
import { SettingsHeader } from "./components/settings-header";
import { Sub2APIConnections } from "./components/sub2api-connections";
import { UserKeysCard } from "./components/user-keys-card";
import { useSettingsStore } from "./store";

function SettingsDataController() {
  const didLoadRef = useRef(false);
  const initialize = useSettingsStore((state) => state.initialize);
  const loadPools = useSettingsStore((state) => state.loadPools);
  const loadBackups = useSettingsStore((state) => state.loadBackups);
  const pools = useSettingsStore((state) => state.pools);
  const backupState = useSettingsStore((state) => state.backupState);

  useEffect(() => {
    if (didLoadRef.current) return;
    didLoadRef.current = true;
    void initialize();
  }, [initialize]);

  useEffect(() => {
    const hasRunningJobs = pools.some((pool) => {
      const status = pool.import_job?.status;
      return status === "pending" || status === "running";
    });
    if (!hasRunningJobs) return;
    const timer = window.setInterval(() => { void loadPools(true); }, 1500);
    return () => window.clearInterval(timer);
  }, [loadPools, pools]);

  useEffect(() => {
    if (!backupState?.running) return;
    const timer = window.setInterval(() => { void loadBackups(true); }, 3000);
    return () => window.clearInterval(timer);
  }, [backupState?.running, loadBackups]);

  return null;
}

function SettingsPageContent() {
  return (
    <>
      <SettingsDataController />
      <SettingsHeader />

      <section className="space-y-3">
        <SettingsSection
          title="Cấu hình hệ thống"
          description="Proxy, rate limit, tự động xóa tài khoản, system prompt, kiểm duyệt AI"
          icon={<Settings className="size-5" />}
          defaultOpen={true}
        >
          <ConfigCard />
        </SettingsSection>

        <SettingsSection
          title="Gemini AI Studio"
          description="Google Gemini với Google Search — miễn phí 15 RPM, hỗ trợ nhiều API key"
          icon={<span className="text-lg">🔮</span>}
        >
          <GeminiCard />
        </SettingsSection>

        <SettingsSection
          title="NVIDIA NIM"
          description="80+ model qua NVIDIA — chat, vision, tạo ảnh FLUX — build.nvidia.com"
          icon={<span className="text-lg">🟢</span>}
        >
          <NvidiaNimCard />
        </SettingsSection>

        <SettingsSection
          title="Custom Providers"
          description="Kết nối bất kỳ OpenAI-compatible API: DeepSeek, vLLM, LiteLLM, Gemini Server..."
          icon={<Link className="size-5" />}
        >
          <CustomProvidersCard />
        </SettingsSection>

        <SettingsSection
          title="Khóa người dùng"
          description="Tạo API key riêng cho người dùng thường — chỉ truy cập trang vẽ ảnh"
          icon={<KeyRound className="size-5" />}
        >
          <UserKeysCard />
        </SettingsSection>

        <SettingsSection
          title="CPA Pools"
          description="Quản lý pool Codex OAuth và token Codex Pro"
          icon={<Zap className="size-5" />}
        >
          <CPAPoolsCard />
        </SettingsSection>

        <SettingsSection
          title="Sub2API Connections"
          description="Kết nối tới các instance chatgpt2api khác để chia sẻ tải"
          icon={<Plug className="size-5" />}
        >
          <Sub2APIConnections />
        </SettingsSection>

        <SettingsSection
          title="Home Assistant"
          description="Kết nối HA để AI biết trạng thái nhà và điều khiển thiết bị"
          icon={<Archive className="size-5" />}
        >
          <HACard />
        </SettingsSection>

        <SettingsSection
          title="Sao lưu & Phục hồi"
          description="Tạo và quản lý bản sao lưu toàn bộ hệ thống"
          icon={<Archive className="size-5" />}
        >
          <BackupSettingsCard />
        </SettingsSection>
      </section>

      <CPAPoolDialog />
      <ImportBrowserDialog />
    </>
  );
}

export default function SettingsPage() {
  const { isCheckingAuth, session } = useAuthGuard(["admin"]);

  if (isCheckingAuth || !session || session.role !== "admin") {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <LoaderCircle className="size-5 animate-spin text-slate-400" />
      </div>
    );
  }

  return <SettingsPageContent />;
}
