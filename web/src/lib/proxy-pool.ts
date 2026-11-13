import type {
  ProxyPoolHealthState,
  ProxyPoolItem,
  ProxyPoolPayload,
  ProxyPoolSource,
  ProxySubscriptionNode,
  ProxySubscriptionNodeMode,
  ProxySubscriptionRefreshResult,
  ProxySubscriptionSummary,
  ProxySubscriptionUserinfo,
} from "@/lib/api";

type HealthMeta = {
  label: string;
  variant: "success" | "danger" | "secondary";
  dotClass: string;
  textClass: string;
};

const healthMeta: Record<ProxyPoolHealthState, HealthMeta> = {
  healthy: { label: "健康", variant: "success", dotClass: "bg-success", textClass: "text-success" },
  unhealthy: { label: "异常", variant: "danger", dotClass: "bg-destructive", textClass: "text-destructive" },
  unknown: { label: "未知", variant: "secondary", dotClass: "bg-muted-foreground", textClass: "text-muted-foreground" },
};

export function getProxyHealthMeta(state?: string | null): HealthMeta {
  return healthMeta[state as ProxyPoolHealthState] ?? healthMeta.unknown;
}

export const proxySourceLabel: Record<ProxyPoolSource, string> = {
  manual: "手动",
  legacy_account: "迁移",
  import: "导入",
  subscription: "订阅",
};

/** 列表 / 下拉里展示的代理名称：优先名称，没有名称时用脱敏地址 */
export function proxyPoolLabel(item: Pick<ProxyPoolItem, "name" | "masked_url">) {
  return item.name?.trim() || item.masked_url;
}

/** 绑定的代理被禁用或判定异常时，账号会临时借用其他代理（绑定本身不变） */
export function isProxyUnavailable(item: Pick<ProxyPoolItem, "enabled" | "health">) {
  return !item.enabled || item.health?.state === "unhealthy";
}

/** 只保留接口返回的三块数据，丢掉 added / result 之类的附加字段 */
export function pickProxyPoolPayload(data: ProxyPoolPayload): ProxyPoolPayload {
  return { settings: data.settings, items: data.items, summary: data.summary };
}

export function formatProxyTime(value?: string | null) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const pad = (num: number) => String(num).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(
    date.getSeconds(),
  )}`;
}

/** 账号上手填的旧代理可能带账号密码，列表里只显示协议和主机 */
export function maskProxyUrl(raw?: string | null) {
  const value = String(raw ?? "").trim();
  if (!value) {
    return "";
  }
  const hasScheme = value.includes("://");
  try {
    const url = new URL(hasScheme ? value : `http://${value}`);
    return hasScheme ? `${url.protocol}//${url.host}` : url.host;
  } catch {
    return value.replace(/\/\/[^@/]*@/, "//***@");
  }
}

/**
 * 已启用的代理里出口 IP 相同的分组：exit_ip → 条目数，只返回 ≥ 2 的。
 * 禁用的代理不参与分配，不算重复（禁用其中一个就能消掉提示）。
 */
export function duplicateExitIps(items: ReadonlyArray<Pick<ProxyPoolItem, "enabled" | "health">>) {
  const counts = new Map<string, number>();
  for (const item of items) {
    const ip = item.health?.exit_ip?.trim();
    if (!item.enabled || !ip) {
      continue;
    }
    counts.set(ip, (counts.get(ip) ?? 0) + 1);
  }
  for (const [ip, count] of counts) {
    if (count < 2) {
      counts.delete(ip);
    }
  }
  return counts;
}

// ── 订阅 ──────────────────────────────────────────────────────────

export const DEFAULT_SUBSCRIPTION_USER_AGENT = "clash.meta";
export const DEFAULT_SUBSCRIPTION_REFRESH_HOURS = 6;
export const MAX_SUBSCRIPTION_REFRESH_HOURS = 168;

export const MANUAL_SUBSCRIPTION_NAME = "手动添加的节点";

export function isManualSubscription(item: Pick<ProxySubscriptionSummary, "kind">) {
  return item.kind === "manual";
}

export function subscriptionLabel(item: Pick<ProxySubscriptionSummary, "name" | "masked_url"> & { kind?: ProxySubscriptionSummary["kind"] }) {
  return item.name?.trim() || (item.kind === "manual" ? MANUAL_SUBSCRIPTION_NAME : item.masked_url);
}

/** 批量添加里需要走 mihomo 内核的分享链接协议（与后端 SHARE_LINK_SCHEMES 对应） */
const SHARE_LINK_SCHEMES = new Set(["vmess", "vless", "trojan", "ss", "ssr", "hysteria2", "hy2", "tuic", "socks"]);

/**
 * 这一行是否是分享链接或整段 Base64 订阅内容（后端会存进「手动添加的节点」）。
 * Base64 的判断和后端一致：长度 > 16、不含空格和冒号。
 */
export function isShareLinkLine(line: string) {
  const value = line.trim();
  const index = value.indexOf("://");
  if (index > 0) {
    return SHARE_LINK_SCHEMES.has(value.slice(0, index).toLowerCase());
  }
  return value.length > 16 && !/[\s:]/.test(value) && /^[A-Za-z0-9+/=_-]+$/.test(value);
}

export function formatRefreshInterval(hours?: number | null) {
  return hours && hours > 0 ? `每 ${hours} 小时` : "手动";
}

/** 校验刷新间隔输入：0–168 的整数，不合法返回 null */
export function parseRefreshHours(raw: string) {
  const value = raw.trim();
  if (!/^\d+$/.test(value)) {
    return null;
  }
  const hours = Number(value);
  return hours <= MAX_SUBSCRIPTION_REFRESH_HOURS ? hours : null;
}

export function formatBytes(bytes?: number | null) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || size >= 100 ? 0 : size >= 10 ? 1 : 2;
  return `${Number(size.toFixed(digits))} ${units[unit]}`;
}

export type SubscriptionTraffic = { used: number; total: number | null; percent: number | null; text: string };
export type SubscriptionExpire = { date: string; expired: boolean; daysLeft: number };

/** subscription-userinfo 里的流量：已用 = 上传 + 下载 */
export function subscriptionTraffic(userinfo?: ProxySubscriptionUserinfo | null): SubscriptionTraffic | null {
  if (!userinfo) {
    return null;
  }
  const { upload, download, total } = userinfo;
  if (upload == null && download == null && !total) {
    return null;
  }
  const used = (upload ?? 0) + (download ?? 0);
  if (total && total > 0) {
    const percent = Math.min(100, Math.round((used / total) * 100));
    return { used, total, percent, text: `${formatBytes(used)} / ${formatBytes(total)}` };
  }
  return { used, total: null, percent: null, text: `已用 ${formatBytes(used)}` };
}

export function subscriptionExpire(userinfo?: ProxySubscriptionUserinfo | null, now = Date.now()): SubscriptionExpire | null {
  const expire = userinfo?.expire;
  if (!expire || expire <= 0) {
    return null;
  }
  const date = new Date(expire * 1000);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const pad = (num: number) => String(num).padStart(2, "0");
  const remaining = expire * 1000 - now;
  return {
    date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    expired: remaining <= 0,
    daysLeft: Math.ceil(remaining / 86_400_000),
  };
}

/** 刷新结果的一句话摘要（用在 toast 里） */
export function describeRefreshResult(result: ProxySubscriptionRefreshResult) {
  if (!result.ok) {
    return `拉取失败：${result.error || "未知错误"}`;
  }
  const parts = [`${result.nodes ?? 0} 个节点`];
  if (result.updated) parts.push(`更新 ${result.updated} 个代理地址`);
  if (result.missing) parts.push(`${result.missing} 个节点不可用，已自动禁用`);
  if (result.restored) parts.push(`恢复 ${result.restored} 个`);
  return parts.join("，");
}

export const nodeModeLabel: Record<ProxySubscriptionNodeMode, string> = {
  direct: "可直连",
  core: "需内核",
  unsupported: "不支持",
};

export type NodeModeFilter = "all" | ProxySubscriptionNodeMode;

/** 未导入且当前可导入的节点才能勾选 */
export function isNodeSelectable(node: Pick<ProxySubscriptionNode, "available" | "imported">) {
  return node.available && !node.imported;
}

export function filterSubscriptionNodes<T extends ProxySubscriptionNode>(nodes: readonly T[], query: string, mode: NodeModeFilter) {
  const keyword = query.trim().toLowerCase();
  return nodes.filter((node) => {
    if (mode !== "all" && node.mode !== mode) {
      return false;
    }
    if (!keyword) {
      return true;
    }
    return [node.name, node.type, `${node.server}:${node.port}`].some((value) => value.toLowerCase().includes(keyword));
  });
}
