import type { AccountStatus } from "@/lib/api";

// Account status arrives from the API as a Chinese literal and is compared
// against those literals in backend business logic, so the wire value stays
// as-is. Only its display is translated, through this key map.
export const ACCOUNT_STATUS_KEYS: Record<AccountStatus, string> = {
  "正常": "normal",
  "限流": "rateLimited",
  "异常": "error",
  "禁用": "disabled",
};
