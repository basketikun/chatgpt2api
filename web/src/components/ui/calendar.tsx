"use client";

import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { vi } from "date-fns/locale";

import { cn } from "@/lib/utils";

function Calendar({
  className,
  classNames,
  showOutsideDays = true,
  ...props
}: React.ComponentProps<typeof DayPicker>) {
  return (
    <DayPicker
      showOutsideDays={showOutsideDays}
      className={cn("p-1 text-sm", className)}
      classNames={{
        months: "flex flex-col gap-4 sm:flex-row",
        month: "relative",
        month_caption: "flex h-9 items-center justify-center font-medium",
        nav: "absolute inset-x-2 top-2 flex items-center justify-between",
        button_previous: "inline-flex size-8 items-center justify-center rounded-lg hover:bg-stone-200",
        button_next: "inline-flex size-8 items-center justify-center rounded-lg hover:bg-stone-200",
        weekdays: "mt-2 grid grid-cols-7 text-xs text-stone-500",
        weekday: "flex h-8 items-center justify-center font-normal",
        week: "grid grid-cols-7",
        day: "size-9 p-0 text-center",
        day_button: "size-9 rounded-lg text-sm transition hover:bg-stone-200",
        today: "font-semibold text-stone-950",
        selected: "[[&_button]:bg-stone-100 [&_button]:text-white_button]:bg-stone-900 [[&_button]:bg-stone-100 [&_button]:text-white_button]:text-white [&_button]:hover:bg-stone-800",
        outside: "text-stone-700",
        disabled: "text-stone-700 opacity-50",
        ...classNames,
      }}
      components={{
        Chevron: ({ orientation }) =>
          orientation === "left" ? <ChevronLeft className="size-4" /> : <ChevronRight className="size-4" />,
      }}
      locale={vi}
      {...props}
    />
  );
}

export { Calendar };
