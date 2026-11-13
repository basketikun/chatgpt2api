"use client";

import { useI18n } from "@/lib/i18n";
import { EditableFilePanel } from "./editable-file-panel";

export function PptPanel() {
  const { locale } = useI18n();
  const isFa = locale === "fa";
  const isAr = locale === "ar";
  const isZh = locale === "zh";

  const title = isFa ? "تولید اسلاید PPT" : isAr ? "توليد عروض PPT" : isZh ? "PPT生成" : "PPT Generation";
  const defaultPrompt = isFa
    ? "نیاز به تهیه یک فایل ارائه PPT با موضوع «گزارش عملکرد تجارت الکترونیک سه‌ماهه دوم ۲۰۲۶» برای جلسه فصلی مدیران است. تعداد اسلایدها حداکثر ۸ اسلاید با سبک مدرن و تجاری، شامل رشد فروش، جذب کاربران و نمودارهای آماری."
    : isAr
      ? "مطلوب إعداد عرض تقديمي PPT بعنوان «تقرير أداء التجارة الإلكترونية للربع الثاني 2026» لاجتماع الإدارة، في حدود 8 شرائح بنمط أعمال تقني مع رسوم بيانية ومخططات نمو."
      : isZh
        ? "需要制作一份《2026年Q2 电商运营工作汇报》PPT，用于公司管理层季度会议汇报，整体页数控制在 8 页以内，风格偏商务科技感。重点体现销售增长、用户增长、广告投放效果以及618活动成果，并通过折线图、柱状图、环形图、漏斗图呈现。"
        : "Need to create a 'Q2 2026 E-commerce Operations Report' PPT presentation for executive review, under 8 slides, business-tech style, highlighting sales growth, user growth, and performance with charts.";

  return <EditableFilePanel title={title} kind="ppt" endpoint="/v1/ppt/generations" defaultPrompt={defaultPrompt} />;
}
