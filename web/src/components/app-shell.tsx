"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { useLangStore } from "@/store/lang";
import { Sun, Moon, Monitor } from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { lang } = useLangStore();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
      setDarkMode(true);
      document.documentElement.classList.add("dark");
    }
  }, []);

  const toggleDarkMode = () => {
    setDarkMode(prev => {
      const next = !prev;
      if (next) {
        document.documentElement.classList.add("dark");
        localStorage.setItem("theme", "dark");
      } else {
        document.documentElement.classList.remove("dark");
        localStorage.setItem("theme", "light");
      }
      return next;
    });
  };

  return (
    <div className="flex min-h-screen bg-[var(--background)] text-[var(--foreground)] font-sans transition-colors duration-300">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />
      <main
        className="flex-1 overflow-x-hidden transition-[padding-left] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]"
        style={{
          paddingLeft: sidebarCollapsed ? "72px" : "16rem",
        }}
      >
        <div className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </div>
      </main>
      {/* Floating theme toggle — micro-interaction */}
      <button
        onClick={toggleDarkMode}
        className="group fixed bottom-6 right-6 z-50 flex size-11 items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--card)] shadow-lg transition-all duration-300 hover:scale-110 hover:shadow-xl active:scale-95 backdrop-blur-sm"
        title={darkMode ? "Light mode" : "Dark mode"}
        aria-label="Toggle theme"
      >
        <span className="transition-transform duration-300 group-hover:rotate-12">
          {darkMode ? <Sun className="size-5 text-amber-400" /> : <Moon className="size-5 text-indigo-500" />}
        </span>
      </button>
    </div>
  );
}
