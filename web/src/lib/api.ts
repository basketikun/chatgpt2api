import { httpRequest } from "@/lib/request";

export type AccountType = "Free" | "Plus" | "ProLite" | "Pro" | "Team";
export type AccountStatus = "正常" | "限流" | "异常" | "禁用";
export type ImageModel = "gpt-image-2" | "codex-gpt-image-2";
export type AuthRole = "admin" | "user";

export type Account = {
  id: string;
  access_token: string;
  type: AccountType;
  status: AccountStatus;
  quota: number;
  imageQuotaUnknown?: boolean;
  email?: string | null;
  user_id?: string | null;
  limits_progress?: Array<{
    feature_name?: string;
    remaining?: number;
    reset_after?: string;
  }>;
  default_model_slug?: string | null;
  restoreAt?: string | null;
  success: number;
  fail: number;
  lastUsedAt: string | null;
};

type AccountListResponse = {
  items: Account[];
};

type AccountMutationResponse = {
  items: Account[];
  added?: number;
  skipped?: number;
  removed?: number;
  refreshed?: number;
  errors?: Array<{ access_token: string; error: string }>;
};

type AccountRefreshResponse = {
  items: Account[];
  refreshed: number;
  errors: Array<{ access_token: string; error: string }>;
};

type AccountUpdateResponse = {
  item: Account;
  items: Account[];
};

export type SettingsConfig = {
  proxy: string;
  base_url?: string;
  refresh_account_interval_minute?: number | string;
  image_retention_days?: number | string;
  auto_remove_invalid_accounts?: boolean;
  auto_remove_rate_limited_accounts?: boolean;
  log_levels?: string[];
  [key: string]: unknown;
};

export type ManagedImage = {
  name: string;
  date: string;
  size: number;
  url: string;
  created_at: string;
};

export type SystemLog = {
  time: string;
  type: "call" | "account" | string;
  summary?: string;
  detail?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ImageResponse = {
  created: number;
  data: Array<{ b64_json: string; revised_prompt?: string }>;
};

export type LoginResponse = {
  ok: boolean;
  version: string;
  role: AuthRole;
  subject_id: string;
  name: string;
  token: string;
  user: ManagedUser;
};

export type SetupStatus = {
  has_admin: boolean;
  requires_setup: boolean;
};

export type PublicSettings = {
  site_name: string;
  registration_enabled: boolean;
  email_verification_enabled: boolean;
  invitation_required: boolean;
  promo_codes_enabled: boolean;
  email_domain_whitelist: string[];
};

export type ManagedUser = {
  id: string;
  email: string;
  name: string;
  role: AuthRole;
  enabled: boolean;
  image_quota: number;
  image_concurrency: number;
  active_image_requests: number;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
};

export type AuthSettings = {
  site_name: string;
  registration_enabled: boolean;
  email_verification_enabled: boolean;
  invitation_required: boolean;
  promo_codes_enabled: boolean;
  email_domain_whitelist: string[];
  default_image_quota: number;
  default_image_concurrency: number;
  verify_code_ttl_seconds: number;
  verify_send_cooldown_seconds: number;
  verify_max_attempts: number;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password: string;
  smtp_from: string;
  smtp_tls: boolean;
  has_smtp_password: boolean;
};

export type RedeemCodeType = "image_quota" | "concurrency" | "invitation";

export type RedeemCode = {
  id: string;
  code_preview: string;
  type: RedeemCodeType;
  value: number;
  enabled: boolean;
  used: boolean;
  used_by_user_id: string | null;
  used_at: string | null;
  expires_at: string | null;
  created_at: string;
  code?: string;
};

export type PromoCode = {
  id: string;
  code_preview: string;
  image_quota: number;
  max_uses: number;
  used_count: number;
  enabled: boolean;
  expires_at: string | null;
  created_at: string;
};

export type RegisterConfig = {
  enabled: boolean;
  mail: {
    request_timeout: number;
    wait_timeout: number;
    wait_interval: number;
    providers: Array<Record<string, unknown>>;
  };
  proxy: string;
  total: number;
  threads: number;
  mode: "total" | "quota" | "available";
  target_quota: number;
  target_available: number;
  check_interval: number;
  stats: {
    job_id?: string;
    success: number;
    fail: number;
    done: number;
    running: number;
    threads: number;
    elapsed_seconds?: number;
    avg_seconds?: number;
    success_rate?: number;
    current_quota?: number;
    current_available?: number;
    started_at?: string;
    updated_at?: string;
    finished_at?: string;
  };
  logs?: Array<{
    time: string;
    text: string;
    level: string;
  }>;
};

export async function fetchSetupStatus() {
  return httpRequest<SetupStatus>("/api/setup/status", { redirectOnUnauthorized: false });
}

export async function setupAdmin(payload: { email: string; password: string }) {
  return httpRequest<LoginResponse>("/api/setup/admin", {
    method: "POST",
    body: payload,
    redirectOnUnauthorized: false,
  });
}

export async function fetchPublicSettings() {
  return httpRequest<{ settings: PublicSettings }>("/api/public/settings", { redirectOnUnauthorized: false });
}

export async function login(email: string, password: string) {
  return httpRequest<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: { email, password },
    redirectOnUnauthorized: false,
  });
}

export async function registerUser(payload: {
  email: string;
  password: string;
  verification_code?: string;
  invitation_code?: string;
  promo_code?: string;
}) {
  return httpRequest<LoginResponse>("/api/auth/register", {
    method: "POST",
    body: payload,
    redirectOnUnauthorized: false,
  });
}

export async function sendVerifyCode(email: string) {
  return httpRequest<{ ok: boolean }>("/api/auth/send-verify-code", {
    method: "POST",
    body: { email, purpose: "register" },
    redirectOnUnauthorized: false,
  });
}

export async function fetchMe() {
  return httpRequest<{ user: ManagedUser }>("/api/auth/me");
}

export async function fetchAccounts() {
  return httpRequest<AccountListResponse>("/api/accounts");
}

export async function createAccounts(tokens: string[]) {
  return httpRequest<AccountMutationResponse>("/api/accounts", {
    method: "POST",
    body: { tokens },
  });
}

export async function deleteAccounts(tokens: string[]) {
  return httpRequest<AccountMutationResponse>("/api/accounts", {
    method: "DELETE",
    body: { tokens },
  });
}

export async function refreshAccounts(accessTokens: string[]) {
  return httpRequest<AccountRefreshResponse>("/api/accounts/refresh", {
    method: "POST",
    body: { access_tokens: accessTokens },
  });
}

export async function updateAccount(
  accessToken: string,
  updates: {
    type?: AccountType;
    status?: AccountStatus;
    quota?: number;
  },
) {
  return httpRequest<AccountUpdateResponse>("/api/accounts/update", {
    method: "POST",
    body: {
      access_token: accessToken,
      ...updates,
    },
  });
}

export async function generateImage(prompt: string, model?: ImageModel, size?: string) {
  return httpRequest<ImageResponse>(
    "/v1/images/generations",
    {
      method: "POST",
      body: {
        prompt,
        ...(model ? { model } : {}),
        ...(size ? { size } : {}),
        n: 1,
        response_format: "b64_json",
      },
    },
  );
}

export async function editImage(files: File | File[], prompt: string, model?: ImageModel, size?: string) {
  const formData = new FormData();
  const uploadFiles = Array.isArray(files) ? files : [files];

  uploadFiles.forEach((file) => {
    formData.append("image", file);
  });
  formData.append("prompt", prompt);
  if (model) {
    formData.append("model", model);
  }
  if (size) {
    formData.append("size", size);
  }
  formData.append("n", "1");

  return httpRequest<ImageResponse>(
    "/v1/images/edits",
    {
      method: "POST",
      body: formData,
    },
  );
}

export async function fetchSettingsConfig() {
  return httpRequest<{ config: SettingsConfig }>("/api/settings");
}

export async function updateSettingsConfig(settings: SettingsConfig) {
  return httpRequest<{ config: SettingsConfig }>("/api/settings", {
    method: "POST",
    body: settings,
  });
}

export async function fetchManagedImages(filters: { start_date?: string; end_date?: string }) {
  const params = new URLSearchParams();
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  return httpRequest<{ items: ManagedImage[]; groups: Array<{ date: string; items: ManagedImage[] }> }>(
    `/api/images${params.toString() ? `?${params.toString()}` : ""}`,
  );
}

export async function fetchSystemLogs(filters: { type?: string; start_date?: string; end_date?: string }) {
  const params = new URLSearchParams();
  if (filters.type) params.set("type", filters.type);
  if (filters.start_date) params.set("start_date", filters.start_date);
  if (filters.end_date) params.set("end_date", filters.end_date);
  return httpRequest<{ items: SystemLog[] }>(`/api/logs${params.toString() ? `?${params.toString()}` : ""}`);
}

export async function fetchAuthSettings() {
  return httpRequest<{ settings: AuthSettings }>("/api/admin/auth-settings");
}

export async function updateAuthSettings(updates: Partial<AuthSettings>) {
  return httpRequest<{ settings: AuthSettings }>("/api/admin/auth-settings", { method: "PATCH", body: updates });
}

export async function fetchManagedUsers(query = "") {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  return httpRequest<{ items: ManagedUser[] }>(`/api/admin/users${params.toString() ? `?${params.toString()}` : ""}`);
}

export async function createManagedUser(payload: {
  email: string;
  password: string;
  role: AuthRole;
  enabled: boolean;
  image_quota: number;
  image_concurrency: number;
}) {
  return httpRequest<{ item: ManagedUser; items: ManagedUser[] }>("/api/admin/users", {
    method: "POST",
    body: payload,
  });
}

export async function updateManagedUser(userId: string, updates: Partial<ManagedUser> & { password?: string }) {
  return httpRequest<{ item: ManagedUser; items: ManagedUser[] }>(`/api/admin/users/${userId}`, {
    method: "PATCH",
    body: updates,
  });
}

export async function deleteManagedUser(userId: string) {
  return httpRequest<{ items: ManagedUser[] }>(`/api/admin/users/${userId}`, {
    method: "DELETE",
  });
}

export async function generateRedeemCodes(payload: {
  type: RedeemCodeType;
  value: number;
  count: number;
  expires_at?: string;
}) {
  return httpRequest<{ codes: RedeemCode[]; items: RedeemCode[] }>("/api/admin/redeem-codes/generate", {
    method: "POST",
    body: payload,
  });
}

export async function fetchRedeemCodes() {
  return httpRequest<{ items: RedeemCode[] }>("/api/admin/redeem-codes");
}

export async function updateRedeemCode(codeId: string, updates: { enabled?: boolean; expires_at?: string }) {
  return httpRequest<{ item: RedeemCode; items: RedeemCode[] }>(`/api/admin/redeem-codes/${codeId}`, {
    method: "PATCH",
    body: updates,
  });
}

export async function deleteRedeemCode(codeId: string) {
  return httpRequest<{ items: RedeemCode[] }>(`/api/admin/redeem-codes/${codeId}`, { method: "DELETE" });
}

export async function redeemCode(code: string) {
  return httpRequest<{ redeem: RedeemCode; user: ManagedUser }>("/api/redeem", { method: "POST", body: { code } });
}

export async function fetchRedeemHistory() {
  return httpRequest<{ items: RedeemCode[] }>("/api/redeem/history");
}

export async function fetchPromoCodes() {
  return httpRequest<{ items: PromoCode[] }>("/api/admin/promo-codes");
}

export async function createPromoCode(payload: {
  code: string;
  image_quota: number;
  max_uses: number;
  enabled: boolean;
  expires_at?: string;
}) {
  return httpRequest<{ item: PromoCode; items: PromoCode[] }>("/api/admin/promo-codes", {
    method: "POST",
    body: payload,
  });
}

export async function updatePromoCode(codeId: string, updates: Partial<PromoCode>) {
  return httpRequest<{ item: PromoCode; items: PromoCode[] }>(`/api/admin/promo-codes/${codeId}`, {
    method: "PATCH",
    body: updates,
  });
}

export async function deletePromoCode(codeId: string) {
  return httpRequest<{ items: PromoCode[] }>(`/api/admin/promo-codes/${codeId}`, { method: "DELETE" });
}

export async function fetchRegisterConfig() {
  return httpRequest<{ register: RegisterConfig }>("/api/register");
}

export async function updateRegisterConfig(updates: Partial<RegisterConfig>) {
  return httpRequest<{ register: RegisterConfig }>("/api/register", {
    method: "POST",
    body: updates,
  });
}

export async function startRegister() {
  return httpRequest<{ register: RegisterConfig }>("/api/register/start", { method: "POST" });
}

export async function stopRegister() {
  return httpRequest<{ register: RegisterConfig }>("/api/register/stop", { method: "POST" });
}

export async function resetRegister() {
  return httpRequest<{ register: RegisterConfig }>("/api/register/reset", { method: "POST" });
}

// ── CPA (CLIProxyAPI) ──────────────────────────────────────────────

export type CPAPool = {
  id: string;
  name: string;
  base_url: string;
  import_job?: CPAImportJob | null;
};

export type CPARemoteFile = {
  name: string;
  email: string;
};

export type CPAImportJob = {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  total: number;
  completed: number;
  added: number;
  skipped: number;
  refreshed: number;
  failed: number;
  errors: Array<{ name: string; error: string }>;
};

export async function fetchCPAPools() {
  return httpRequest<{ pools: CPAPool[] }>("/api/cpa/pools");
}

export async function createCPAPool(pool: { name: string; base_url: string; secret_key: string }) {
  return httpRequest<{ pool: CPAPool; pools: CPAPool[] }>("/api/cpa/pools", {
    method: "POST",
    body: pool,
  });
}

export async function updateCPAPool(
  poolId: string,
  updates: { name?: string; base_url?: string; secret_key?: string },
) {
  return httpRequest<{ pool: CPAPool; pools: CPAPool[] }>(`/api/cpa/pools/${poolId}`, {
    method: "POST",
    body: updates,
  });
}

export async function deleteCPAPool(poolId: string) {
  return httpRequest<{ pools: CPAPool[] }>(`/api/cpa/pools/${poolId}`, {
    method: "DELETE",
  });
}

export async function fetchCPAPoolFiles(poolId: string) {
  return httpRequest<{ pool_id: string; files: CPARemoteFile[] }>(`/api/cpa/pools/${poolId}/files`);
}

export async function startCPAImport(poolId: string, names: string[]) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/cpa/pools/${poolId}/import`, {
    method: "POST",
    body: { names },
  });
}

export async function fetchCPAPoolImportJob(poolId: string) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/cpa/pools/${poolId}/import`);
}

// ── Sub2API ────────────────────────────────────────────────────────

export type Sub2APIServer = {
  id: string;
  name: string;
  base_url: string;
  email: string;
  has_api_key: boolean;
  group_id: string;
  import_job?: CPAImportJob | null;
};

export type Sub2APIRemoteAccount = {
  id: string;
  name: string;
  email: string;
  plan_type: string;
  status: string;
  expires_at: string;
  has_refresh_token: boolean;
};

export type Sub2APIRemoteGroup = {
  id: string;
  name: string;
  description: string;
  platform: string;
  status: string;
  account_count: number;
  active_account_count: number;
};

export async function fetchSub2APIServers() {
  return httpRequest<{ servers: Sub2APIServer[] }>("/api/sub2api/servers");
}

export async function createSub2APIServer(server: {
  name: string;
  base_url: string;
  email: string;
  password: string;
  api_key: string;
  group_id: string;
}) {
  return httpRequest<{ server: Sub2APIServer; servers: Sub2APIServer[] }>("/api/sub2api/servers", {
    method: "POST",
    body: server,
  });
}

export async function updateSub2APIServer(
  serverId: string,
  updates: {
    name?: string;
    base_url?: string;
    email?: string;
    password?: string;
    api_key?: string;
    group_id?: string;
  },
) {
  return httpRequest<{ server: Sub2APIServer; servers: Sub2APIServer[] }>(`/api/sub2api/servers/${serverId}`, {
    method: "POST",
    body: updates,
  });
}

export async function fetchSub2APIServerGroups(serverId: string) {
  return httpRequest<{ server_id: string; groups: Sub2APIRemoteGroup[] }>(
    `/api/sub2api/servers/${serverId}/groups`,
  );
}

export async function deleteSub2APIServer(serverId: string) {
  return httpRequest<{ servers: Sub2APIServer[] }>(`/api/sub2api/servers/${serverId}`, {
    method: "DELETE",
  });
}

export async function fetchSub2APIServerAccounts(serverId: string) {
  return httpRequest<{ server_id: string; accounts: Sub2APIRemoteAccount[] }>(
    `/api/sub2api/servers/${serverId}/accounts`,
  );
}

export async function startSub2APIImport(serverId: string, accountIds: string[]) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/sub2api/servers/${serverId}/import`, {
    method: "POST",
    body: { account_ids: accountIds },
  });
}

export async function fetchSub2APIImportJob(serverId: string) {
  return httpRequest<{ import_job: CPAImportJob | null }>(`/api/sub2api/servers/${serverId}/import`);
}

// ── Upstream proxy ────────────────────────────────────────────────

export type ProxySettings = {
  enabled: boolean;
  url: string;
};

export type ProxyTestResult = {
  ok: boolean;
  status: number;
  latency_ms: number;
  error: string | null;
};

export async function fetchProxy() {
  return httpRequest<{ proxy: ProxySettings }>("/api/proxy");
}

export async function updateProxy(updates: { enabled?: boolean; url?: string }) {
  return httpRequest<{ proxy: ProxySettings }>("/api/proxy", {
    method: "POST",
    body: updates,
  });
}

export async function testProxy(url?: string) {
  return httpRequest<{ result: ProxyTestResult }>("/api/proxy/test", {
    method: "POST",
    body: { url: url ?? "" },
  });
}
