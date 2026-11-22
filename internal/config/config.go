package config

import (
	"errors"
	"fmt"
	"net/netip"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"gopkg.in/yaml.v3"
)

type Config struct {
	APIKey         string          `yaml:"api-key" json:"-"`
	DatabaseURL    string          `yaml:"-" json:"-"`
	BaseURL        string          `yaml:"base_url" json:"base_url"`
	Proxy          string          `yaml:"proxy" json:"proxy"`
	SystemPrompt   string          `yaml:"global_system_prompt" json:"global_system_prompt"`
	DefaultModel   string          `yaml:"default_upstream_model_name" json:"default_upstream_model_name"`
	ThinkingEffort string          `yaml:"default_thinking_effort" json:"default_thinking_effort"`
	ImageModelName string          `yaml:"image_model_name" json:"image_model_name"`
	Account        AccountSettings `yaml:"account" json:"account"`
	Image          ImageSettings   `yaml:"image" json:"image"`
	ProxyRuntime   ProxyRuntime    `yaml:"proxy_runtime" json:"proxy_runtime"`
	Cache          CacheSettings   `yaml:"chat_completion_cache" json:"chat_completion_cache"`
	MaxUploadMB    int64           `yaml:"max_upload_mb" json:"max_upload_mb"`
	Port           string          `yaml:"-" json:"-"`
	Bind           string          `yaml:"-" json:"-"`
	Version        string          `yaml:"-" json:"-"`
	path           string
	raw            map[string]any
	mu             sync.RWMutex
}

// 未配置对外生图模型名称时使用的名称
const defaultImageModelName = "gpt-image-2.6"

type AccountSettings struct {
	RefreshIntervalMinute int  `yaml:"refresh_interval_minute" json:"refresh_interval_minute"`
	AutoRemoveInvalid     bool `yaml:"auto_remove_invalid" json:"auto_remove_invalid"`
	RemoveConversation    bool `yaml:"remove_conversation_after_result" json:"remove_conversation_after_result"`
}

type ImageSettings struct {
	RetentionDays          int          `yaml:"retention_days" json:"retention_days"`
	PollTimeoutSeconds     int          `yaml:"poll_timeout_secs" json:"poll_timeout_secs"`
	PollIntervalSeconds    float64      `yaml:"poll_interval_secs" json:"poll_interval_secs"`
	PollInitialWaitSeconds float64      `yaml:"poll_initial_wait_secs" json:"poll_initial_wait_secs"`
	AccountConcurrency     int          `yaml:"account_concurrency" json:"account_concurrency"`
	AccountRetries         int          `yaml:"account_retries" json:"account_retries"`
	CodexModel             string       `yaml:"codex_model" json:"codex_model"`
	CodexImageModel        string       `yaml:"codex_image_model" json:"codex_image_model"`
	MinFreeMB              int          `yaml:"min_free_mb" json:"min_free_mb"`
	Storage                ImageStorage `yaml:"storage" json:"storage"`
}

type ImageStorage struct {
	Enabled        bool   `yaml:"enabled" json:"enabled"`
	Mode           string `yaml:"mode" json:"mode"`
	WebDAVURL      string `yaml:"webdav_url" json:"webdav_url"`
	WebDAVUsername string `yaml:"webdav_username" json:"webdav_username"`
	WebDAVPassword string `yaml:"webdav_password" json:"-"`
	WebDAVRootPath string `yaml:"webdav_root_path" json:"webdav_root_path"`
	PublicBaseURL  string `yaml:"public_base_url" json:"public_base_url"`
}

type ProxyRuntime struct {
	Enabled          bool              `yaml:"enabled" json:"enabled"`
	EgressMode       string            `yaml:"egress_mode" json:"egress_mode"`
	ProxyURL         string            `yaml:"proxy_url" json:"proxy_url"`
	ResourceProxyURL string            `yaml:"resource_proxy_url" json:"resource_proxy_url"`
	Clearance        ClearanceSettings `yaml:"clearance" json:"clearance"`
}

type ClearanceSettings struct {
	Mode            string `yaml:"mode" json:"mode"`
	CFCookies       string `yaml:"cf_cookies" json:"-"`
	CFClearance     string `yaml:"cf_clearance" json:"-"`
	UserAgent       string `yaml:"user_agent" json:"user_agent"`
	FlareSolverrURL string `yaml:"flaresolverr_url" json:"flaresolverr_url"`
	TimeoutSeconds  int    `yaml:"timeout_sec" json:"timeout_sec"`
	RefreshInterval int    `yaml:"refresh_interval" json:"refresh_interval"`
}

type CacheSettings struct {
	Enabled                bool `yaml:"enabled" json:"enabled"`
	TTLSeconds             int  `yaml:"ttl_seconds" json:"ttl_seconds"`
	MaxEntries             int  `yaml:"max_entries" json:"max_entries"`
	StreamCache            bool `yaml:"stream_cache" json:"stream_cache"`
	NormalizeMessages      bool `yaml:"normalize_messages" json:"normalize_messages"`
	DropAdjacentDuplicates bool `yaml:"drop_adjacent_duplicates" json:"drop_adjacent_duplicates"`
	DropAssistantHistory   bool `yaml:"drop_assistant_history" json:"drop_assistant_history"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	cfg := &Config{DefaultModel: "auto", ThinkingEffort: "auto", MaxUploadMB: 50, Port: "3000", Version: "0.0.0", path: path, raw: map[string]any{}, Account: AccountSettings{RefreshIntervalMinute: 5, AutoRemoveInvalid: true}, Image: ImageSettings{RetentionDays: 30, PollTimeoutSeconds: 300, PollIntervalSeconds: 5, PollInitialWaitSeconds: 10, AccountConcurrency: 3, AccountRetries: 2, CodexModel: "gpt-6-luna", CodexImageModel: "gpt-image-2.6", MinFreeMB: 500, Storage: ImageStorage{Mode: "local", WebDAVRootPath: "chatgpt2api/images"}}, Cache: CacheSettings{Enabled: true, TTLSeconds: 60, MaxEntries: 256, StreamCache: true, NormalizeMessages: true, DropAdjacentDuplicates: true}}
	if len(data) > 0 {
		if err := yaml.Unmarshal(data, cfg); err != nil {
			return nil, err
		}
		if err := yaml.Unmarshal(data, &cfg.raw); err != nil {
			return nil, err
		}
	}
	if cfg.ImageModelName == "" {
		cfg.ImageModelName = defaultImageModelName
	}
	cfg.DatabaseURL = os.Getenv("DATABASE_URL")
	if cfg.DatabaseURL == "" {
		cfg.DatabaseURL = "sqlite:///" + filepath.Join("data", "chatgpt2api.db")
	}
	if value := os.Getenv("CHATGPT2API_AUTH_KEY"); value != "" {
		cfg.APIKey = value
	}
	if value := os.Getenv("PORT"); value != "" {
		cfg.Port = value
	}
	// 监听地址。默认空 = 监听全部网卡(0.0.0.0)，与历史行为一致。
	// 需要收紧到回环时设 BIND_ADDR=127.0.0.1；端口仍由 PORT 决定，不要写进 BIND_ADDR。
	if value := strings.TrimSpace(os.Getenv("BIND_ADDR")); value != "" {
		if err := validateBind(value); err != nil {
			return nil, err
		}
		cfg.Bind = value
	}
	if data, err := os.ReadFile("VERSION"); err == nil && strings.TrimSpace(string(data)) != "" {
		cfg.Version = strings.TrimSpace(string(data))
	}
	if cfg.APIKey == "" {
		return nil, errors.New("请先在 config.yaml 或 CHATGPT2API_AUTH_KEY 中设置管理员密钥")
	}
	return cfg, nil
}

// validateBind 只接受裸的监听地址（IP 或主机名），端口必须通过 PORT 配置。
// 否则 net.JoinHostPort 会把 "127.0.0.1:8080" 当成主机名，启动时只报难以理解的解析错误。
func validateBind(value string) error {
	if _, err := netip.ParseAddr(value); err == nil {
		return nil
	}
	if strings.ContainsAny(value, ":/[]") {
		return fmt.Errorf("BIND_ADDR 只填写监听地址（IP 或主机名），不要包含端口或方括号；端口请用 PORT 配置：%q", value)
	}
	if strings.ContainsAny(value, " \t\r\n%") {
		return fmt.Errorf("BIND_ADDR 不是合法的监听地址：%q", value)
	}
	return nil
}

func (c *Config) Public() map[string]any {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.publicLocked()
}

func (c *Config) Update(values map[string]any) (map[string]any, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	image, _ := c.raw["image"].(map[string]any)
	if image == nil {
		image = map[string]any{}
	}
	account, _ := c.raw["account"].(map[string]any)
	if account == nil {
		account = map[string]any{}
	}
	imageFields := map[string]string{"image_retention_days": "retention_days", "image_poll_timeout_secs": "poll_timeout_secs", "image_poll_interval_secs": "poll_interval_secs", "image_poll_initial_wait_secs": "poll_initial_wait_secs", "image_account_concurrency": "account_concurrency", "image_account_retries": "account_retries", "image_codex_model": "codex_model", "image_codex_image_model": "codex_image_model", "image_min_free_mb": "min_free_mb"}
	accountFields := map[string]string{"refresh_account_interval_minute": "refresh_interval_minute", "auto_remove_invalid_accounts": "auto_remove_invalid", "remove_conversation_after_result": "remove_conversation_after_result"}
	for field, key := range imageFields {
		if value, ok := values[field]; ok {
			image[key] = value
			delete(values, field)
		}
	}
	for field, key := range accountFields {
		if value, ok := values[field]; ok {
			account[key] = value
			delete(values, field)
		}
	}
	if value, ok := values["image_storage"]; ok {
		if storage, ok := value.(map[string]any); ok {
			previous, _ := image["storage"].(map[string]any)
			if storage["webdav_password"] == nil || storage["webdav_password"] == "" {
				storage["webdav_password"] = previous["webdav_password"]
			}
			delete(storage, "has_webdav_password")
		}
		image["storage"] = value
		delete(values, "image_storage")
	}
	c.raw["image"], c.raw["account"] = image, account
	for key, value := range values {
		if key != "api-key" {
			if key == "proxy_runtime" {
				value = preserveClearance(c.raw[key], value)
			}
			c.raw[key] = value
		}
	}
	data, err := yaml.Marshal(c.raw)
	if err != nil {
		return nil, err
	}
	if err := os.WriteFile(c.path, data, 0600); err != nil {
		return nil, err
	}
	var current Config
	if err := yaml.Unmarshal(data, &current); err != nil {
		return nil, err
	}
	c.Proxy, c.BaseURL, c.SystemPrompt, c.DefaultModel, c.ThinkingEffort, c.Account, c.Image, c.ProxyRuntime, c.Cache = current.Proxy, current.BaseURL, current.SystemPrompt, current.DefaultModel, current.ThinkingEffort, current.Account, current.Image, current.ProxyRuntime, current.Cache
	c.ImageModelName = current.ImageModelName
	if current.MaxUploadMB > 0 {
		c.MaxUploadMB = current.MaxUploadMB
	}
	if c.ImageModelName == "" {
		c.ImageModelName = defaultImageModelName
	}
	return c.publicLocked(), nil
}

func (c *Config) publicLocked() map[string]any {
	result := publicCopy(c.raw)
	delete(result, "image")
	delete(result, "account")
	result["image_model_name"] = c.ImageModelName
	result["image_retention_days"] = c.Image.RetentionDays
	result["image_poll_timeout_secs"] = c.Image.PollTimeoutSeconds
	result["image_poll_interval_secs"] = c.Image.PollIntervalSeconds
	result["image_poll_initial_wait_secs"] = c.Image.PollInitialWaitSeconds
	result["image_account_concurrency"] = c.Image.AccountConcurrency
	result["image_account_retries"] = c.Image.AccountRetries
	result["image_codex_model"] = c.Image.CodexModel
	result["image_codex_image_model"] = c.Image.CodexImageModel
	result["image_min_free_mb"] = c.Image.MinFreeMB
	result["refresh_account_interval_minute"] = c.Account.RefreshIntervalMinute
	result["auto_remove_invalid_accounts"] = c.Account.AutoRemoveInvalid
	result["remove_conversation_after_result"] = c.Account.RemoveConversation
	storage := map[string]any{}
	data, _ := yaml.Marshal(c.Image.Storage)
	yaml.Unmarshal(data, &storage)
	storage["has_webdav_password"] = c.Image.Storage.WebDAVPassword != ""
	delete(storage, "webdav_password")
	result["image_storage"] = storage
	maskSecrets(result)
	return result
}
func publicCopy(values map[string]any) map[string]any {
	data, _ := yaml.Marshal(values)
	result := map[string]any{}
	yaml.Unmarshal(data, &result)
	delete(result, "api-key")
	return result
}
func maskSecrets(values map[string]any) {
	if runtime, ok := values["proxy_runtime"].(map[string]any); ok {
		if clearance, ok := runtime["clearance"].(map[string]any); ok {
			cookies, _ := clearance["cf_cookies"].(string)
			token, _ := clearance["cf_clearance"].(string)
			clearance["has_cf_cookies"] = cookies != ""
			clearance["has_cf_clearance"] = token != ""
			delete(clearance, "cf_cookies")
			delete(clearance, "cf_clearance")
		}
	}
}
func preserveClearance(current any, incoming any) any {
	next, ok := incoming.(map[string]any)
	if !ok {
		return incoming
	}
	previous, _ := current.(map[string]any)
	previousClearance, _ := previous["clearance"].(map[string]any)
	clearance, _ := next["clearance"].(map[string]any)
	if clearance == nil {
		return incoming
	}
	if clearance["has_cf_cookies"] == true && clearance["cf_cookies"] == nil {
		clearance["cf_cookies"] = previousClearance["cf_cookies"]
	}
	if clearance["has_cf_clearance"] == true && clearance["cf_clearance"] == nil {
		clearance["cf_clearance"] = previousClearance["cf_clearance"]
	}
	delete(clearance, "has_cf_cookies")
	delete(clearance, "has_cf_clearance")
	return next
}

