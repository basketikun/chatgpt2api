"use client";

import { format, parse } from "date-fns";
import { CalendarIcon } from "lucide-react";
import type { DateRange } from "react-day-picker";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Field } from "@/components/ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

type DateRangeFilterProps = {
  startDate: string;
  endDate: string;
  onChange: (startDate: string, endDate: string) => void;
};

export function DateRangeFilter({ startDate, endDate, onChange }: DateRangeFilterProps) {
  const selected: DateRange | undefined = startDate
    ? {
        from: parse(startDate, "yyyy-MM-dd", new Date()),
        to: endDate ? parse(endDate, "yyyy-MM-dd", new Date()) : undefined,
      }
    : undefined;

  const label = startDate ? `${startDate} to ${endDate || startDate}` : "Select date range";

  return (
    <Field className="w-[240px]">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" className="h-10 justify-start rounded-xl border-stone-200 bg-white px-3 font-normal text-stone-700">
            <CalendarIcon className="size-4 text-stone-400" />
            {label}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-auto p-3" align="start">
          <Calendar
            mode="range"
            defaultMonth={selected?.from}
            selected={selected}
            onSelect={(value) => onChange(value?.from ? format(value.from, "yyyy-MM-dd") : "", value?.to ? format(value.to, "yyyy-MM-dd") : "")}
            numberOfMonths={2}
          />
        </PopoverContent>
      </Popover>
    </Field>
  );
}
