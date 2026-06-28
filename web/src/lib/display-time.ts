export const DEFAULT_DISPLAY_TIMEZONE = "Asia/Shanghai";

export const DISPLAY_TIMEZONE_CHOICES = [
  { value: "Asia/Shanghai", label: "中国大陆 / 北京时间" },
  { value: "Asia/Hong_Kong", label: "中国香港" },
  { value: "Asia/Taipei", label: "中国台湾" },
  { value: "Asia/Singapore", label: "新加坡" },
  { value: "Asia/Tokyo", label: "日本东京" },
  { value: "Asia/Seoul", label: "韩国首尔" },
  { value: "Asia/Bangkok", label: "泰国曼谷" },
  { value: "Asia/Jakarta", label: "印尼雅加达" },
  { value: "Asia/Kolkata", label: "印度加尔各答" },
  { value: "Asia/Dubai", label: "阿联酋迪拜" },
  { value: "Australia/Sydney", label: "澳大利亚悉尼" },
  { value: "Pacific/Auckland", label: "新西兰奥克兰" },
  { value: "UTC", label: "UTC 标准时间" },
  { value: "Europe/London", label: "英国伦敦" },
  { value: "Europe/Paris", label: "法国巴黎" },
  { value: "Europe/Berlin", label: "德国柏林" },
  { value: "Europe/Amsterdam", label: "荷兰阿姆斯特丹" },
  { value: "Europe/Moscow", label: "俄罗斯莫斯科" },
  { value: "America/New_York", label: "美国纽约 / 东部" },
  { value: "America/Chicago", label: "美国芝加哥 / 中部" },
  { value: "America/Denver", label: "美国丹佛 / 山区" },
  { value: "America/Los_Angeles", label: "美国洛杉矶 / 太平洋" },
  { value: "America/Toronto", label: "加拿大多伦多" },
  { value: "America/Vancouver", label: "加拿大温哥华" },
  { value: "America/Mexico_City", label: "墨西哥城" },
  { value: "America/Sao_Paulo", label: "巴西圣保罗" },
] as const;

export const DISPLAY_TIMEZONE_OPTIONS = DISPLAY_TIMEZONE_CHOICES.map((item) => item.value);

const TIMEZONE_FORMAT_CACHE = new Map<string, boolean>();
const UTC_OFFSET_PATTERN = /(?:z|[+-]\d{2}:?\d{2})$/i;
const NAIVE_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?$/;

export function normalizeDisplayTimezone(value: unknown): string {
  const timezone = String(value || DEFAULT_DISPLAY_TIMEZONE).trim();
  if (!timezone) {
    return DEFAULT_DISPLAY_TIMEZONE;
  }
  const cached = TIMEZONE_FORMAT_CACHE.get(timezone);
  if (cached !== undefined) {
    return cached ? timezone : DEFAULT_DISPLAY_TIMEZONE;
  }
  try {
    new Intl.DateTimeFormat("zh-CN", { timeZone: timezone }).format(new Date(0));
    TIMEZONE_FORMAT_CACHE.set(timezone, true);
    return timezone;
  } catch {
    TIMEZONE_FORMAT_CACHE.set(timezone, false);
    return DEFAULT_DISPLAY_TIMEZONE;
  }
}

export function parseDisplayDate(value: unknown): Date | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    const timestamp = value > 10_000_000_000 ? value : value * 1000;
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const raw = String(value ?? "").trim();
  if (!raw) {
    return null;
  }
  if (/^\d+$/.test(raw)) {
    return parseDisplayDate(Number(raw));
  }

  const normalized = raw.replace(" ", "T");
  const source = UTC_OFFSET_PATTERN.test(normalized) || !NAIVE_DATE_TIME_PATTERN.test(raw)
    ? normalized
    : `${normalized}Z`;
  const date = new Date(source);
  return Number.isNaN(date.getTime()) ? null : date;
}

function dateParts(date: Date, timezone: string) {
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: normalizeDisplayTimezone(timezone),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const parts = formatter.formatToParts(date).reduce<Record<string, string>>((acc, part) => {
    acc[part.type] = part.value;
    return acc;
  }, {});
  return {
    year: parts.year || "0000",
    month: parts.month || "00",
    day: parts.day || "00",
    hour: parts.hour || "00",
    minute: parts.minute || "00",
    second: parts.second || "00",
  };
}

export function formatDisplayDateTime(value: unknown, timezone: string, fallback = "-"): string {
  const date = parseDisplayDate(value);
  if (!date) {
    return fallback;
  }
  const parts = dateParts(date, timezone);
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
}

export function formatDisplayShortDateTime(value: unknown, timezone: string, fallback = "-"): string {
  const date = parseDisplayDate(value);
  if (!date) {
    return fallback;
  }
  const parts = dateParts(date, timezone);
  return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

export function formatDisplayTime(value: unknown, timezone: string, fallback = "-"): string {
  const date = parseDisplayDate(value);
  if (!date) {
    return fallback;
  }
  const parts = dateParts(date, timezone);
  return `${parts.hour}:${parts.minute}:${parts.second}`;
}
