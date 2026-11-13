"use client";

import { LoaderCircle } from "lucide-react";

import { cn } from "@/lib/utils";

/** 页面级加载占位（鉴权校验、首屏数据）。 */
export function PageLoader({ className, label = "加载中" }: { className?: string; label?: string }) {
  return (
    <div className={cn("flex min-h-[40vh] flex-1 items-center justify-center gap-2 text-stone-400", className)}>
      <LoaderCircle className="size-5 animate-spin" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
