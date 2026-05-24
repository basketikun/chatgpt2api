"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Sun, Moon, Sparkles } from "lucide-react";
import { usePathname } from "next/navigation";
import { getValidatedAuthSession } from "@/lib/auth-session";
import { clearStoredAuthSession, type StoredAuthSession } from "@/store/auth";
import { useRouter } from "next/navigation";

const pageTitles: Record<string, string> = {
  "/": "Dashboard",
  "/accounts": "Quản lý tài khoản",
  "/providers": "Nhà cung cấp AI",
  "/models": "Models",
  "/combos": "Combos",
  "/mcp": "MCP Servers",
  "/chat": "Chat",
  "/image": "Vẽ ảnh",
  "/image-manager": "Quản lý ảnh",
  "/video": "Video",
  "/video-manager": "Quản lý video",
  "/search": "Tìm kiếm",
  "/backup": "Sao lưu",
  "/settings": "Cài đặt",
  "/logs": "Nhật ký",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(true);
  const [session, setSession] = useState<StoredAuthSession | null | undefined>(undefined);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    // 2026 default: dark unless explicitly light
    const useDark = stored !== "light";
    setDarkMode(useDark);
    document.documentElement.classList.toggle("dark", useDark);
    getValidatedAuthSession().then(s => setSession(s));
  }, []);

  const toggleDarkMode = () => {
    setDarkMode(prev => {
      const next = !prev;
      document.documentElement.classList.toggle("dark", next);
      localStorage.setItem("theme", next ? "dark" : "light");
      return next;
    });
  };

  const handleLogout = async () => {
    await clearStoredAuthSession();
    router.replace("/login");
  };

  const pageTitle = pageTitles[pathname] || "chatgpt2api";
  const displayName = session?.name?.trim() || "Admin";

  if (pathname === "/login") return <>{children}</>;

  return (
    <div className="flex min-h-screen bg-[var(--background)]">
      {/* Sidebar */}
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />

      {/* Main area */}
      <div
        className="flex-1 flex flex-col min-h-screen"
        style={{
          marginLeft: sidebarCollapsed ? "68px" : "250px",
          transition: "margin-left 0.25s ease",
        }}
      >
        {/* Glass top header */}
        <header className="glass-strong sticky top-0 z-30 h-14 flex items-center justify-between px-4 sm:px-6 border-b border-[var(--border)]/40 !rounded-none">
          <div className="flex items-center gap-3 min-w-0">
            <Sparkles className="size-4 text-[var(--neon-cyan)] shrink-0 dot-glow" />
            <h1 className="text-[15px] font-semibold tracking-tight gradient-text truncate">
              {pageTitle}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={toggleDarkMode}
              className="size-9 inline-flex items-center justify-center rounded-[10px] hover:bg-[var(--secondary)] transition-colors"
              title="Toggle theme"
            >
              {darkMode ? (
                <Sun className="size-4 text-[var(--neon-amber)]" />
              ) : (
                <Moon className="size-4 text-[var(--muted-foreground)]" />
              )}
            </button>
            <div className="flex items-center gap-2 pl-2 ml-1 border-l border-[var(--border)]/50">
              <div
                className="size-8 rounded-full flex items-center justify-center text-[11px] font-bold text-[var(--primary-foreground)]"
                style={{
                  background:
                    "linear-gradient(135deg, var(--neon-cyan), var(--neon-magenta))",
                }}
              >
                {displayName.charAt(0).toUpperCase()}
              </div>
              <div className="hidden sm:block">
                <div className="text-[13px] font-medium text-[var(--foreground)] leading-tight">
                  {displayName}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="text-[11px] text-[var(--muted-foreground)] hover:text-[var(--destructive)] ml-1 transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
