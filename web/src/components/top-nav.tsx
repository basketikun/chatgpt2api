"use client";

import Link from "next/link";
import { Github } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

import webConfig from "@/constants/common-env";
import { clearStoredAuthKey } from "@/store/auth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/image", label: "画图" },
  { href: "/prompts", label: "提示词" },
  { href: "/accounts", label: "号池管理" },
  { href: "/settings", label: "设置" },
];

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    await clearStoredAuthKey();
    router.replace("/login");
  };

  if (pathname === "/login") {
    return null;
  }

  return (
    <header>
      <div className="flex h-12 items-start justify-between pt-1">
        <div className="flex flex-1 items-center gap-3">
          <Link
            href="/image"
            className="py-2 text-[15px] font-semibold tracking-tight text-stone-950 transition hover:text-stone-700"
          >
            chatgpt2api
          </Link>
          <a
            href="https://github.com/basketikun/chatgpt2api"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 py-2 text-sm text-stone-400 transition hover:text-stone-700"
            aria-label="GitHub repository"
          >
            <Github className="size-4" />
            <span>GitHub</span>
          </a>
        </div>
        <div className="flex justify-center gap-8">
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "relative py-2 text-[15px] font-medium transition",
                  active ? "font-semibold text-stone-950" : "text-stone-500 hover:text-stone-900",
                )}
              >
                {item.label}
                {active ? <span className="absolute inset-x-0 -bottom-[3px] h-0.5 bg-stone-950" /> : null}
              </Link>
            );
          })}
        </div>
        <div className="flex flex-1 items-center justify-end gap-3">
          <span className="rounded-md bg-stone-100 px-2 py-1 text-[11px] font-medium text-stone-500">
            v{webConfig.appVersion}
          </span>
          <button
            type="button"
            className="py-2 text-sm text-stone-400 transition hover:text-stone-700"
            onClick={() => void handleLogout()}
          >
            退出
          </button>
        </div>
      </div>
    </header>
  );
}
