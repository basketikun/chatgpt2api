"use client";

import { create } from "zustand";
import { toast } from "sonner";

import {
  createCPAPool,
  deleteBackup,
  deleteCPAPool,
  fetchCPAPoolFiles,
  fetchCPAPools,
  fetchBackups,
  fetchRegisterConfig,
  resetRegister as resetRegisterApi,
  fetchSettingsConfig,
  runBackupNow,
  syncImageStorage,
  startRegister,
  startCPAImport,
  stopRegister,
  testBackupConnection,
  testImageStorageConnection,
  updateCPAPool,
  updateRegisterConfig,
  updateSettingsConfig,
  type BackupItem,
  type BackupSettings,
  type BackupState,
  type CPAPool,
  type CPARemoteFile,
  type ImageStorageMode,
  type ImageStorageSettings,
  type RegisterConfig,
  type SettingsConfig,
} from "@/lib/api";

export const PAGE_SIZE_OPTIONS = ["50", "100", "200"] as const;

export type PageSizeOption = (typeof PAGE_SIZE_OPTIONS)[number];

function normalizeConfig(config: SettingsConfig): SettingsConfig {
  const imageStorage = typeof config.image_storage === "object" && config.image_storage
    ? config.image_storage as ImageStorageSettings
    : {
      enabled: false,
      mode: "local",
      webdav_url: "",
      webdav_username: "",
      webdav_password: "",
      webdav_root_path: "chatgpt2api/images",
      public_base_url: "",
    };
  const imageStorageMode: ImageStorageMode = imageStorage.enabled && imageStorage.mode === "both"
    ? "both"
    : imageStorage.enabled && imageStorage.mode === "webdav"
      ? "webdav"
      : "local";
  const backup = typeof config.backup === "object" && config.backup
    ? config.backup as BackupSettings
    : {
      enabled: false,
      provider: "cloudflare_r2",
      account_id: "",
      access_key_id: "",
      secret_access_key: "",
      bucket: "",
      prefix: "backups",
      interval_minutes: 360,
      rotation_keep: 10,
      encrypt: false,
      passphrase: "",
      include: {
        config: true,
        register: true,
        cpa: true,
        sub2api: true,
        logs: true,
        image_tasks: true,
        accounts_snapshot: true,
        auth_keys_snapshot: true,
        images: false,
      },
    };
  return {
    ...config,
    refresh_account_interval_minute: Number(config.refresh_account_interval_minute || 5),
    image_retention_days: Number(config.image_retention_days || 30),
    image_poll_timeout_secs: Number(config.image_poll_timeout_secs || 120),
    image_account_concurrency: Number(config.image_account_concurrency || 3),
    image_settle_enabled: Boolean(config.image_settle_enabled !== false),
    image_check_before_hit_enabled: Boolean(config.image_check_before_hit_enabled !== false),
    image_settle_secs: Number(config.image_settle_secs || 2.0),
    image_timeout_retry_secs: Number(config.image_timeout_retry_secs || 30),
    auto_remove_invalid_accounts: Boolean(config.auto_remove_invalid_accounts),
    auto_remove_rate_limited_accounts: Boolean(config.auto_remove_rate_limited_accounts),
    auto_relogin_after_refresh: Boolean(config.auto_relogin_after_refresh),
    log_levels: Array.isArray(config.log_levels) ? config.log_levels : [],
    proxy: typeof config.proxy === "string" ? config.proxy : "",
    base_url: typeof config.base_url === "string" ? config.base_url : "",
    global_system_prompt: String(config.global_system_prompt || ""),
    sensitive_words: Array.isArray(config.sensitive_words) ? config.sensitive_words : [],
    ai_review: {
      enabled: Boolean(config.ai_review?.enabled),
      base_url: String(config.ai_review?.base_url || ""),
      api_key: String(config.ai_review?.api_key || ""),
      model: String(config.ai_review?.model || ""),
      prompt: String(config.ai_review?.prompt || ""),
    },
    image_storage: {
      enabled: Boolean(imageStorage.enabled),
      mode: imageStorageMode,
      webdav_url: String(imageStorage.webdav_url || ""),
      webdav_username: String(imageStorage.webdav_username || ""),
      webdav_password: String(imageStorage.webdav_password || ""),
      webdav_root_path: String(imageStorage.webdav_root_path || "chatgpt2api/images"),
      public_base_url: String(imageStorage.public_base_url || ""),
    },
    backup: {
      ...backup,
      enabled: Boolean(backup.enabled),
      account_id: String(backup.account_id || ""),
      access_key_id: String(backup.access_key_id || ""),
      secret_access_key: String(backup.secret_access_key || ""),
      bucket: String(backup.bucket || ""),
      prefix: String(backup.prefix || "backups"),
      interval_minutes: Number(backup.interval_minutes || 360),
      rotation_keep: Number(backup.rotation_keep ?? 10),
      encrypt: Boolean(backup.encrypt),
      passphrase: String(backup.passphrase || ""),
      include: {
        config: Boolean(backup.include?.config ?? true),
        register: Boolean(backup.include?.register ?? true),
        cpa: Boolean(backup.include?.cpa ?? true),
        sub2api: Boolean(backup.include?.sub2api ?? true),
        logs: Boolean(backup.include?.logs ?? true),
        image_tasks: Boolean(backup.include?.image_tasks ?? true),
        accounts_snapshot: Boolean(backup.include?.accounts_snapshot ?? true),
        auth_keys_snapshot: Boolean(backup.include?.auth_keys_snapshot ?? true),
        images: Boolean(backup.include?.images ?? false),
      },
    },
  };
}

function normalizeFiles(items: CPARemoteFile[]) {
  const seen = new Set<string>();
  const files: CPARemoteFile[] = [];
  for (const item of items) {
    const name = String(item.name || "").trim();
    if (!name || seen.has(name)) {
      continue;
    }
    seen.add(name);
    files.push({
      name,
      email: String(item.email || "").trim(),
    });
  }
  return files;
}

type SettingsStore = {
  config: SettingsConfig | null;
  isLoadingConfig: boolean;
  isSavingConfig: boolean;
  backups: BackupItem[];
  backupState: BackupState | null;
  isLoadingBackups: boolean;
  isRunningBackup: boolean;
  deletingBackupKey: string | null;
  isTestingBackup: boolean;
  isTestingImageStorage: boolean;
  isSyncingImageStorage: boolean;

  registerConfig: RegisterConfig | null;
  isLoadingRegister: boolean;
  isSavingRegister: boolean;

  pools: CPAPool[];
  isLoadingPools: boolean;
  deletingId: string | null;
  loadingFilesId: string | null;

  dialogOpen: boolean;
  editingPool: CPAPool | null;
  formName: string;
  formBaseUrl: string;
  formSecretKey: string;
  showSecret: boolean;
  isSavingPool: boolean;

  browserOpen: boolean;
  browserPool: CPAPool | null;
  remoteFiles: CPARemoteFile[];
  selectedNames: string[];
  fileQuery: string;
  filePage: number;
  pageSize: PageSizeOption;
  isStartingImport: boolean;

  initialize: () => Promise<void>;
  loadConfig: () => Promise<void>;
  saveConfig: () => Promise<boolean>;
  loadBackups: (silent?: boolean) => Promise<void>;
  runBackup: () => Promise<void>;
  removeBackup: (key: string) => Promise<void>;
  testBackup: () => Promise<void>;
  setRefreshAccountIntervalMinute: (value: string) => void;
  setImageRetentionDays: (value: string) => void;
  setImagePollTimeoutSecs: (value: string) => void;
  setImageAccountConcurrency: (value: string) => void;
  setImageSettleEnabled: (value: boolean) => void;
  setImageCheckBeforeHitEnabled: (value: boolean) => void;
  setImageSettleSecs: (value: string) => void;
  setImageTimeoutRetrySecs: (value: string) => void;
  setAutoRemoveInvalidAccounts: (value: boolean) => void;
  setAutoRemoveRateLimitedAccounts: (value: boolean) => void;
  setAutoReloginAfterRefresh: (value: boolean) => void;
  setLogLevel: (level: string, enabled: boolean) => void;
  setProxy: (value: string) => void;
  setBaseUrl: (value: string) => void;
  setGlobalSystemPrompt: (value: string) => void;
  setSensitiveWordsText: (value: string) => void;
  setAIReviewField: (key: "enabled" | "base_url" | "api_key" | "model" | "prompt", value: string | boolean) => void;
  setImageStorageField: (key: keyof ImageStorageSettings, value: string | boolean) => void;
  testImageStorage: () => Promise<void>;
  syncImagesToWebDAV: () => Promise<void>;
  setBackupField: (key: keyof BackupSettings, value: string | boolean) => void;
  setBackupInclude: (key: keyof BackupSettings["include"], value: boolean) => void;

  loadRegister: (silent?: boolean) => Promise<void>;
  setRegisterConfig: (config: RegisterConfig) => void;
  setRegisterProxy: (value: string) => void;
  setRegisterTotal: (value: string) => void;
  setRegisterThreads: (value: string) => void;
  setRegisterMode: (value: "total" | "quota" | "available") => void;
  setRegisterTargetQuota: (value: string) => void;
  setRegisterTargetAvailable: (value: string) => void;
  setRegisterCheckInterval: (value: string) => void;
  setRegisterMailField: (key: "request_timeout" | "wait_timeout" | "wait_interval", value: string) => void;
  addRegisterProvider: () => void;
  updateRegisterProvider: (index: number, updates: Record<string, unknown>) => void;
  deleteRegisterProvider: (index: number) => void;
  saveRegister: () => Promise<void>;
  toggleRegister: () => Promise<void>;
  resetRegister: () => Promise<void>;

  loadPools: (silent?: boolean) => Promise<void>;
  openAddDialog: () => void;
  openEditDialog: (pool: CPAPool) => void;
  setDialogOpen: (open: boolean) => void;
  setFormName: (value: string) => void;
  setFormBaseUrl: (value: string) => void;
  setFormSecretKey: (value: string) => void;
  setShowSecret: (checked: boolean) => void;
  savePool: () => Promise<void>;
  deletePool: (pool: CPAPool) => Promise<void>;

  browseFiles: (pool: CPAPool) => Promise<void>;
  setBrowserOpen: (open: boolean) => void;
  toggleFile: (name: string, checked: boolean) => void;
  replaceSelectedNames: (names: string[]) => void;
  setFileQuery: (value: string) => void;
  setFilePage: (page: number) => void;
  setPageSize: (value: PageSizeOption) => void;
  startImport: () => Promise<void>;
};

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  config: null,
  isLoadingConfig: true,
  isSavingConfig: false,
  backups: [],
  backupState: null,
  isLoadingBackups: true,
  isRunningBackup: false,
  deletingBackupKey: null,
  isTestingBackup: false,
  isTestingImageStorage: false,
  isSyncingImageStorage: false,

  registerConfig: null,
  isLoadingRegister: true,
  isSavingRegister: false,

  pools: [],
  isLoadingPools: true,
  deletingId: null,
  loadingFilesId: null,

  dialogOpen: false,
  editingPool: null,
  formName: "",
  formBaseUrl: "",
  formSecretKey: "",
  showSecret: false,
  isSavingPool: false,

  browserOpen: false,
  browserPool: null,
  remoteFiles: [],
  selectedNames: [],
  fileQuery: "",
  filePage: 1,
  pageSize: "100",
  isStartingImport: false,

  initialize: async () => {
    await Promise.allSettled([get().loadConfig(), get().loadPools()]);
    const backup = get().config?.backup;
    const isConfigured = Boolean(
      String(backup?.account_id || "").trim()
      && String(backup?.access_key_id || "").trim()
      && String(backup?.secret_access_key || "").trim()
      && String(backup?.bucket || "").trim(),
    );
    if (isConfigured) {
      await get().loadBackups();
    } else {
      set({ backups: [], isLoadingBackups: false });
    }
  },

  loadConfig: async () => {
    set({ isLoadingConfig: true });
    try {
      const data = await fetchSettingsConfig();
      const normalized = normalizeConfig(data.config);
      set({
        config: normalized,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load system configuration");
    } finally {
      set({ isLoadingConfig: false });
    }
  },

  saveConfig: async () => {
    const { config } = get();
    if (!config) {
      return false;
    }

    set({ isSavingConfig: true });
    try {
      const data = await updateSettingsConfig({
        ...config,
        refresh_account_interval_minute: Math.max(1, Number(config.refresh_account_interval_minute) || 1),
        image_retention_days: Math.max(1, Number(config.image_retention_days) || 30),
        image_poll_timeout_secs: Math.max(1, Number(config.image_poll_timeout_secs) || 120),
        image_account_concurrency: Math.max(1, Number(config.image_account_concurrency) || 3),
        image_settle_enabled: Boolean(config.image_settle_enabled !== false),
        image_check_before_hit_enabled: Boolean(config.image_check_before_hit_enabled !== false),
        image_settle_secs: Math.max(0.5, Number(config.image_settle_secs) || 2.0),
        image_timeout_retry_secs: Math.max(1, Number(config.image_timeout_retry_secs) || 30),
        auto_remove_invalid_accounts: Boolean(config.auto_remove_invalid_accounts),
        auto_remove_rate_limited_accounts: Boolean(config.auto_remove_rate_limited_accounts),
        auto_relogin_after_refresh: Boolean(config.auto_relogin_after_refresh),
        proxy: config.proxy.trim(),
        base_url: String(config.base_url || "").trim(),
        global_system_prompt: String(config.global_system_prompt || "").trim(),
        sensitive_words: (config.sensitive_words || []).map((item) => String(item).trim()).filter(Boolean),
        ai_review: {
          enabled: Boolean(config.ai_review?.enabled),
          base_url: String(config.ai_review?.base_url || "").trim(),
          api_key: String(config.ai_review?.api_key || "").trim(),
          model: String(config.ai_review?.model || "").trim(),
          prompt: String(config.ai_review?.prompt || "").trim(),
        },
        image_storage: {
          enabled: Boolean(config.image_storage?.enabled),
          mode: config.image_storage?.enabled && ["webdav", "both"].includes(String(config.image_storage?.mode)) ? config.image_storage.mode : "local",
          webdav_url: String(config.image_storage?.webdav_url || "").trim(),
          webdav_username: String(config.image_storage?.webdav_username || "").trim(),
          webdav_password: String(config.image_storage?.webdav_password || "").trim(),
          webdav_root_path: String(config.image_storage?.webdav_root_path || "chatgpt2api/images").trim(),
          public_base_url: String(config.image_storage?.public_base_url || "").trim(),
        },
        backup: {
          ...(config.backup as BackupSettings),
          account_id: String(config.backup?.account_id || "").trim(),
          access_key_id: String(config.backup?.access_key_id || "").trim(),
          secret_access_key: String(config.backup?.secret_access_key || "").trim(),
          bucket: String(config.backup?.bucket || "").trim(),
          prefix: String(config.backup?.prefix || "backups").trim(),
          interval_minutes: Math.max(1, Number(config.backup?.interval_minutes) || 360),
          rotation_keep: Math.max(0, Number(config.backup?.rotation_keep) || 0),
          passphrase: String(config.backup?.passphrase || "").trim(),
        },
      });
      set({
        config: normalizeConfig(data.config),
      });
      toast.success("Configuration saved");
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save system configuration");
      return false;
    } finally {
      set({ isSavingConfig: false });
    }
  },

  setRefreshAccountIntervalMinute: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          refresh_account_interval_minute: value,
        },
      };
    });
  },

  setImageRetentionDays: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_retention_days: value } } : {});
  },

  setImagePollTimeoutSecs: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_poll_timeout_secs: value } } : {});
  },

  setImageAccountConcurrency: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_account_concurrency: value } } : {});
  },

  setImageSettleEnabled: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_settle_enabled: value, image_check_before_hit_enabled: value } } : {});
  },

  setImageCheckBeforeHitEnabled: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_check_before_hit_enabled: value } } : {});
  },

  setImageSettleSecs: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_settle_secs: value } } : {});
  },

  setImageTimeoutRetrySecs: (value) => {
    set((state) => state.config ? { config: { ...state.config, image_timeout_retry_secs: value } } : {});
  },

  setAutoRemoveInvalidAccounts: (value) => {
    set((state) => state.config ? { config: { ...state.config, auto_remove_invalid_accounts: value } } : {});
  },

  setAutoRemoveRateLimitedAccounts: (value) => {
    set((state) => state.config ? { config: { ...state.config, auto_remove_rate_limited_accounts: value } } : {});
  },

  setAutoReloginAfterRefresh: (value) => {
    set((state) => state.config ? { config: { ...state.config, auto_relogin_after_refresh: value } } : {});
  },

  setLogLevel: (level, enabled) => {
    set((state) => {
      if (!state.config) return {};
      const levels = new Set(state.config.log_levels || []);
      if (enabled) levels.add(level);
      else levels.delete(level);
      return { config: { ...state.config, log_levels: Array.from(levels) } };
    });
  },

  setProxy: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          proxy: value,
        },
      };
    });
  },

  setBaseUrl: (value) => {
    set((state) => {
      if (!state.config) {
        return {};
      }
      return {
        config: {
          ...state.config,
          base_url: value,
        },
      };
    });
  },

  setGlobalSystemPrompt: (value) => {
    set((state) => state.config ? { config: { ...state.config, global_system_prompt: value } } : {});
  },

  setSensitiveWordsText: (value) => {
    set((state) => state.config ? { config: { ...state.config, sensitive_words: value.split("\n") } } : {});
  },

  setAIReviewField: (key, value) => {
    set((state) => state.config ? { config: { ...state.config, ai_review: { ...(state.config.ai_review || {}), [key]: value } } } : {});
  },

  setImageStorageField: (key, value) => {
    set((state) => {
      if (!state.config?.image_storage) {
        return {};
      }
      const next = {
        ...state.config.image_storage,
        [key]: value,
      };
      if (key === "enabled" && !value) {
        next.mode = "local";
      }
      if (key === "enabled" && value && next.mode === "local") {
        next.mode = "webdav";
      }
      return {
        config: {
          ...state.config,
          image_storage: next,
        },
      };
    });
  },

  testImageStorage: async () => {
    set({ isTestingImageStorage: true });
    try {
      const saved = await get().saveConfig();
      if (!saved) {
        return;
      }
      const data = await testImageStorageConnection();
      if (data.result.ok) {
        toast.success(`WebDAV 连接可用：HTTP ${data.result.status}`);
      } else {
        toast.error(`WebDAV 连接失败：${data.result.error ?? `HTTP ${data.result.status}`}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试 WebDAV 失败");
    } finally {
      set({ isTestingImageStorage: false });
    }
  },

  syncImagesToWebDAV: async () => {
    set({ isSyncingImageStorage: true });
    try {
      const saved = await get().saveConfig();
      if (!saved) {
        return;
      }
      const data = await syncImageStorage();
      toast.success(`同步完成：上传 ${data.result.uploaded}，跳过 ${data.result.skipped}，失败 ${data.result.failed}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "同步图片失败");
    } finally {
      set({ isSyncingImageStorage: false });
    }
  },

  setBackupField: (key, value) => {
    set((state) => {
      if (!state.config?.backup) {
        return {};
      }
      return {
        config: {
          ...state.config,
          backup: {
            ...state.config.backup,
            [key]: value,
          },
        },
      };
    });
  },

  setBackupInclude: (key, value) => {
    set((state) => {
      if (!state.config?.backup) {
        return {};
      }
      return {
        config: {
          ...state.config,
          backup: {
            ...state.config.backup,
            include: {
              ...state.config.backup.include,
              [key]: value,
            },
          },
        },
      };
    });
  },

  loadBackups: async (silent = false) => {
    if (!silent) {
      set({ isLoadingBackups: true });
    }
    try {
      const data = await fetchBackups();
      set({
        backups: data.items,
        backupState: data.state,
      });
    } catch (error) {
      if (!silent) {
        toast.error(error instanceof Error ? error.message : "Failed to load backup list");
      }
    } finally {
      if (!silent) {
        set({ isLoadingBackups: false });
      }
    }
  },

  runBackup: async () => {
    set({ isRunningBackup: true });
    try {
      const saved = await get().saveConfig();
      if (!saved) {
        return;
      }
      const data = await runBackupNow();
      toast.success(`Backup completed: ${data.result.key}`);
      await get().loadBackups(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Backup execution failed");
    } finally {
      set({ isRunningBackup: false });
    }
  },

  removeBackup: async (key) => {
    set({ deletingBackupKey: key });
    try {
      await deleteBackup(key);
      toast.success("Backup deleted");
      await get().loadBackups(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete backup");
    } finally {
      set({ deletingBackupKey: null });
    }
  },

  testBackup: async () => {
    set({ isTestingBackup: true });
    try {
      const saved = await get().saveConfig();
      if (!saved) {
        return;
      }
      const data = await testBackupConnection();
      toast.success(`R2 connection normal (HTTP ${data.result.status})`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to test backup connection");
    } finally {
      set({ isTestingBackup: false });
    }
  },

  loadRegister: async (silent = false) => {
    if (!silent) set({ isLoadingRegister: true });
    try {
      const data = await fetchRegisterConfig();
      set({ registerConfig: data.register });
    } catch (error) {
      if (!silent) toast.error(error instanceof Error ? error.message : "Failed to load registration configuration");
    } finally {
      if (!silent) set({ isLoadingRegister: false });
    }
  },

  setRegisterConfig: (config) => {
    set({ registerConfig: config, isLoadingRegister: false });
  },

  setRegisterProxy: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, proxy: value } } : {});
  },

  setRegisterTotal: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, total: Number(value) || 0 } } : {});
  },

  setRegisterThreads: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, threads: Number(value) || 0 } } : {});
  },

  setRegisterMode: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, mode: value } } : {});
  },

  setRegisterTargetQuota: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, target_quota: Number(value) || 0 } } : {});
  },

  setRegisterTargetAvailable: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, target_available: Number(value) || 0 } } : {});
  },

  setRegisterCheckInterval: (value) => {
    set((state) => state.registerConfig ? { registerConfig: { ...state.registerConfig, check_interval: Number(value) || 0 } } : {});
  },

  setRegisterMailField: (key, value) => {
    set((state) => state.registerConfig ? {
      registerConfig: {
        ...state.registerConfig,
        mail: { ...state.registerConfig.mail, [key]: Number(value) || 0 },
      },
    } : {});
  },

  addRegisterProvider: () => {
    set((state) => state.registerConfig ? {
      registerConfig: {
        ...state.registerConfig,
        mail: {
          ...state.registerConfig.mail,
          providers: [
            ...(state.registerConfig.mail.providers || []),
            { enable: true, type: "cloudmail_gen", api_base: "", admin_email: "", admin_password: "", domain: [], subdomain: [], email_prefix: "" },
          ],
        },
      },
    } : {});
  },

  updateRegisterProvider: (index, updates) => {
    set((state) => {
      if (!state.registerConfig) return {};
      const providers = [...(state.registerConfig.mail.providers || [])];
      providers[index] = { ...(providers[index] || {}), ...updates };
      return { registerConfig: { ...state.registerConfig, mail: { ...state.registerConfig.mail, providers } } };
    });
  },

  deleteRegisterProvider: (index) => {
    set((state) => state.registerConfig ? {
      registerConfig: {
        ...state.registerConfig,
        mail: {
          ...state.registerConfig.mail,
          providers: (state.registerConfig.mail.providers || []).filter((_, itemIndex) => itemIndex !== index),
        },
      },
    } : {});
  },

  saveRegister: async () => {
    const { registerConfig } = get();
    if (!registerConfig) return;
    try {
      set({ isSavingRegister: true });
      const data = await updateRegisterConfig({
        mail: registerConfig.mail,
        proxy: registerConfig.proxy.trim(),
        total: Math.max(1, Number(registerConfig.total) || 1),
        threads: Math.max(1, Number(registerConfig.threads) || 1),
        mode: registerConfig.mode,
        target_quota: Math.max(1, Number(registerConfig.target_quota) || 1),
        target_available: Math.max(1, Number(registerConfig.target_available) || 1),
        check_interval: Math.max(1, Number(registerConfig.check_interval) || 5),
      });
      set({ registerConfig: data.register });
      toast.success("Registration configuration saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save registration configuration");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  toggleRegister: async () => {
    const { registerConfig } = get();
    if (!registerConfig) return;
    set({ isSavingRegister: true });
    try {
      if (!registerConfig.enabled) {
        await updateRegisterConfig({
          mail: registerConfig.mail,
          proxy: registerConfig.proxy.trim(),
          total: Math.max(1, Number(registerConfig.total) || 1),
          threads: Math.max(1, Number(registerConfig.threads) || 1),
          mode: registerConfig.mode,
          target_quota: Math.max(1, Number(registerConfig.target_quota) || 1),
          target_available: Math.max(1, Number(registerConfig.target_available) || 1),
          check_interval: Math.max(1, Number(registerConfig.check_interval) || 5),
        });
      }
      const data = registerConfig.enabled ? await stopRegister() : await startRegister();
      set({ registerConfig: data.register });
      toast.success(registerConfig.enabled ? "Registration task stopped" : "Registration task started");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to toggle registration status");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  resetRegister: async () => {
    set({ isSavingRegister: true });
    try {
      const data = await resetRegisterApi();
      set({ registerConfig: data.register });
      toast.success("Registration statistics reset");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to reset registration statistics");
    } finally {
      set({ isSavingRegister: false });
    }
  },

  loadPools: async (silent = false) => {
    if (!silent) {
      set({ isLoadingPools: true });
    }
    try {
      const data = await fetchCPAPools();
      set({ pools: data.pools });
    } catch (error) {
      if (!silent) {
        toast.error(error instanceof Error ? error.message : "Failed to load CPA connection");
      }
    } finally {
      if (!silent) {
        set({ isLoadingPools: false });
      }
    }
  },

  openAddDialog: () => {
    set({
      editingPool: null,
      formName: "",
      formBaseUrl: "",
      formSecretKey: "",
      showSecret: false,
      dialogOpen: true,
    });
  },

  openEditDialog: (pool) => {
    set({
      editingPool: pool,
      formName: pool.name,
      formBaseUrl: pool.base_url,
      formSecretKey: "",
      showSecret: false,
      dialogOpen: true,
    });
  },

  setDialogOpen: (open) => {
    set({ dialogOpen: open });
  },

  setFormName: (value) => {
    set({ formName: value });
  },

  setFormBaseUrl: (value) => {
    set({ formBaseUrl: value });
  },

  setFormSecretKey: (value) => {
    set({ formSecretKey: value });
  },

  setShowSecret: (checked) => {
    set({ showSecret: checked });
  },

  savePool: async () => {
    const { editingPool, formName, formBaseUrl, formSecretKey } = get();
    if (!formBaseUrl.trim()) {
      toast.error("Please enter CPA address");
      return;
    }
    if (!editingPool && !formSecretKey.trim()) {
      toast.error("Please enter Secret Key");
      return;
    }

    set({ isSavingPool: true });
    try {
      if (editingPool) {
        const data = await updateCPAPool(editingPool.id, {
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          secret_key: formSecretKey.trim() || undefined,
        });
        set({ pools: data.pools, dialogOpen: false });
        toast.success("Connection updated");
      } else {
        const data = await createCPAPool({
          name: formName.trim(),
          base_url: formBaseUrl.trim(),
          secret_key: formSecretKey.trim(),
        });
        set({ pools: data.pools, dialogOpen: false });
        toast.success("Connection added");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Save failed");
    } finally {
      set({ isSavingPool: false });
    }
  },

  deletePool: async (pool) => {
    set({ deletingId: pool.id });
    try {
      const data = await deleteCPAPool(pool.id);
      set({ pools: data.pools });
      toast.success("Connection deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed");
    } finally {
      set({ deletingId: null });
    }
  },

  browseFiles: async (pool) => {
    set({ loadingFilesId: pool.id });
    try {
      const data = await fetchCPAPoolFiles(pool.id);
      const files = normalizeFiles(data.files);
      set({
        browserPool: pool,
        remoteFiles: files,
        selectedNames: [],
        fileQuery: "",
        filePage: 1,
        browserOpen: true,
      });
      toast.success(`Read successfully, ${files.length} remote accounts found`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to read remote accounts");
    } finally {
      set({ loadingFilesId: null });
    }
  },

  setBrowserOpen: (open) => {
    set({ browserOpen: open });
  },

  toggleFile: (name, checked) => {
    set((state) => {
      if (checked) {
        return {
          selectedNames: Array.from(new Set([...state.selectedNames, name])),
        };
      }
      return {
        selectedNames: state.selectedNames.filter((item) => item !== name),
      };
    });
  },

  replaceSelectedNames: (names) => {
    set({ selectedNames: Array.from(new Set(names)) });
  },

  setFileQuery: (value) => {
    set({ fileQuery: value, filePage: 1 });
  },

  setFilePage: (page) => {
    set({ filePage: page });
  },

  setPageSize: (value) => {
    set({ pageSize: value, filePage: 1 });
  },

  startImport: async () => {
    const { browserPool, selectedNames, pools } = get();
    if (!browserPool) {
      return;
    }
    if (selectedNames.length === 0) {
      toast.error("Please select accounts to import first");
      return;
    }

    set({ isStartingImport: true });
    try {
      const result = await startCPAImport(browserPool.id, selectedNames);
      set({
        pools: pools.map((pool) =>
          pool.id === browserPool.id ? { ...pool, import_job: result.import_job } : pool,
        ),
        browserOpen: false,
      });
      toast.success("Import task started");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to start import");
    } finally {
      set({ isStartingImport: false });
    }
  },
}));
