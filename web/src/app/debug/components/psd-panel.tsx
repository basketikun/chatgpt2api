"use client";

import { useI18n } from "@/lib/i18n";
import { EditableFilePanel } from "./editable-file-panel";

export function PsdPanel() {
  const { locale } = useI18n();
  const isFa = locale === "fa";
  const isAr = locale === "ar";
  const isZh = locale === "zh";

  const title = isFa ? "تفکیک لایه‌های PSD" : isAr ? "تفكيك طبقات PSD" : isZh ? "PSD生成" : "PSD Generation";
  const defaultPrompt = isFa
    ? "المان‌های پوستر را بر اساس موقعیت اصلی تفکیک کرده و یک فایل PSD لایه‌باز قابل ویرایش تولید کنید، لایه‌های پس‌زمینه و المان‌ها حفظ شوند و بسته zip متریال‌ها نیز خروجی داده شود."
    : isAr
      ? "تفكيك عناصر الملصق وفق المواضع الأصلية ودمجها في ملف PSD قابل للتعديل مع الحفاظ على موضع الخلفية والطبقات وتصدير حزمة zip."
      : isZh
        ? "按原图位置拆分海报元素并合成可编辑 PSD，保留背景和每个元素图层位置，同时输出每个图层素材 zip。"
        : "Split poster elements based on original positions into an editable PSD, preserving background and layer positions, and export an asset zip.";

  return <EditableFilePanel title={title} kind="psd" endpoint="/v1/psd/generations" defaultPrompt={defaultPrompt} imageRequired />;
}
