"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  LayoutDashboard, Users, Cpu, Combine, ImageIcon, Search, Archive, Settings,
  LogOut, ChevronRight, Sparkles, PanelLeftClose,
  Video, Film, Plug, MessageSquare,
} from "lucide-react";
import webConfig from "@/constants/common-env";
import { getValidatedAuthSession } from "@/lib/auth-session";
import { cn } from "@/lib/utils";
import { useLangStore } from "@/store/lang";
import { translations, TranslationKey } from "@/lib/i18n";
import { clearStoredAuthSession, type StoredAuthSession } from "@/store/auth";

const navItems = [
  { href: "/",              labelKey: "nav_overview"       as TranslationKey, icon: LayoutDashboard },
  { href: "/accounts",      labelKey: "nav_accounts"       as TranslationKey, icon: Users },
  { href: "/providers",     labelKey: "nav_providers"      as TranslationKey, icon: Cpu },
  { href: "/models",         labelKey: "nav_models"         as TranslationKey, icon: Sparkles },
  { href: "/combos",         labelKey: "nav_combos"         as TranslationKey, icon: Combine },
  { href: "/mcp",            labelKey: "nav_mcp"            as TranslationKey, icon: Plug },
  { href: "/chat",           labelKey: "nav_chat"           as TranslationKey, icon: MessageSquare },
  { href: "/image",          labelKey: "nav_image"          as TranslationKey, icon: ImageIcon },
  { href: "/image-manager",  labelKey: "nav_imageLibrary"   as TranslationKey, icon: Archive },
  { href: "/video",          labelKey: "nav_video"          as TranslationKey, icon: Video },
  { href: "/video-manager",  labelKey: "nav_videoLibrary"   as TranslationKey, icon: Film },
  { href: "/search",         labelKey: "nav_search"         as TranslationKey, icon: Search },
  { href: "/backup",         labelKey: "nav_backup"         as TranslationKey, icon: Archive },
  { href: "/settings",       labelKey: "nav_settings"       as TranslationKey, icon: Settings },
];

const adminOnlyPaths = ["/accounts","/providers","/models","/combos","/mcp","/image-manager","/video-manager","/search","/backup","/settings"];

type SidebarProps = { collapsed: boolean; onToggle: () => void };

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { lang } = useLangStore();
  const t = (key: TranslationKey) => translations[lang][key] || key;
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<StoredAuthSession | null | undefined>(undefined);

  useEffect(() => {
    let active = true;
    (async () => {
      if (pathname === "/login") { setSession(null); return; }
      const s = await getValidatedAuthSession();
      if (active) setSession(s);
    })();
    return () => { active = false; };
  }, [pathname]);

  const handleLogout = useCallback(async () => {
    await clearStoredAuthSession();
    router.replace("/login");
  }, [router]);

  if (pathname === "/login" || session === undefined || !session) return null;

  const isAdmin = session.role === "admin";
  const displayName = session.name?.trim() || (isAdmin ? "Admin" : "User");
  const visibleItems = isAdmin ? navItems : navItems.filter(i => !adminOnlyPaths.includes(i.href));

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-50 flex h-screen flex-col glass-strong text-[var(--sidebar-foreground)]",
        "transition-[width] duration-200 ease-out !rounded-none border-r border-[var(--sidebar-border)] border-l-0 border-t-0 border-b-0",
        collapsed ? "w-[68px]" : "w-[250px]",
      )}
      style={{ background: "var(--sidebar)" }}
    >
      {/* Logo */}
      <div className={cn("flex h-14 items-center border-b border-[var(--sidebar-border)] shrink-0", collapsed ? "justify-center px-2" : "px-4 gap-2.5")}>
        <Link href="/" className="flex items-center gap-2.5 no-underline shrink-0">
          <div
            className="flex size-9 items-center justify-center rounded-[12px] text-white relative overflow-hidden"
            style={{
              background: "linear-gradient(135deg, var(--neon-cyan), var(--neon-magenta))",
              boxShadow: "0 0 18px color-mix(in srgb, var(--neon-cyan) 35%, transparent)",
            }}
          >
            <Sparkles className="size-4 relative z-10" />
          </div>
          {!collapsed && (
            <span className="text-[14px] font-bold tracking-tight gradient-text">
              chatgpt2api
            </span>
          )}
        </Link>
        <button
          onClick={onToggle}
          className={cn(
            "rounded-md p-1 text-[var(--sidebar-foreground)]/50 hover:text-[var(--neon-cyan)] hover:bg-[var(--sidebar-accent)] transition",
            collapsed
              ? "absolute -right-2.5 top-3.5 bg-[var(--card)] border border-[var(--border)] rounded-full size-5 flex items-center justify-center"
              : "ml-auto",
          )}
        >
          {collapsed ? <ChevronRight className="size-3" /> : <PanelLeftClose className="size-3.5" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-0.5">
        {visibleItems.map(item => {
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative flex items-center rounded-[10px] transition-all duration-200",
                collapsed ? "justify-center py-2.5" : "gap-2.5 px-3 py-2",
                "text-[13px]",
                active
                  ? "text-[var(--neon-cyan)] font-semibold"
                  : "text-[var(--sidebar-foreground)]/75 hover:text-[var(--sidebar-foreground)] font-normal hover:bg-[var(--sidebar-accent)]",
              )}
              style={
                active
                  ? {
                      background:
                        "linear-gradient(90deg, color-mix(in srgb, var(--neon-cyan) 18%, transparent), color-mix(in srgb, var(--neon-cyan) 4%, transparent))",
                      boxShadow:
                        "inset 0 0 0 1px color-mix(in srgb, var(--neon-cyan) 25%, transparent)",
                    }
                  : undefined
              }
              title={collapsed ? t(item.labelKey) : undefined}
            >
              {/* Active indicator bar */}
              {active && (
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full"
                  style={{
                    background:
                      "linear-gradient(180deg, var(--neon-cyan), var(--neon-magenta))",
                    boxShadow: "0 0 12px var(--neon-cyan)",
                  }}
                />
              )}
              <Icon className={cn("size-[18px] shrink-0", active && "drop-shadow-[0_0_6px_var(--neon-cyan)]")} />
              {!collapsed && <span className="truncate">{t(item.labelKey)}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-[var(--sidebar-border)] p-3 shrink-0">
        {!collapsed && (
          <div className="flex items-center gap-2.5 mb-2 px-1">
            <div
              className="size-7 rounded-full flex items-center justify-center text-white text-[11px] font-bold"
              style={{
                background:
                  "linear-gradient(135deg, var(--neon-cyan), var(--neon-magenta))",
              }}
            >
              {displayName.charAt(0).toUpperCase()}
            </div>
            <div className="text-[11px] overflow-hidden">
              <div className="text-[var(--foreground)] font-medium truncate">{displayName}</div>
              <div className="text-[var(--sidebar-foreground)]/55">
                {isAdmin ? "Admin" : "User"} · v{webConfig.appVersion}
              </div>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          className={cn(
            "flex items-center rounded-md text-[var(--sidebar-foreground)]/60 hover:text-red-400 hover:bg-red-400/10 transition-colors w-full text-xs",
            collapsed ? "justify-center py-2" : "gap-2 px-2 py-1.5",
          )}
        >
          <LogOut className="size-3.5 shrink-0" />
          {!collapsed && "Đăng xuất"}
        </button>
      </div>
    </aside>
  );
}
