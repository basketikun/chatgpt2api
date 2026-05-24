"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface SettingsSectionProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
  children: React.ReactNode;
}

export function SettingsSection({
  title,
  description,
  icon,
  defaultOpen = false,
  badge,
  children,
}: SettingsSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-[16px] border border-[var(--border)] bg-[var(--card)]",
        "transition-all duration-300",
        open
          ? "shadow-[0_8px_28px_color-mix(in_srgb,var(--neon-cyan)_10%,transparent),0_2px_8px_rgba(0,0,0,0.08)] border-[color-mix(in_srgb,var(--neon-cyan)_25%,var(--border))]"
          : "shadow-[0_1px_3px_rgba(0,0,0,0.06)]"
      )}
    >
      {/* Clickable header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center gap-4 px-5 py-4 text-left transition-colors duration-200",
          open
            ? "border-b border-[var(--border)]/60 bg-[color-mix(in_srgb,var(--neon-cyan)_4%,transparent)]"
            : "hover:bg-[var(--secondary)]/40"
        )}
      >
        {/* Icon avatar — neon gradient */}
        {icon && (
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-[12px] text-white shrink-0"
            style={{
              background: open
                ? "linear-gradient(135deg, var(--neon-cyan), var(--neon-magenta))"
                : "linear-gradient(135deg, color-mix(in srgb, var(--neon-cyan) 80%, transparent), color-mix(in srgb, var(--neon-magenta) 70%, transparent))",
              boxShadow: open
                ? "0 0 18px color-mix(in srgb, var(--neon-cyan) 35%, transparent)"
                : "0 2px 6px rgba(0,0,0,0.1)",
              transition: "box-shadow 0.3s ease, background 0.3s ease",
            }}
          >
            <span className="text-white">{icon}</span>
          </div>
        )}

        {/* Text */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[14px] font-bold text-[var(--foreground)]">{title}</span>
            {badge}
          </div>
          {description && (
            <p className="mt-0.5 text-[12px] text-[var(--muted-foreground)] truncate">{description}</p>
          )}
        </div>

        {/* Chevron */}
        <ChevronDown
          className={cn(
            "size-5 shrink-0 transition-all duration-200",
            open ? "rotate-180 text-[var(--neon-cyan)] drop-shadow-[0_0_6px_var(--neon-cyan)]" : "text-[var(--muted-foreground)]"
          )}
        />
      </button>

      {/* Collapsible content */}
      <div
        className={cn(
          "grid transition-all duration-300 ease-in-out",
          open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="overflow-hidden">
          <div className="p-5">{children}</div>
        </div>
      </div>
    </div>
  );
}
