"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import { HeaderActions } from "@/components/header-actions";
import { Sheet, SheetClose, SheetContent, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import webConfig from "@/constants/common-env";
import { getValidatedAuthSession } from "@/lib/auth-session";
import { cn } from "@/lib/utils";
import { clearStoredAuthSession, type StoredAuthSession } from "@/store/auth";

const adminNavItems = [
  { href: "/image", label: "Draw" },
  { href: "/accounts", label: "Account Pool" },
  { href: "/register", label: "Register" },
  { href: "/image-manager", label: "Images" },
  { href: "/logs", label: "Logs" },
  { href: "/debug", label: "Debug" },
  { href: "/settings", label: "Settings" },
];

const userNavItems = [{ href: "/image", label: "Draw" }];

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<StoredAuthSession | null | undefined>(undefined);

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

      const storedSession = await getValidatedAuthSession();
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

  if (pathname === "/login" || session === undefined || !session) {
    return null;
  }

  const navItems = session.role === "admin" ? adminNavItems : userNavItems;
  const roleLabel = session.role === "admin" ? "Admin" : "User";
  const displayName = session.name.trim() || roleLabel;
  const baseUrl = webConfig.apiUrl.replace(/\/$/, "") || window.location.origin;
  const canvasHref = `https://infinite-canvas-cpco.onrender.com?apiKey=${encodeURIComponent(session.key)}&baseUrl=${encodeURIComponent(baseUrl)}`;
  const canvasItem = { href: canvasHref, label: "Infinite Canvas", external: true };
  const allNavItems = [canvasItem, ...navItems.map((item) => ({ ...item, external: false }))];

  return (
    <header className="border-b border-stone-100/50 dark:border-white/10">
      <div className="flex min-h-12 flex-col gap-1 px-3 py-2 sm:h-12 sm:flex-row sm:items-center sm:justify-between sm:gap-3 sm:px-6 sm:py-0">
        <div className="flex items-center justify-between gap-2 sm:justify-start sm:gap-3">
          <Sheet>
            <SheetTrigger className="inline-flex size-8 items-center justify-center text-stone-700 transition hover:text-stone-950 sm:hidden dark:text-stone-200 dark:hover:text-white">
              <Menu className="size-4" />
              <span className="sr-only">Open navigation</span>
            </SheetTrigger>
            <SheetContent side="left">
              <SheetHeader>
                <SheetTitle>chatgpt2api</SheetTitle>
                <span className="text-xs text-stone-500 dark:text-stone-400">{roleLabel} · {displayName}</span>
              </SheetHeader>
              <nav className="mt-8 flex flex-col gap-1">
                {allNavItems.map((item) => {
                  const active = !item.external && pathname === item.href;
                  const className = cn(
                    "flex items-center rounded-xl px-3 py-2.5 text-sm font-medium transition",
                    active ? "bg-stone-950 text-white dark:bg-white dark:text-stone-950" : "text-stone-600 hover:bg-stone-100 hover:text-stone-950 dark:text-stone-300 dark:hover:bg-white/10 dark:hover:text-white",
                  );
                  return item.external ? (
                    <a key={item.href} href={item.href} target="_blank" rel="noreferrer" className={className}>{item.label}</a>
                  ) : (
                    <SheetClose asChild key={item.href}>
                      <Link href={item.href} className={className}>{item.label}</Link>
                    </SheetClose>
                  );
                })}
              </nav>
              <SheetFooter>
                <button
                  type="button"
                  className="rounded-xl border border-stone-200 px-3 py-2.5 text-left text-sm font-medium text-stone-500 transition hover:text-stone-950 dark:border-white/10 dark:text-stone-300 dark:hover:text-white"
                  onClick={() => void handleLogout()}
                >
                  Logout
                </button>
              </SheetFooter>
            </SheetContent>
          </Sheet>
          <Link
            href="/image"
            className="shrink-0 py-1 text-[15px] font-bold tracking-tight text-stone-950 transition hover:text-stone-700 dark:text-stone-50 dark:hover:text-white"
          >
            chatgpt2api
          </Link>
          <HeaderActions className="ml-auto sm:hidden" showGithubText={false} />
        </div>
        <nav className="hide-scrollbar -mx-1 hidden min-w-0 flex-1 gap-1 overflow-x-auto px-1 sm:mx-0 sm:flex sm:justify-center sm:gap-8 sm:overflow-visible sm:px-0">
          <a
            href={canvasHref}
            target="_blank"
            rel="noreferrer"
            className="relative shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[13px] font-medium text-stone-500 transition hover:text-stone-900 sm:rounded-none sm:px-0 sm:text-[15px] dark:text-stone-400 dark:hover:text-stone-100"
          >
            Infinite Canvas
          </a>
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[13px] font-medium transition sm:rounded-none sm:px-0 sm:text-[15px]",
                  active
                    ? "bg-stone-950 text-white sm:bg-transparent sm:font-semibold sm:text-stone-950 dark:bg-white dark:text-stone-950 dark:sm:bg-transparent dark:sm:text-white"
                    : "text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100",
                )}
              >
                {item.label}
                {active ? <span className="absolute inset-x-0 -bottom-[1px] hidden h-0.5 bg-stone-950 dark:bg-white sm:block" /> : null}
              </Link>
            );
          })}
        </nav>
        <div className="hidden items-center justify-end gap-2 sm:flex sm:gap-3">
          <HeaderActions />
          <span className="hidden rounded-md bg-stone-100 px-2 py-1 text-[10px] font-medium text-stone-500 dark:bg-white/8 dark:text-stone-300 sm:inline-block sm:text-[11px]">
            {roleLabel} · {displayName}
          </span>
          <button
            type="button"
            className="py-1 text-xs text-stone-400 transition hover:text-stone-700 dark:text-stone-500 dark:hover:text-stone-200 sm:text-sm"
            onClick={() => void handleLogout()}
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
