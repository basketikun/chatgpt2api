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
        "overflow-hidden rounded-[16px] border border-black/[0.04] bg-white",
        "shadow-[0_1px_3px_rgba(0,0,0,0.06),0_4px_16px_rgba(0,0,0,0.04)]",
        "transition-shadow duration-200",
        open && "shadow-[0_4px_16px_rgba(99,102,241,0.10),0_12px_40px_rgba(0,0,0,0.07)]"
      )}
    >
      {/* Clickable header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center gap-4 px-6 py-4 text-left transition-colors duration-200",
          open ? "bg-slate-50/80 border-b border-black/[0.04]" : "hover:bg-slate-50/60"
        )}
      >
        {/* Icon avatar */}
        {icon && (
          <div className="flex size-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-indigo-500 to-violet-500 shadow-md shadow-indigo-200">
            <span className="text-white">{icon}</span>
          </div>
        )}

        {/* Text */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[15px] font-bold text-slate-900">{title}</span>
            {badge}
          </div>
          {description && (
            <p className="mt-0.5 text-[13px] text-slate-500 truncate">{description}</p>
          )}
        </div>

        {/* Chevron */}
        <ChevronDown
          className={cn(
            "size-5 shrink-0 text-slate-400 transition-transform duration-200",
            open && "rotate-180 text-indigo-500"
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
          <div className="p-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
