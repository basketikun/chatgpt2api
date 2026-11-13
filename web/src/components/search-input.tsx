"use client";

import { Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type SearchInputProps = {
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  /** default 与其他表单控件对齐；sm 用在紧凑工具栏 */
  size?: "default" | "sm";
  "aria-label"?: string;
};

/** 列表筛选用的搜索框：左侧放大镜 + 输入框。 */
export function SearchInput({
  value,
  onValueChange,
  placeholder,
  className,
  size = "default",
  "aria-label": ariaLabel,
}: SearchInputProps) {
  return (
    <div className={cn("relative min-w-0", className)}>
      <Search
        className={cn(
          "pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400",
          size === "sm" ? "size-3.5" : "size-4",
        )}
      />
      <Input
        type="search"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        className={cn(
          "w-full",
          size === "sm" ? "h-8 rounded-lg pl-8 text-[13px]" : "h-10 rounded-xl pl-9 text-sm",
        )}
      />
    </div>
  );
}
