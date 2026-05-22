"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Bell, Search, Sun, Moon } from "lucide-react";
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
  const [darkMode, setDarkMode] = useState(false);
  const [session, setSession] = useState<StoredAuthSession | null | undefined>(undefined);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
      setDarkMode(true);
      document.documentElement.classList.add("dark");
    }
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
      <div className="flex-1 flex flex-col min-h-screen" style={{ marginLeft: sidebarCollapsed ? "68px" : "250px", transition: "margin-left 0.25s ease" }}>
        {/* Top Header Bar */}
        <header className="sticky top-0 z-30 h-14 bg-[var(--card)] border-b border-[var(--border)] flex items-center justify-between px-4 sm:px-6 shadow-sm">
          <h1 className="text-lg font-semibold text-[var(--foreground)] tracking-tight">{pageTitle}</h1>
          <div className="flex items-center gap-3">
            {/* Theme toggle */}
            <button onClick={toggleDarkMode} className="p-2 rounded-lg hover:bg-[var(--secondary)] transition-colors" title="Toggle theme">
              {darkMode ? <Sun className="size-4 text-amber-400" /> : <Moon className="size-4 text-slate-500" />}
            </button>
            {/* User info */}
            <div className="flex items-center gap-2 pl-3 border-l border-[var(--border)]">
              <div className="size-8 rounded-full bg-[var(--primary)] flex items-center justify-center text-white text-xs font-bold">
                {displayName.charAt(0).toUpperCase()}
              </div>
              <div className="hidden sm:block">
                <div className="text-sm font-medium text-[var(--foreground)] leading-tight">{displayName}</div>
              </div>
              <button onClick={handleLogout} className="text-xs text-[var(--muted-foreground)] hover:text-[var(--destructive)] ml-1">
                Logout
              </button>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
