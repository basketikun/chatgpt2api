"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  LayoutDashboard, Users, Cpu, Combine, ImageIcon, Search, Archive, Settings,
  LogOut, ChevronLeft, ChevronRight, Sparkles, PanelLeftClose, PanelLeft,
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
        "fixed left-0 top-0 z-50 flex h-screen flex-col bg-[var(--sidebar)] text-[var(--sidebar-foreground)]",
        "transition-[width] duration-200 ease-out",
        collapsed ? "w-[68px]" : "w-[250px]",
      )}
    >
      {/* Logo */}
      <div className={cn("flex h-14 items-center border-b border-[var(--sidebar-border)]", collapsed ? "justify-center px-2" : "px-4 gap-2.5")}>
        <Link href="/" className="flex items-center gap-2.5 no-underline shrink-0">
          <div className="flex size-8 items-center justify-center rounded-lg bg-[var(--sidebar-primary)] text-white">
            <LayoutDashboard className="size-4" />
          </div>
          {!collapsed && <span className="text-sm font-bold text-white tracking-tight">chatgpt2api</span>}
        </Link>
        <button onClick={onToggle} className={cn(
          "rounded-md p-1 text-[var(--sidebar-foreground)]/50 hover:text-[var(--sidebar-foreground)] hover:bg-[var(--sidebar-accent)] transition",
          collapsed ? "absolute -right-2.5 top-3.5 bg-[var(--sidebar)] border border-[var(--sidebar-border)] rounded-full size-5 flex items-center justify-center" : "ml-auto"
        )}>
          {collapsed ? <ChevronRight className="size-3" /> : <PanelLeftClose className="size-3.5" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {visibleItems.map(item => {
          const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href}
              className={cn(
                "flex items-center rounded-md transition-colors duration-150",
                collapsed ? "justify-center py-2.5" : "gap-2.5 px-3 py-2",
                active
                  ? "bg-[var(--sidebar-primary)] text-white font-medium"
                  : "text-[var(--sidebar-foreground)]/70 hover:bg-[var(--sidebar-accent)] hover:text-white font-normal",
                "text-[13px]",
              )}
              title={collapsed ? t(item.labelKey) : undefined}
            >
              <Icon className="size-[18px] shrink-0" />
              {!collapsed && <span className="truncate">{t(item.labelKey)}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-[var(--sidebar-border)] p-3">
        {!collapsed && (
          <div className="flex items-center gap-2.5 mb-2 px-1">
            <div className="size-7 rounded-full bg-[var(--sidebar-primary)] flex items-center justify-center text-white text-xs font-bold">
              {displayName.charAt(0).toUpperCase()}
            </div>
            <div className="text-xs overflow-hidden">
              <div className="text-white font-medium truncate">{displayName}</div>
              <div className="text-[var(--sidebar-foreground)]/50">{isAdmin ? "Admin" : "User"} · v{webConfig.appVersion}</div>
            </div>
          </div>
        )}
        <button onClick={handleLogout} className={cn(
          "flex items-center rounded-md text-[var(--sidebar-foreground)]/60 hover:text-red-400 hover:bg-red-400/10 transition-colors w-full text-xs",
          collapsed ? "justify-center py-2" : "gap-2 px-2 py-1.5"
        )}>
          <LogOut className="size-3.5 shrink-0" />
          {!collapsed && "Đăng xuất"}
        </button>
      </div>
    </aside>
  );
}
