package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/google/uuid"
)

const subListLimit = 10000

type SourceService struct {
	repo     *repository.Repository
	accounts *AccountService
	proxy    *ProxyService
}

func NewSourceService(repo *repository.Repository, accounts *AccountService, proxy *ProxyService) *SourceService {
	updatedAt := time.Now().UTC().Format(time.RFC3339)
	repo.FailCPAImports(context.Background(), updatedAt)
	repo.FailSubImports(context.Background(), updatedAt)
	return &SourceService{repo: repo, accounts: accounts, proxy: proxy}
}
func (s *SourceService) CPAs(ctx context.Context) ([]repository.CPA, error) {
	return s.repo.CPAs(ctx)
}
func (s *SourceService) CPA(ctx context.Context, id string) (repository.CPA, error) {
	return s.repo.CPA(ctx, id)
}
func (s *SourceService) SaveCPA(ctx context.Context, item repository.CPA) (repository.CPA, error) {
	if item.ID == "" {
		item.ID = id32()
	}
	return item, s.repo.SaveCPA(ctx, item)
}
func (s *SourceService) DeleteCPA(ctx context.Context, id string) error {
	return s.repo.DeleteCPA(ctx, id)
}
func (s *SourceService) Subs(ctx context.Context) ([]repository.Sub, error) {
	return s.repo.Subs(ctx)
}
func (s *SourceService) Sub(ctx context.Context, id string) (repository.Sub, error) {
	return s.repo.Sub(ctx, id)
}
func (s *SourceService) SaveSub(ctx context.Context, item repository.Sub) (repository.Sub, error) {
	if item.ID == "" {
		item.ID = id32()
	}
	return item, s.repo.SaveSub(ctx, item)
}
func (s *SourceService) DeleteSub(ctx context.Context, id string) error {
	return s.repo.DeleteSub(ctx, id)
}

func (s *SourceService) CPAFiles(ctx context.Context, pool repository.CPA) ([]map[string]string, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimSuffix(pool.BaseURL, "/")+"/v0/management/auth-files", nil)
	req.Header.Set("Authorization", "Bearer "+pool.SecretKey)
	req.Header.Set("Accept", "application/json")
	response, err := s.proxy.Client("", false, false).Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, errors.New(response.Status)
	}
	var payload struct {
		Files []map[string]any `json:"files"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, err
	}
	items := make([]map[string]string, 0, len(payload.Files))
	for _, file := range payload.Files {
		name, _ := file["name"].(string)
		email, _ := file["email"].(string)
		if email == "" {
			email, _ = file["account"].(string)
		}
		if name != "" {
			items = append(items, map[string]string{"name": name, "email": email})
		}
	}
	return items, nil
}

func (s *SourceService) ImportCPA(ctx context.Context, pool repository.CPA, names []string) (repository.ImportJob, error) {
	if len(names) == 0 {
		return repository.ImportJob{}, errors.New("selected files is required")
	}
	now := time.Now().UTC().Format(time.RFC3339)
	pool.ImportJob = repository.ImportJob{ID: id32(), Status: "pending", CreatedAt: now, UpdatedAt: now, Total: len(names), Errors: []map[string]any{}}
	if err := s.repo.SaveCPA(ctx, pool); err != nil {
		return repository.ImportJob{}, err
	}
	go s.runCPAImport(pool, names)
	return pool.ImportJob, nil
}

func (s *SourceService) runCPAImport(pool repository.CPA, names []string) {
	ctx := context.Background()
	pool.ImportJob.Status = "running"
	s.repo.SaveCPA(ctx, pool)
	tokens := []string{}
	type result struct {
		name  string
		token string
		err   error
	}
	results := make(chan result, len(names))
	semaphore := make(chan struct{}, min(16, len(names)))
	var wait sync.WaitGroup
	for _, name := range names {
		wait.Add(1)
		go func(name string) {
			defer wait.Done()
			semaphore <- struct{}{}
			defer func() { <-semaphore }()
			token, err := s.fetchCPAToken(ctx, pool, name)
			results <- result{name: name, token: token, err: err}
		}(name)
	}
	go func() {
		wait.Wait()
		close(results)
	}()
	for item := range results {
		if item.err != nil {
			pool.ImportJob.Errors = append(pool.ImportJob.Errors, map[string]any{"name": item.name, "error": item.err.Error()})
			pool.ImportJob.Failed++
		} else {
			tokens = append(tokens, item.token)
		}
		pool.ImportJob.Completed++
		pool.ImportJob.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
		s.repo.SaveCPA(ctx, pool)
	}
	if len(tokens) == 0 {
		pool.ImportJob.Status = "failed"
		pool.ImportJob.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
		s.repo.SaveCPA(ctx, pool)
		return
	}
	accounts := make([]repository.Account, 0, len(tokens))
	for _, token := range tokens {
		accounts = append(accounts, repository.Account{AccessToken: token})
	}
	added, skipped, refreshed, _, _ := s.accounts.Add(ctx, accounts)
	pool.ImportJob.Added, pool.ImportJob.Skipped, pool.ImportJob.Refreshed = added, skipped, refreshed
	pool.ImportJob.Status = "completed"
	pool.ImportJob.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	s.repo.SaveCPA(ctx, pool)
}

func (s *SourceService) fetchCPAToken(ctx context.Context, pool repository.CPA, name string) (string, error) {
	endpoint := strings.TrimSuffix(pool.BaseURL, "/") + "/v0/management/auth-files/download?" + url.Values{"name": {name}}.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+pool.SecretKey)
	response, err := s.proxy.Client("", false, false).Do(req)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return "", fmt.Errorf("HTTP %d", response.StatusCode)
	}
	var payload map[string]any
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return "", err
	}
	token, _ := payload["access_token"].(string)
	if token == "" {
		return "", errors.New("missing access_token")
	}
	return token, nil
}

func (s *SourceService) SubGroups(ctx context.Context, sub repository.Sub) ([]map[string]any, error) {
	return s.subList(ctx, sub, "/api/v1/admin/groups", url.Values{"page": {"1"}, "page_size": {strconv.Itoa(subListLimit)}})
}
func (s *SourceService) SubAccounts(ctx context.Context, sub repository.Sub, page int, size int, search string) ([]map[string]any, int, error) {
	headers, err := s.subHeaders(ctx, sub)
	if err != nil {
		return nil, 0, err
	}
	params := url.Values{"platform": {"openai"}, "type": {"oauth"}, "page": {strconv.Itoa(page)}, "page_size": {strconv.Itoa(size)}, "search": {search}}
	if sub.GroupID != "" {
		params.Set("group", sub.GroupID)
	}
	return s.subPage(ctx, headers, sub.BaseURL, "/api/v1/admin/accounts", params)
}

func (s *SourceService) ImportSub(ctx context.Context, sub repository.Sub, ids []string, all bool, search string) (repository.ImportJob, error) {
	total := len(ids)
	if all {
		_, count, err := s.SubAccounts(ctx, sub, 1, 1, search)
		if err != nil {
			return repository.ImportJob{}, err
		}
		total = count
	}
	if total == 0 {
		return repository.ImportJob{}, errors.New("account ids is required")
	}
	now := time.Now().UTC().Format(time.RFC3339)
	sub.ImportJob = repository.ImportJob{ID: id32(), Status: "pending", CreatedAt: now, UpdatedAt: now, Total: total, Errors: []map[string]any{}}
	if err := s.repo.SaveSub(ctx, sub); err != nil {
		return repository.ImportJob{}, err
	}
	go s.runSubImport(sub, ids, all, search)
	return sub.ImportJob, nil
}

// 按批读取令牌并写入号池；导入全部时逐页向对方服务取账号编号。
func (s *SourceService) runSubImport(sub repository.Sub, ids []string, all bool, search string) {
	ctx := context.Background()
	const batchSize = 100
	job := &sub.ImportJob
	job.Status = "running"
	s.repo.SaveSub(ctx, sub)
	tokenCount := 0
	for page := 1; ; page++ {
		var batch []string
		if all {
			items, _, err := s.SubAccounts(ctx, sub, page, batchSize, search)
			if err != nil {
				job.Errors = append(job.Errors, map[string]any{"name": fmt.Sprintf("第 %d 页", page), "error": err.Error()})
				break
			}
			for _, item := range items {
				batch = append(batch, stringValue(item["id"]))
			}
		} else if start := (page - 1) * batchSize; start < len(ids) {
			batch = ids[start:min(start+batchSize, len(ids))]
		}
		if len(batch) == 0 {
			break
		}
		tokens, importErrors, err := s.fetchSubTokens(ctx, sub, batch)
		if err != nil {
			for _, id := range batch {
				job.Errors = append(job.Errors, map[string]any{"name": id, "error": err.Error()})
			}
		} else {
			job.Errors = append(job.Errors, importErrors...)
		}
		if len(tokens) > 0 {
			accounts := make([]repository.Account, 0, len(tokens))
			for _, token := range tokens {
				accounts = append(accounts, repository.Account{AccessToken: token})
			}
			added, skipped, refreshed, _, _ := s.accounts.Add(ctx, accounts)
			job.Added, job.Skipped, job.Refreshed = job.Added+added, job.Skipped+skipped, job.Refreshed+refreshed
			tokenCount += len(tokens)
		}
		job.Completed += len(batch)
		job.Failed = len(job.Errors)
		job.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
		s.repo.SaveSub(ctx, sub)
	}
	job.Status = "completed"
	if tokenCount == 0 {
		job.Status = "failed"
	}
	job.Failed = len(job.Errors)
	job.UpdatedAt = time.Now().UTC().Format(time.RFC3339)
	s.repo.SaveSub(ctx, sub)
}

func (s *SourceService) fetchSubTokens(ctx context.Context, sub repository.Sub, ids []string) ([]string, []map[string]any, error) {
	headers, err := s.subHeaders(ctx, sub)
	if err != nil {
		return nil, nil, err
	}
	endpoint := strings.TrimSuffix(sub.BaseURL, "/") + "/api/v1/admin/accounts/data?" + url.Values{"ids": {strings.Join(ids, ",")}, "timezone": {"Asia/Shanghai"}}.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, nil, err
	}
	copyHeaders(req.Header, headers)
	response, err := s.proxy.Client("", false, false).Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, nil, fmt.Errorf("HTTP %d", response.StatusCode)
	}
	var payload map[string]any
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, nil, err
	}
	accounts, ok := exportedAccounts(payload)
	if !ok {
		return nil, nil, errors.New("invalid export payload")
	}
	tokens := []string{}
	importErrors := []map[string]any{}
	for _, item := range accounts {
		credentials, _ := item["credentials"].(map[string]any)
		if token := accessToken(credentials); token != "" {
			tokens = append(tokens, token)
			continue
		}
		name := stringValue(item["id"])
		if name == "" {
			name = stringValue(credentials["chatgpt_account_id"])
		}
		if name == "" {
			name = stringValue(item["name"])
		}
		if name == "" {
			name = "unknown"
		}
		importErrors = append(importErrors, map[string]any{"name": name, "error": "missing access_token"})
	}
	if len(accounts) < len(ids) {
		importErrors = append(importErrors, map[string]any{"name": strings.Join(ids, ","), "error": fmt.Sprintf("exported %d/%d accounts", len(accounts), len(ids))})
	}
	return tokens, importErrors, nil
}

func (s *SourceService) subList(ctx context.Context, sub repository.Sub, path string, params url.Values) ([]map[string]any, error) {
	headers, err := s.subHeaders(ctx, sub)
	if err != nil {
		return nil, err
	}
	var all []map[string]any
	for page := 1; ; page++ {
		params.Set("page", strconv.Itoa(page))
		items, total, err := s.subPage(ctx, headers, sub.BaseURL, path, params)
		if err != nil {
			return nil, err
		}
		all = append(all, items...)
		if len(all) >= total {
			return all, nil
		}
		if len(items) == 0 {
			return nil, fmt.Errorf("sub2api list returned %d/%d items", len(all), total)
		}
	}
}

func (s *SourceService) subPage(ctx context.Context, headers http.Header, baseURL string, path string, params url.Values) ([]map[string]any, int, error) {
	endpoint := strings.TrimSuffix(baseURL, "/") + path + "?" + params.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, 0, err
	}
	copyHeaders(req.Header, headers)
	response, err := s.proxy.Client("", false, false).Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(response.Body, 200))
		kind := "list"
		if strings.Contains(path, "/groups") {
			kind = "groups"
		}
		return nil, 0, fmt.Errorf("sub2api %s failed: HTTP %d %s", kind, response.StatusCode, body)
	}
	var payload map[string]any
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, 0, err
	}
	items, total := pagedItems(payload)
	return items, total, nil
}

func (s *SourceService) subHeaders(ctx context.Context, sub repository.Sub) (http.Header, error) {
	headers := http.Header{"Accept": {"application/json"}}
	if sub.APIKey != "" {
		headers.Set("x-api-key", sub.APIKey)
		return headers, nil
	}
	payload, _ := json.Marshal(map[string]string{"email": sub.Email, "password": sub.Password})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimSuffix(sub.BaseURL, "/")+"/api/v1/auth/login", strings.NewReader(string(payload)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	response, err := s.proxy.Client("", false, false).Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(response.Body, 200))
		return nil, fmt.Errorf("sub2api login failed: HTTP %d %s", response.StatusCode, body)
	}
	var body map[string]any
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		return nil, err
	}
	if data, ok := body["data"].(map[string]any); ok {
		body = data
	}
	token, _ := body["access_token"].(string)
	if token == "" {
		return nil, errors.New("sub2api login did not return access_token")
	}
	headers.Set("Authorization", "Bearer "+token)
	return headers, nil
}

func pagedItems(payload map[string]any) ([]map[string]any, int) {
	if data, ok := payload["data"].(map[string]any); ok {
		payload = data
	}
	for _, key := range []string{"items", "data", "list"} {
		if items, ok := mapItems(payload[key]); ok {
			total := anyInt(payload["total"])
			if total == 0 {
				total = len(items)
			}
			return items, total
		}
	}
	return []map[string]any{}, 0
}

func exportedAccounts(payload map[string]any) ([]map[string]any, bool) {
	if data, ok := payload["data"].(map[string]any); ok {
		payload = data
	}
	return mapItems(payload["accounts"])
}

func mapItems(value any) ([]map[string]any, bool) {
	raw, ok := value.([]any)
	if !ok {
		return nil, false
	}
	items := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if value, ok := item.(map[string]any); ok {
			items = append(items, value)
		}
	}
	return items, true
}

func accessToken(credentials map[string]any) string {
	for _, key := range []string{"access_token", "accessToken", "token"} {
		if token, ok := credentials[key].(string); ok && token != "" {
			return token
		}
	}
	return ""
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprint(value)
}
func copyHeaders(target http.Header, source http.Header) {
	for key, values := range source {
		for _, value := range values {
			target.Add(key, value)
		}
	}
}
func id32() string { return strings.ReplaceAll(uuid.NewString(), "-", "") }
func anyInt(value any) int {
	switch item := value.(type) {
	case float64:
		return int(item)
	case string:
		result, _ := strconv.Atoi(item)
		return result
	}
	return 0
}
