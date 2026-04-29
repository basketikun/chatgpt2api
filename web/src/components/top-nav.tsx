"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Github, Moon, Sun } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import webConfig from "@/constants/common-env";
import { clearStoredAuthSession, getStoredAuthSession, type StoredAuthSession } from "@/store/auth";
import { cn } from "@/lib/utils";

const adminNavItems = [
  { href: "/image", label: "画图" },
  { href: "/accounts", label: "号池管理" },
  { href: "/register", label: "注册机" },
  { href: "/image-manager", label: "图片管理" },
  { href: "/logs", label: "日志管理" },
  { href: "/settings", label: "设置" },
];

const userNavItems = [{ href: "/image", label: "画图" }];

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<StoredAuthSession | null | undefined>(undefined);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = typeof window !== "undefined" ? window.localStorage.getItem("theme") : null;
    const initial = stored === "dark" ? "dark" : "light";
    setTheme(initial);
    document.documentElement.classList.toggle("dark", initial === "dark");
  }, []);

  useEffect(() => {
    let active = true;

    const load = async () => {
      if (pathname === "/login") {
        if (!active) {
          return;
        }
        setSession(null);
        return;
      }

      const storedSession = await getStoredAuthSession();
      if (!active) {
        return;
      }
      setSession(storedSession);
    };

    void load();
    return () => {
      active = false;
    };
  }, [pathname]);

  const handleLogout = async () => {
    await clearStoredAuthSession();
    router.replace("/login");
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    window.localStorage.setItem("theme", next);
  };

  if (pathname === "/login" || session === undefined || !session) {
    return null;
  }

  const navItems = session.role === "admin" ? adminNavItems : userNavItems;
  const roleLabel = session.role === "admin" ? "管理员" : "普通用户";

  return (
    <header className="sticky top-2 z-40 rounded-[22px] border border-white/70 bg-white/55 shadow-[0_18px_70px_-48px_rgba(28,25,23,0.45)] backdrop-blur-2xl dark:border-white/10 dark:bg-slate-950/45 dark:shadow-[0_24px_90px_-48px_rgba(2,6,23,0.95)]">
      <div className="flex min-h-12 flex-col gap-1 px-3 py-2 sm:h-12 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-6 sm:py-0">
        <div className="flex items-center justify-between gap-2 sm:justify-start sm:gap-3">
          <Link
            href="/image"
            className="shrink-0 py-1 text-[15px] font-bold tracking-tight text-stone-950 transition hover:text-stone-700 dark:bg-gradient-to-r dark:from-amber-200 dark:via-cyan-200 dark:to-violet-300 dark:bg-clip-text dark:text-transparent"
          >
            chatgpt2api
          </Link>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-full border border-transparent px-2 py-1 text-sm text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 dark:border-white/10 dark:bg-white/[0.04] dark:text-amber-200 dark:hover:border-amber-300/30 dark:hover:bg-amber-300/10 dark:hover:text-amber-100"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "切换到亮色模式" : "切换到暗色模式"}
          >
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            <span className="hidden md:inline">{theme === "dark" ? "亮色" : "暗色"}</span>
          </button>
          <a
            href="https://github.com/basketikun/chatgpt2api"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-sm text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 dark:text-slate-400 dark:hover:bg-white/[0.04] dark:hover:text-cyan-200"
            aria-label="GitHub repository"
          >
            <Github className="size-4" />
            <span className="hidden md:inline">GitHub</span>
          </a>
          <button
            type="button"
            className="ml-auto shrink-0 rounded-full px-2 py-1 text-xs text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 dark:text-slate-400 dark:hover:bg-white/[0.05] dark:hover:text-slate-100 sm:hidden"
            onClick={() => void handleLogout()}
          >
            退出
          </button>
        </div>
        <nav className="hide-scrollbar -mx-1 flex min-w-0 flex-1 gap-1 overflow-x-auto px-1 sm:mx-0 sm:justify-center sm:gap-8 sm:overflow-visible sm:px-0">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[13px] font-medium transition sm:rounded-none sm:px-0 sm:text-[15px]",
                  active
                    ? "bg-stone-950 text-white shadow-[0_12px_32px_-20px_rgba(28,25,23,0.55)] sm:bg-transparent sm:font-semibold sm:text-stone-950 sm:shadow-none dark:bg-gradient-to-r dark:from-amber-300 dark:via-cyan-300 dark:to-violet-300 dark:text-slate-950 dark:shadow-[0_16px_40px_-24px_rgba(34,211,238,0.85)] sm:dark:bg-clip-text sm:dark:text-transparent sm:dark:shadow-none"
                    : "text-stone-500 hover:text-stone-900 dark:text-slate-400 dark:hover:text-slate-100",
                )}
              >
                {item.label}
                {active ? <span className="absolute inset-x-0 -bottom-[1px] hidden h-0.5 bg-stone-950 dark:bg-gradient-to-r dark:from-amber-300 dark:via-cyan-300 dark:to-violet-300 sm:block" /> : null}
              </Link>
            );
          })}
        </nav>
        <div className="hidden items-center justify-end gap-2 sm:flex sm:gap-3">
          <span className="hidden rounded-md bg-stone-100 px-2 py-1 text-[10px] font-medium text-stone-500 dark:border dark:border-white/10 dark:bg-white/[0.055] dark:text-slate-300 sm:inline-block sm:text-[11px]">
            {roleLabel}
          </span>
          <span className="hidden rounded-md bg-stone-100 px-2 py-1 text-[10px] font-medium text-stone-500 dark:border dark:border-white/10 dark:bg-white/[0.055] dark:text-slate-300 sm:inline-block sm:text-[11px]">
            v{webConfig.appVersion}
          </span>
          <button
            type="button"
            className="rounded-full px-2 py-1 text-xs text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 dark:text-slate-400 dark:hover:bg-white/[0.05] dark:hover:text-slate-100 sm:text-sm"
            onClick={() => void handleLogout()}
          >
            退出
          </button>
        </div>
      </div>
    </header>
  );
}
