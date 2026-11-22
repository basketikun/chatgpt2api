package service

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"slices"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/repository"
	chatgpt "github.com/basketikun/chatgpt2api/internal/upstream"
)

const codexClientID = "app_EMoamEEZ73f0CkXaXp7hrann"

type AccountService struct {
	repo  *repository.Repository
	proxy *ProxyService
}

func NewAccountService(repo *repository.Repository, proxy *ProxyService) *AccountService {
	return &AccountService{repo: repo, proxy: proxy}
}

func (s *AccountService) List(ctx context.Context, page int, pageSize int, query string, accountType string, status string) ([]repository.Account, int64, []string, error) {
	return s.repo.AccountPage(ctx, page, pageSize, query, accountType, status)
}

func (s *AccountService) Add(ctx context.Context, items []repository.Account) (int, int, int, []map[string]string, error) {
	now := time.Now().UTC().Format(time.RFC3339)
	deduped := make(map[string]repository.Account, len(items))
	for _, item := range items {
		if err := applyTokenClaims(&item); err != nil {
			return 0, 0, 0, nil, err
		}
		current, err := s.repo.AccountByEmail(ctx, *item.Email)
		if err == nil {
			item = mergeImportedAccount(current, item)
		} else if !errors.Is(err, repository.ErrNotFound) {
			return 0, 0, 0, nil, err
		}
		if item.CreatedAt == "" {
			item.CreatedAt = now
		}
		if item.Status == "" {
			item.Status = "正常"
		}
		if item.Type == "" {
			item.Type = "free"
		}
		deduped[*item.Email] = item
	}
	items = items[:0]
	for _, item := range deduped {
		items = append(items, item)
	}
	added, skipped, err := s.repo.SaveAccounts(ctx, items)
	if err != nil {
		return 0, 0, 0, nil, err
	}
	refreshed, refreshErrors := s.Refresh(ctx, itemTokens(items))
	return added, skipped, refreshed, refreshErrors, nil
}

func (s *AccountService) Delete(ctx context.Context, tokens []string) (int64, error) {
	emails := make([]string, 0, len(tokens))
	for _, token := range tokens {
		emails = append(emails, tokenEmail(token))
	}
	return s.repo.DeleteAccounts(ctx, emails)
}

func (s *AccountService) Update(ctx context.Context, token string, values map[string]any) (repository.Account, error) {
	return s.repo.UpdateAccount(ctx, tokenEmail(token), values)
}

func (s *AccountService) Summary(ctx context.Context) (map[string]int64, error) {
	result, err := s.repo.AccountSummary(ctx)
	if err != nil {
		return nil, err
	}
	return result, nil
}
func (s *AccountService) Account(ctx context.Context, token string) (repository.Account, error) {
	return s.repo.AccountByEmail(ctx, tokenEmail(token))
}

func (s *AccountService) MarkTextUsed(ctx context.Context, token string) error {
	err := s.repo.TouchAccount(ctx, tokenEmail(token), time.Now().UTC().Format(time.RFC3339))
	if errors.Is(err, repository.ErrNotFound) {
		return nil
	}
	return err
}

func (s *AccountService) TextTokenForModel(ctx context.Context, excluded map[string]bool, accountTypes map[string]bool, model string) (string, error) {
	var types []string
	if accountTypes != nil {
		types = make([]string, 0, len(accountTypes))
		for accountType, allowed := range accountTypes {
			if allowed {
				types = append(types, accountType)
			}
		}
	}
	emails := make([]string, 0, len(excluded))
	for token := range excluded {
		emails = append(emails, tokenEmail(token))
	}
	item, err := s.repo.NextTextAccount(ctx, types, emails)
	if errors.Is(err, repository.ErrNotFound) {
		return "", fmt.Errorf("model %q is not available to any active account", model)
	}
	if err != nil {
		return "", err
	}
	return s.refreshToken(ctx, item, false)
}

func (s *AccountService) RefreshToken(ctx context.Context, token string, force bool) (string, error) {
	item, err := s.repo.AccountByEmail(ctx, tokenEmail(token))
	if err != nil {
		return "", err
	}
	return s.refreshToken(ctx, item, force)
}

func (s *AccountService) RefreshQuota(ctx context.Context, token string) (repository.Account, error) {
	return s.remoteInfo(ctx, token)
}

func (s *AccountService) RecordTextError(ctx context.Context, token string, err error) {
	s.recordRefreshError(ctx, token, err.Error())
}

func (s *AccountService) ImageToken(ctx context.Context, routes []string, plans []string) (string, error) {
	attempted := map[string]bool{}
	for attempts := 0; attempts < 20; {
		concurrency := max(1, s.proxy.config.Image.AccountConcurrency)
		selected, acquired, err := s.repo.AcquireImageAccount(ctx, routes, plans, concurrency, attempted)
		if err != nil {
			return "", err
		}
		if !acquired {
			available, err := s.repo.ImageAccountAvailable(ctx, routes, plans, attempted)
			if err != nil {
				return "", err
			}
			if !available {
				return "", fmt.Errorf("当前没有可用图片额度（已尝试 %d 个账号）", len(attempted))
			}
			select {
			case <-ctx.Done():
				return "", ctx.Err()
			case <-time.After(time.Second):
				continue
			}
		}
		attempts++
		attempted[*selected.Email] = true
		account, err := s.remoteInfo(ctx, selected.AccessToken)
		if err == nil && account.Status == "正常" && account.Quota > 0 && (account.IsCodex || slices.Contains(routes, "web")) && (len(plans) == 0 || slices.Contains(plans, account.Type)) {
			return account.AccessToken, nil
		}
		s.repo.ReleaseImageAccountByID(ctx, selected.ID)
	}
	return "", fmt.Errorf("当前没有可用图片额度（已尝试 %d 个账号）", len(attempted))
}

func (s *AccountService) ReleaseImageToken(ctx context.Context, token string, success bool) {
	s.repo.ReleaseImageAccount(ctx, tokenEmail(token), success, time.Now().UTC().Format(time.RFC3339))
}

func (s *AccountService) Refresh(ctx context.Context, tokens []string) (int, []map[string]string) {
	refreshed, failures := 0, []map[string]string{}
	var mu sync.Mutex
	var wait sync.WaitGroup
	slots := make(chan struct{}, 8)
	for _, token := range tokens {
		slots <- struct{}{}
		wait.Add(1)
		go func(token string) {
			defer wait.Done()
			defer func() { <-slots }()
			item, err := s.remoteInfo(ctx, token)
			mu.Lock()
			defer mu.Unlock()
			if err != nil {
				failures = append(failures, map[string]string{"token": tokenID(token), "error": err.Error()})
			} else if item.AccessToken != "" {
				refreshed++
			}
		}(token)
	}
	wait.Wait()
	return refreshed, failures
}

func (s *AccountService) RefreshAll(ctx context.Context) (int, []map[string]string, error) {
	items, err := s.repo.Accounts(ctx)
	if err != nil {
		return 0, nil, err
	}
	refreshed, failures := s.Refresh(ctx, itemTokens(items))
	return refreshed, failures, nil
}

func (s *AccountService) RefreshScheduled(ctx context.Context) error {
	items, err := s.repo.Accounts(ctx)
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	checks, keepalive, expiring := []string{}, []repository.Account{}, map[string]bool{}
	for _, item := range items {
		if item.Status == "正常" || item.Status == "限流" {
			checks = append(checks, item.AccessToken)
			if tokenNeedsRefresh(item.AccessToken) && item.RefreshToken != "" {
				expiring[item.AccessToken] = true
			}
		}
		if item.RefreshToken != "" && item.Status != "禁用" && refreshKeepaliveDue(item, now) {
			keepalive = append(keepalive, item)
		}
	}
	if len(checks) > 0 {
		s.Refresh(ctx, checks)
	}
	sort.Slice(keepalive, func(i int, j int) bool {
		return refreshKeepaliveAnchor(keepalive[i]).Before(refreshKeepaliveAnchor(keepalive[j]))
	})
	count := 0
	for _, item := range keepalive {
		if count == 3 {
			break
		}
		if expiring[item.AccessToken] {
			continue
		}
		s.refreshToken(ctx, item, true)
		count++
	}
	return nil
}

func (s *AccountService) refreshToken(ctx context.Context, item repository.Account, force bool) (string, error) {
	current, err := s.repo.AccountByEmail(ctx, *item.Email)
	if err != nil {
		return item.AccessToken, nil
	}
	item = current
	claims := tokenClaims(item.AccessToken)
	expiry, _ := claims["exp"].(float64)
	if item.RefreshToken == "" || !force && (expiry == 0 || time.Until(time.Unix(int64(expiry), 0)) > 24*time.Hour) {
		return item.AccessToken, nil
	}
	clientID, _ := claims["client_id"].(string)
	if clientID == "" {
		s.recordRefreshError(ctx, item.AccessToken, "refresh token failed: missing client_id")
		return item.AccessToken, nil
	}
	form := url.Values{"grant_type": {"refresh_token"}, "refresh_token": {item.RefreshToken}, "client_id": {clientID}}
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, openAIAuthBase+"/oauth/token", strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("User-Agent", openAIUserAgent)
	response, err := s.proxy.Client(item.Proxy, false, false).Do(req)
	if err != nil {
		s.recordRefreshError(ctx, item.AccessToken, err.Error())
		return item.AccessToken, nil
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		s.recordRefreshError(ctx, item.AccessToken, err.Error())
		return item.AccessToken, nil
	}
	result := map[string]any{}
	json.Unmarshal(body, &result)
	newToken, _ := result["access_token"].(string)
	if response.StatusCode != http.StatusOK || newToken == "" {
		detail, _ := result["error_description"].(string)
		if detail == "" {
			detail, _ = result["error"].(string)
		}
		if detail == "" {
			detail, _ = result["message"].(string)
		}
		if detail == "" {
			detail = string(body)
		}
		if len(detail) > 300 {
			detail = detail[:300]
		}
		s.recordRefreshError(ctx, item.AccessToken, fmt.Sprintf("oauth_refresh_http_%d: %s", response.StatusCode, detail))
		return item.AccessToken, nil
	}
	updated := item
	updated.AccessToken = newToken
	if value, _ := result["refresh_token"].(string); value != "" {
		updated.RefreshToken = value
	}
	if value, _ := result["id_token"].(string); value != "" {
		updated.IDToken = value
	}
	updated.LastRefreshAt = stringPointer(time.Now().UTC().Format(time.RFC3339))
	updated.LastError = nil
	if _, err := s.repo.ReplaceAccountToken(ctx, *item.Email, updated); err != nil {
		s.recordRefreshError(ctx, item.AccessToken, err.Error())
		return item.AccessToken, err
	}
	return newToken, nil
}

func (s *AccountService) remoteInfo(ctx context.Context, token string) (repository.Account, error) {
	email := tokenEmail(token)
	item, err := s.repo.AccountByEmail(ctx, email)
	if err != nil {
		return repository.Account{}, err
	}
	active, _ := s.refreshToken(ctx, item, false)
	item, err = s.repo.AccountByEmail(ctx, email)
	if err != nil {
		return repository.Account{}, err
	}
	remaining, resetAfter, err := chatgpt.NewOpenAIBackendAPI(active, item.Proxy, s.proxy, s.proxy.config).WithAccountID(item.AccountID).QuotaInfo(ctx)
	if err != nil && invalidTokenError(err) {
		refreshed, _ := s.refreshToken(ctx, item, true)
		if refreshed != active {
			item, err = s.repo.AccountByEmail(ctx, email)
			if err != nil {
				return repository.Account{}, err
			}
			remaining, resetAfter, err = chatgpt.NewOpenAIBackendAPI(refreshed, item.Proxy, s.proxy, s.proxy.config).WithAccountID(item.AccountID).QuotaInfo(ctx)
			active = refreshed
		}
	}
	if err != nil {
		if invalidTokenError(err) {
			s.recordRefreshError(ctx, active, err.Error())
			s.RemoveInvalid(ctx, active)
		}
		return repository.Account{}, err
	}
	item.Quota, item.Remaining, item.ResetAfter = remaining, remaining, stringPointer(resetAfter)
	if remaining == 0 {
		item.Status = "限流"
	} else {
		item.Status = "正常"
	}
	item.LastError = nil
	return s.repo.UpdateAccount(ctx, email, map[string]any{"quota": item.Quota, "remaining": item.Remaining, "reset_after": item.ResetAfter, "status": item.Status, "last_error": nil})
}

func itemTokens(items []repository.Account) []string {
	result := make([]string, 0, len(items))
	for _, item := range items {
		result = append(result, item.AccessToken)
	}
	return result
}
func tokenClaims(token string) map[string]any {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return map[string]any{}
	}
	data, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return map[string]any{}
	}
	result := map[string]any{}
	json.Unmarshal(data, &result)
	return result
}
func tokenEmail(token string) string {
	profile, _ := tokenClaims(token)["https://api.openai.com/profile"].(map[string]any)
	email, _ := profile["email"].(string)
	return email
}
func tokenID(token string) string {
	if len(token) < 12 {
		return "token"
	}
	return token[:6] + "..." + token[len(token)-4:]
}
func stringPointer(value string) *string { return &value }

func (s *AccountService) recordRefreshError(ctx context.Context, token string, message string) {
	s.repo.UpdateAccount(ctx, tokenEmail(token), map[string]any{"last_error": message})
}

func (s *AccountService) RemoveInvalid(ctx context.Context, token string) {
	if s.proxy.config.Account.AutoRemoveInvalid {
		s.Delete(ctx, []string{token})
		return
	}
	s.repo.UpdateAccount(ctx, tokenEmail(token), map[string]any{"status": "异常", "quota": 0})
}

func invalidTokenError(err error) bool {
	if err == nil {
		return false
	}
	var upstreamError *chatgpt.UpstreamHTTPError
	return errors.Is(err, chatgpt.ErrTokenInvalidated) || errors.As(err, &upstreamError) && upstreamError.StatusCode == http.StatusUnauthorized
}

func tokenNeedsRefresh(token string) bool {
	expiry, _ := tokenClaims(token)["exp"].(float64)
	return expiry > 0 && time.Until(time.Unix(int64(expiry), 0)) <= 24*time.Hour
}

func refreshKeepaliveAnchor(item repository.Account) time.Time {
	if item.LastRefreshAt != nil {
		if parsed, err := accountTime(*item.LastRefreshAt); err == nil {
			return parsed
		}
	}
	issued, _ := tokenClaims(item.AccessToken)["iat"].(float64)
	if issued > 0 {
		return time.Unix(int64(issued), 0)
	}
	if parsed, err := accountTime(item.CreatedAt); err == nil {
		return parsed
	}
	return time.Time{}
}

func accountTime(value string) (time.Time, error) {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed, nil
	}
	return time.Parse("2006-01-02 15:04:05", value)
}

func refreshKeepaliveDue(item repository.Account, now time.Time) bool {
	anchor := refreshKeepaliveAnchor(item)
	return anchor.IsZero() || !anchor.Add(3*24*time.Hour).After(now)
}

func mergeImportedAccount(current repository.Account, incoming repository.Account) repository.Account {
	if incoming.RefreshToken == "" {
		incoming.RefreshToken = current.RefreshToken
	}
	if incoming.IDToken == "" {
		incoming.IDToken = current.IDToken
	}
	if incoming.Email == nil {
		incoming.Email = current.Email
	}
	if incoming.UserID == nil {
		incoming.UserID = current.UserID
	}
	if incoming.AccountID == "" {
		incoming.AccountID = current.AccountID
	}
	if incoming.Type == "" {
		incoming.Type = current.Type
	}
	if incoming.Status == "" {
		incoming.Status = current.Status
	}
	if incoming.Quota == 0 {
		incoming.Quota = current.Quota
	}
	if incoming.Proxy == "" {
		incoming.Proxy = current.Proxy
	}
	if incoming.Remaining == 0 {
		incoming.Remaining = current.Remaining
	}
	if incoming.ResetAfter == nil {
		incoming.ResetAfter = current.ResetAfter
	}
	if incoming.Success == 0 {
		incoming.Success = current.Success
	}
	if incoming.Fail == 0 {
		incoming.Fail = current.Fail
	}
	if incoming.LastUsedAt == nil {
		incoming.LastUsedAt = current.LastUsedAt
	}
	if incoming.LastRefreshAt == nil {
		incoming.LastRefreshAt = current.LastRefreshAt
	}
	if incoming.LastError == nil {
		incoming.LastError = current.LastError
	}
	if incoming.ImageInflight == 0 {
		incoming.ImageInflight = current.ImageInflight
	}
	if incoming.CreatedAt == "" {
		incoming.CreatedAt = current.CreatedAt
	}
	incoming.ID = current.ID
	return incoming
}

func applyTokenClaims(item *repository.Account) error {
	parts := strings.Split(item.AccessToken, ".")
	if len(parts) != 3 {
		return errors.New("access_token 声明格式不正确")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return err
	}
	var claims map[string]any
	if json.Unmarshal(payload, &claims) != nil {
		return errors.New("access_token 声明解析失败")
	}
	item.IsCodex = claims["client_id"] == codexClientID
	auth, ok := claims["https://api.openai.com/auth"].(map[string]any)
	if !ok {
		return errors.New("access_token 缺少账号声明")
	}
	plan, _ := auth["chatgpt_plan_type"].(string)
	if plan == "" {
		plan = "free"
	}
	item.Type = strings.ToLower(plan)
	if auth != nil {
		if value, ok := auth["chatgpt_user_id"].(string); ok {
			item.UserID = &value
		}
		if value, ok := auth["chatgpt_account_id"].(string); ok {
			item.AccountID = value
		}
	}
	if profile, ok := claims["https://api.openai.com/profile"].(map[string]any); ok {
		if value, ok := profile["email"].(string); ok {
			item.Email = &value
		}
	}
	if item.Email == nil {
		return errors.New("access_token 缺少邮箱声明")
	}
	return nil
}
