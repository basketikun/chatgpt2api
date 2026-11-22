package upstream

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
	http "github.com/bogdanfinn/fhttp"
	tls_client "github.com/bogdanfinn/tls-client"
	"github.com/google/uuid"
)

const chatGPTBaseURL = "https://chatgpt.com"
const upstreamUserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
const defaultDataBuild = "5750d92c02e7d1b6aa2ea1ffdb1c1fb376272952"
const defaultBuildNumber = ""
const upstreamRetryBudgetSeconds = 15.0
const upstreamRetryMaxDelaySeconds = 10.0
const upstreamRetryBaseDelay = 700 * time.Millisecond

var scriptSources = []string{"https://chatgpt.com/backend-api/sentinel/sdk.js"}
var bootstrapCompleted bool
var bootstrapAt time.Time
var bootstrapBuild = defaultBuildNumber
var bootstrapVersion = defaultDataBuild
var bootstrapMu sync.Mutex

type OpenAIBackendOptions struct {
	DefaultUpstreamModelName string
	DefaultThinkingEffort    string
	ImagePollTimeoutSeconds  float64
	ImagePollIntervalSeconds float64
	ImagePollInitialWait     float64
}

type OpenAIBackendAPI struct {
	baseURL      string
	accessToken  string
	accountID    string
	sentinel     string
	proof        string
	turnstile    string
	accountProxy string
	proxy        ClientProvider
	options      OpenAIBackendOptions
	deviceID     string
	sessionID    string
	build        string
	version      string
}

type ClientProvider interface {
	TLSClient(accountProxy string, resource bool, timeoutSeconds ...int) (tls_client.HttpClient, error)
	UpstreamClearance(ctx context.Context, targetURL string) (string, map[string]string)
}

func NewOpenAIBackendAPI(token string, accountProxy string, proxy ClientProvider, cfg *config.Config) *OpenAIBackendAPI {
	options := OpenAIBackendOptions{DefaultUpstreamModelName: cfg.DefaultModel, DefaultThinkingEffort: cfg.ThinkingEffort, ImagePollTimeoutSeconds: float64(cfg.Image.PollTimeoutSeconds), ImagePollIntervalSeconds: cfg.Image.PollIntervalSeconds, ImagePollInitialWait: cfg.Image.PollInitialWaitSeconds}
	return &OpenAIBackendAPI{baseURL: chatGPTBaseURL, accessToken: token, accountProxy: accountProxy, proxy: proxy, options: options, deviceID: uuid.NewString(), sessionID: uuid.NewString(), build: defaultBuildNumber, version: defaultDataBuild}
}

// WithAccountID 设置 ChatGPT-Account-ID；网页端在账号有 account id 时会带上该头。
func (u *OpenAIBackendAPI) WithAccountID(accountID string) *OpenAIBackendAPI {
	u.accountID = accountID
	return u
}

func (u *OpenAIBackendAPI) ListModels(ctx context.Context) ([]map[string]any, error) {
	if err := u.bootstrap(ctx); err != nil {
		return nil, err
	}
	response, err := u.request(ctx, http.MethodGet, "/backend-api/models?history_and_training_disabled=false", nil, nil)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	var payload struct {
		Models []map[string]any `json:"models"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return nil, err
	}
	return payload.Models, nil
}

func (u *OpenAIBackendAPI) Me(ctx context.Context) (string, error) {
	response, err := u.request(ctx, http.MethodGet, "/backend-api/me", nil, nil)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	var result struct {
		Email string `json:"email"`
	}
	err = json.NewDecoder(response.Body).Decode(&result)
	return result.Email, err
}

func (u *OpenAIBackendAPI) QuotaInfo(ctx context.Context) (int, string, error) {
	payload := map[string]any{"gizmo_id": nil, "requested_default_model": nil, "conversation_id": nil, "conversation_origin": nil, "system_hints": nil, "timezone": "Asia/Shanghai", "timezone_offset_min": -480}
	response, err := u.request(ctx, http.MethodPost, "/backend-api/conversation/init", payload, nil)
	if err != nil {
		return 0, "", err
	}
	defer response.Body.Close()
	var result struct {
		Limits []struct {
			Feature    string `json:"feature_name"`
			Remaining  int    `json:"remaining"`
			ResetAfter string `json:"reset_after"`
		} `json:"limits_progress"`
	}
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return 0, "", err
	}
	for _, limit := range result.Limits {
		if limit.Feature == "image_gen" {
			return limit.Remaining, limit.ResetAfter, nil
		}
	}
	return 0, "", nil
}

func (u *OpenAIBackendAPI) StartConversation(ctx context.Context, messages []map[string]any, model string, effort string, hints []string, search bool, delta func(string) error, createdCallbacks ...func(string) error) (string, error) {
	var created func(string) error
	if len(createdCallbacks) > 0 {
		created = createdCallbacks[0]
	}
	requireText := true
	for _, hint := range hints {
		if hint == "picture_v2" {
			requireText = false
		}
	}
	return u.startConversation(ctx, messages, model, effort, hints, search, requireText, delta, created)
}

// startConversation posts a new turn. Pass requireText=false for flows that only
// need the conversation id — the model may complete the turn without streaming
// plain assistant text, for example when it reports file paths instead.
func (u *OpenAIBackendAPI) startConversation(ctx context.Context, messages []map[string]any, model string, effort string, hints []string, search bool, requireText bool, delta func(string) error, created func(string) error) (string, error) {
	conversationID, _, err := u.startConversationWithMessage(ctx, messages, model, effort, hints, search, requireText, delta, created)
	return conversationID, err
}

// startConversationWithMessage also returns the assistant message id, letting
// callers address that message without fetching the conversation again.
func (u *OpenAIBackendAPI) startConversationWithMessage(ctx context.Context, messages []map[string]any, model string, effort string, hints []string, search bool, requireText bool, delta func(string) error, created func(string) error) (string, string, error) {
	if err := u.bootstrap(ctx); err != nil {
		return "", "", err
	}
	if err := u.chatRequirements(ctx); err != nil {
		return "", "", err
	}
	converted := make([]map[string]any, 0, len(messages))
	for _, message := range messages {
		item, err := u.convertMessage(ctx, message)
		if err != nil {
			return "", "", err
		}
		converted = append(converted, item)
	}
	traceID := uuid.NewString()
	if search && !containsString(hints, "search") {
		hints = append(hints, "search")
	}
	payload := u.conversationPayload(converted, model, effort, hints, search)
	applySystemHints(converted, hints)
	mimeTypes, uploadIDs := conversationAttachments(converted)
	conduit, err := u.prepareConversation(ctx, model, hints, mimeTypes, uploadIDs, traceID)
	if err != nil {
		return "", "", err
	}
	headers := map[string]string{"Accept": "text/event-stream", "X-OAI-Turn-Trace-Id": traceID, "X-OAI-MCP-Form-Version": "2"}
	if conduit != "" {
		headers["X-Conduit-Token"] = conduit
	}
	response, err := u.request(ctx, http.MethodPost, "/backend-api/f/conversation", payload, headers)
	if err != nil {
		return "", "", err
	}
	defer response.Body.Close()
	return readConversationSSEWithMessage(response.Body, delta, requireText, created)
}

// prepareConversation 在发起对话前换取 conduit token。
// 真实网页端的 prepare 是精简载荷：不带 messages / partial_query，只带本轮
// 模型、父消息、system_hints、附件元数据与准备状态；生图模型返回空值时不带该头。
func (u *OpenAIBackendAPI) prepareConversation(ctx context.Context, model string, hints []string, mimeTypes []string, uploadIDs []string, traceID string) (string, error) {
	body := preparePayload(model, hints, mimeTypes, uploadIDs)
	response, err := u.requestRetry(ctx, http.MethodPost, "/backend-api/f/conversation/prepare", body, map[string]string{"X-OAI-Turn-Trace-Id": traceID, "X-OAI-MCP-Form-Version": "2"})
	if err != nil {
		return "", err
	}
	defer response.Body.Close()
	var result struct {
		ConduitToken *string `json:"conduit_token"`
	}
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return "", err
	}
	if result.ConduitToken == nil {
		return "", nil
	}
	return *result.ConduitToken, nil
}

// prepareMaxUploadIDs 是 prepare 接口能接受的 upload ID 上限。3 个及以上会返回
// 422 Invalid conversation body（#426）；该字段只是预检提示，正式会话消息里
// 仍然携带全部附件，因此超过上限时整体省略。
const prepareMaxUploadIDs = 2

func preparePayload(model string, hints []string, mimeTypes []string, uploadIDs []string) map[string]any {
	body := map[string]any{"client_prepare_state": "sent", "action": "next", "model": model, "parent_message_id": "client-created-root", "timezone": "Asia/Shanghai", "timezone_offset_min": -480, "is_do_not_remember": false, "local_function_names": []string{"local.continue_in_work"}, "client_prepare_dispatch": "debounced", "client_prepare_source": "composer_editor_state"}
	if len(hints) > 0 {
		body["system_hints"] = hints
	}
	if len(mimeTypes) > 0 {
		body["attachment_mime_types"] = mimeTypes
	}
	if len(uploadIDs) > 0 && len(uploadIDs) <= prepareMaxUploadIDs {
		body["prepare_image_upload_ids"] = uploadIDs
	}
	return body
}

// conversationAttachments 汇总本轮消息里的附件 MIME 与上传 ID，供 prepare 使用。
func conversationAttachments(messages []map[string]any) ([]string, []string) {
	mimeSet, idSet := map[string]bool{}, map[string]bool{}
	mimeTypes, uploadIDs := []string{}, []string{}
	add := func(list any) {
		items := []map[string]any{}
		switch value := list.(type) {
		case []map[string]any:
			items = value
		case []any:
			for _, raw := range value {
				if item, ok := raw.(map[string]any); ok {
					items = append(items, item)
				}
			}
		}
		for _, item := range items {
			if value, ok := item["mime_type"].(string); ok && value != "" && !mimeSet[value] {
				mimeSet[value] = true
				mimeTypes = append(mimeTypes, value)
			}
			if value, ok := item["id"].(string); ok && value != "" && !idSet[value] {
				idSet[value] = true
				uploadIDs = append(uploadIDs, value)
			}
		}
	}
	for _, message := range messages {
		metadata, _ := message["metadata"].(map[string]any)
		add(metadata["attachments"])
	}
	sort.Strings(mimeTypes)
	return mimeTypes, uploadIDs
}

// Conversation 读取会话详情。网页端主路径是复数接口并返回 messages；
// 若该接口不可用再回退到 bundle 里的单数接口（返回 mapping 节点树）。
func (u *OpenAIBackendAPI) Conversation(ctx context.Context, id string) (map[string]any, error) {
	response, err := u.requestRetry(ctx, http.MethodGet, "/backend-api/conversations/"+id+"?num_turns=10&include_has_versions=true", nil, nil)
	if err != nil {
		response, err = u.requestRetry(ctx, http.MethodGet, "/backend-api/conversation/"+id+"?include_model_switcher_metadata=false", nil, nil)
	}
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	var result map[string]any
	err = json.NewDecoder(response.Body).Decode(&result)
	return result, err
}

// DeleteConversation 调用网页端删除会话接口。
func (u *OpenAIBackendAPI) DeleteConversation(ctx context.Context, id string) error {
	response, err := u.request(ctx, http.MethodDelete, "/backend-api/conversation/id/"+id, nil, nil)
	if err == nil {
		response.Body.Close()
	}
	return err
}

func (u *OpenAIBackendAPI) PollImages(ctx context.Context, conversationID string) ([]string, error) {
	time.Sleep(time.Duration(u.options.ImagePollInitialWait * float64(time.Second)))
	return u.PollImagesFor(ctx, conversationID, time.Duration(u.options.ImagePollTimeoutSeconds)*time.Second)
}
func (u *OpenAIBackendAPI) PollImagesFor(ctx context.Context, conversationID string, timeout time.Duration) ([]string, error) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		ids, err := u.ImageIDs(ctx, conversationID)
		if err != nil {
			return nil, err
		}
		if len(ids) > 0 {
			return ids, nil
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(time.Duration(u.options.ImagePollIntervalSeconds * float64(time.Second))):
		}
	}
	return nil, errors.New("ChatGPT 生图超时")
}

// ImageIDs 读取会话一次，返回其中已生成的图片 ID。
func (u *OpenAIBackendAPI) ImageIDs(ctx context.Context, conversationID string) ([]string, error) {
	detail, err := u.Conversation(ctx, conversationID)
	return generatedImageIDs(detail), err
}

func (u *OpenAIBackendAPI) Upload(ctx context.Context, data []byte, width int, height int, contentType string, filenames ...string) (map[string]any, error) {
	filename := "image.png"
	if len(filenames) > 0 {
		filename = filenames[0]
	}
	payload := map[string]any{"file_name": filename, "file_size": len(data), "use_case": "multimodal", "width": width, "height": height}
	response, err := u.request(ctx, http.MethodPost, "/backend-api/files", payload, nil)
	if err != nil {
		return nil, err
	}
	var metadata map[string]any
	if err := json.NewDecoder(response.Body).Decode(&metadata); err != nil {
		response.Body.Close()
		return nil, err
	}
	response.Body.Close()
	uploadURL, _ := metadata["upload_url"].(string)
	fileID, _ := metadata["file_id"].(string)
	if uploadURL == "" || fileID == "" {
		return nil, errors.New("upstream file upload metadata is incomplete")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, uploadURL, bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", contentType)
	req.Header.Set("x-ms-blob-type", "BlockBlob")
	req.Header.Set("x-ms-version", "2020-04-08")
	req.Header.Set("Origin", u.baseURL)
	req.Header.Set("Referer", u.baseURL+"/")
	req.Header.Set("User-Agent", upstreamUserAgent)
	client, err := u.proxy.TLSClient(u.accountProxy, true)
	if err != nil {
		return nil, err
	}
	uploadResponse, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	if uploadResponse.StatusCode < 200 || uploadResponse.StatusCode >= 300 {
		return nil, responseError("image upload", uploadResponse)
	}
	uploadResponse.Body.Close()
	response, err = u.request(ctx, http.MethodPost, "/backend-api/files/"+fileID+"/uploaded", map[string]any{}, nil)
	if err != nil {
		return nil, err
	}
	response.Body.Close()
	metadata["file_size"], metadata["mime_type"], metadata["width"], metadata["height"] = len(data), contentType, width, height
	return metadata, nil
}

func (u *OpenAIBackendAPI) Download(ctx context.Context, conversationID string, fileID string) ([]byte, error) {
	path := "/backend-api/files/download/" + fileID + "?download_intent=false&inline=true"
	if conversationID != "" {
		path += "&conversation_id=" + conversationID
	}
	response, err := u.requestRetry(ctx, http.MethodGet, path, nil, nil)
	if err != nil {
		return nil, err
	}
	var metadata map[string]any
	if err := json.NewDecoder(response.Body).Decode(&metadata); err != nil {
		response.Body.Close()
		return nil, err
	}
	response.Body.Close()
	downloadURL, _ := metadata["download_url"].(string)
	if downloadURL == "" {
		return nil, errors.New("upstream file download URL is missing")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, downloadURL, nil)
	if err != nil {
		return nil, err
	}
	if req.URL.Scheme+"://"+req.URL.Host == u.baseURL {
		req.Header.Set("Authorization", "Bearer "+u.accessToken)
	}
	req.Header.Set("Referer", u.baseURL+"/library")
	client, err := u.proxy.TLSClient(u.accountProxy, true)
	if err != nil {
		return nil, err
	}
	response, err = client.Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, responseError("image download", response)
	}
	return io.ReadAll(response.Body)
}

func (u *OpenAIBackendAPI) GenerateImage(ctx context.Context, prompt string, model string, images [][]byte) ([]byte, string, error) {
	content := []any{map[string]any{"type": "text", "text": prompt}}
	for _, data := range images {
		content = append(content, map[string]any{"type": "image", "data": data, "mime": "image/png"})
	}
	conversationID, err := u.StartConversation(ctx, []map[string]any{{"role": "user", "content": content}}, model, "", []string{"picture_v2"}, false, func(string) error { return nil })
	if err != nil {
		return nil, "", err
	}
	ids, err := u.PollImages(ctx, conversationID)
	if err != nil {
		return nil, conversationID, err
	}
	data, err := u.Download(ctx, conversationID, ids[0])
	return data, conversationID, err
}

func (u *OpenAIBackendAPI) chatRequirements(ctx context.Context) error {
	pow := POW{}
	pToken := pow.BuildPToken(upstreamUserAgent, scriptSources, u.version)
	response, err := u.requestRetry(ctx, http.MethodPost, "/backend-api/sentinel/chat-requirements/prepare", map[string]string{"p": pToken}, nil)
	if err != nil {
		return err
	}
	var prepare map[string]any
	if err := json.NewDecoder(response.Body).Decode(&prepare); err != nil {
		response.Body.Close()
		return err
	}
	response.Body.Close()
	proof, turnstile := "", ""
	if value, ok := prepare["proofofwork"].(map[string]any); ok && value["required"] == true {
		proof, err = pow.BuildProofToken(fmt.Sprint(value["seed"]), fmt.Sprint(value["difficulty"]), upstreamUserAgent, scriptSources, u.version)
		if err != nil {
			return err
		}
	}
	if value, ok := prepare["turnstile"].(map[string]any); ok && value["required"] == true {
		turnstile = (Turnstile{}).Solve(fmt.Sprint(value["dx"]), pToken)
	}
	response, err = u.requestRetry(ctx, http.MethodPost, "/backend-api/sentinel/chat-requirements/finalize", map[string]any{"prepare_token": prepare["prepare_token"], "proof_token": proof, "turnstile_token": turnstile}, nil)
	if err != nil {
		return err
	}
	var result map[string]any
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		response.Body.Close()
		return err
	}
	response.Body.Close()
	token, _ := result["token"].(string)
	if token == "" {
		return fmt.Errorf("missing chat requirements token: %v", result)
	}
	u.sentinel, u.proof, u.turnstile = token, proof, turnstile
	return nil
}

func (u *OpenAIBackendAPI) bootstrap(ctx context.Context) error {
	bootstrapMu.Lock()
	defer bootstrapMu.Unlock()
	if bootstrapCompleted && time.Since(bootstrapAt) < 6*time.Hour {
		u.build, u.version = bootstrapBuild, bootstrapVersion
		return nil
	}
	response, err := u.requestRetry(ctx, http.MethodGet, "/", nil, map[string]string{"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8", "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "none", "Sec-Fetch-User": "?1", "Upgrade-Insecure-Requests": "1"})
	if err != nil {
		return err
	}
	defer response.Body.Close()
	parser := ScriptSrcParser{}
	if err := parser.Parse(response.Body); err != nil {
		return err
	}
	if parser.DataBuild != "" {
		bootstrapVersion = parser.DataBuild
	}
	if parser.BuildNumber != "" {
		bootstrapBuild = parser.BuildNumber
	}
	u.build, u.version = bootstrapBuild, bootstrapVersion
	bootstrapAt = time.Now()
	bootstrapCompleted = true
	return nil
}

// conversationPayload 构造真实网页端 /backend-api/f/conversation 的提交载荷。
// 以 2026-11 浏览器抓包为准：保留 turn_attribution / genui_state_snapshots /
// client_prepare_state，正常对话不带 conversation_mode 与空 system_hints。
func (u *OpenAIBackendAPI) conversationPayload(messages []map[string]any, model string, effort string, hints []string, search bool) map[string]any {
	if search && !containsString(hints, "search") {
		hints = append(hints, "search")
	}
	payload := map[string]any{"turn_attribution": map[string]string{"turn_trigger": "composer"}, "action": "next", "messages": messages, "model": model, "parent_message_id": "client-created-root", "timezone": "Asia/Shanghai", "timezone_offset_min": -480, "is_do_not_remember": false, "client_contextual_info": map[string]any{"app_name": "chatgpt.com", "app_surface": "codex_browser", "has_web_push_capabilities": true, "web_push_notification_permission": "default"}, "local_function_names": []string{"local.continue_in_work"}, "supported_encodings": []string{"v1"}, "genui_state_snapshots": []any{}, "client_prepare_state": "success"}
	if len(hints) > 0 {
		payload["system_hints"] = hints
	}
	value := ConvertThinkingEffort(effort)
	if value == "" {
		value = ConvertThinkingEffort(u.options.DefaultThinkingEffort)
	}
	if value != "" {
		payload["thinking_effort"] = value
	}
	if search {
		payload["force_use_search"] = true
		payload["client_reported_search_source"] = "conversation_composer_web_icon"
	}
	return payload
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

// applySystemHints 把本轮 system hints 同时写到用户消息 metadata，
// 与网页端生图请求保持一致。
func applySystemHints(messages []map[string]any, hints []string) {
	if len(hints) == 0 || len(messages) == 0 {
		return
	}
	metadata, _ := messages[len(messages)-1]["metadata"].(map[string]any)
	if metadata == nil {
		return
	}
	metadata["system_hints"] = hints
}

func (u *OpenAIBackendAPI) request(ctx context.Context, method string, path string, payload any, extra map[string]string) (*http.Response, error) {
	var body io.Reader
	contentType := ""
	if payload != nil {
		data, _ := json.Marshal(payload)
		body = bytes.NewReader(data)
		contentType = "application/json"
	}
	return u.requestBody(ctx, method, path, body, contentType, extra)
}

// requestBody sends a request with a raw body, which is what multipart uploads
// (speech transcription) need.
func (u *OpenAIBackendAPI) requestBody(ctx context.Context, method string, path string, body io.Reader, contentType string, extra map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, method, u.baseURL+path, body)
	if err != nil {
		return nil, err
	}
	u.applyHeaders(req, path, true)
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	for key, value := range extra {
		req.Header.Set(key, value)
	}
	if userAgent, cookies := u.proxy.UpstreamClearance(ctx, u.baseURL); len(cookies) > 0 {
		if userAgent != "" {
			req.Header.Set("User-Agent", userAgent)
		}
		for name, value := range cookies {
			req.AddCookie(&http.Cookie{Name: name, Value: value})
		}
	}
	client, err := u.proxy.TLSClient(u.accountProxy, false)
	if err != nil {
		return nil, err
	}
	response, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		if response.StatusCode == http.StatusUnauthorized {
			response.Body.Close()
			return nil, ErrTokenInvalidated
		}
		return nil, responseError(path, response)
	}
	return response, nil
}

// applyHeaders sets the browser-shaped headers the ChatGPT backend expects.
// Targets outside /backend-api (for example signed content URLs) still need the
// bearer token, so the caller only tunes the target path headers.
func (u *OpenAIBackendAPI) applyHeaders(req *http.Request, path string, targetPath bool) {
	req.Header.Set("Authorization", "Bearer "+u.accessToken)
	req.Header.Set("User-Agent", upstreamUserAgent)
	req.Header.Set("Origin", u.baseURL)
	req.Header.Set("Referer", u.baseURL+"/")
	req.Header.Set("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7")
	req.Header.Set("Cache-Control", "no-cache")
	req.Header.Set("Pragma", "no-cache")
	req.Header.Set("Priority", "u=1, i")
	req.Header.Set("Sec-Ch-Ua", `"Not-A.Brand";v="99", "Google Chrome";v="157", "Chromium";v="157"`)
	req.Header.Set("Sec-Ch-Ua-Arch", `"x86"`)
	req.Header.Set("Sec-Ch-Ua-Bitness", `"64"`)
	req.Header.Set("Sec-Ch-Ua-Full-Version", `"157.0.8103.51"`)
	req.Header.Set("Sec-Ch-Ua-Full-Version-List", `"Not-A.Brand";v="99.0.0.0", "Google Chrome";v="157.0.8103.51", "Chromium";v="157.0.8103.51"`)
	req.Header.Set("Sec-Ch-Ua-Mobile", "?0")
	req.Header.Set("Sec-Ch-Ua-Model", `""`)
	req.Header.Set("Sec-Ch-Ua-Platform", `"Windows"`)
	req.Header.Set("Sec-Ch-Ua-Platform-Version", `"19.0.0"`)
	req.Header.Set("OAI-Device-Id", u.deviceID)
	req.Header.Set("OAI-DID", u.deviceID)
	req.Header.Set("OAI-Session-Id", u.sessionID)
	req.Header.Set("OAI-Language", "zh-CN")
	req.Header.Set("Originator", "Codex Browser")
	req.Header.Set("X-OpenAI-Web-Frontend", "codex_webview")
	req.Header.Set("X-OpenAI-Codex-Window-Type", "browser")
	req.Header.Set("X-OpenAI-Rate-Limit-Join-Workspace", "1")
	req.Header.Set("X-OpenAI-Rejoin-Pro-CTA", "1")
	if u.accountID != "" {
		req.Header.Set("ChatGPT-Account-ID", u.accountID)
	}
	if u.build != "" {
		req.Header.Set("OAI-Client-Build-Number", u.build)
	}
	if u.version != "" {
		req.Header.Set("OAI-Client-Version", u.version)
	}
	req.Header.Set("X-OAI-MCP-Form-Version", "2")
	req.Header.Set("Sec-Fetch-Dest", "empty")
	req.Header.Set("Sec-Fetch-Mode", "cors")
	req.Header.Set("Sec-Fetch-Site", "same-origin")
	if targetPath {
		req.Header.Set("X-OpenAI-Target-Path", strings.Split(path, "?")[0])
		req.Header.Set("X-OpenAI-Target-Route", strings.Split(path, "?")[0])
	}
	if u.sentinel != "" {
		req.Header.Set("OpenAI-Sentinel-Chat-Requirements-Token", u.sentinel)
	}
	if u.proof != "" {
		req.Header.Set("OpenAI-Sentinel-Proof-Token", u.proof)
	}
	if u.turnstile != "" {
		req.Header.Set("OpenAI-Sentinel-Turnstile-Token", u.turnstile)
	}
}

// requestRetry wraps request with retries for transient connection failures.
// Only safe for idempotent calls (GET/PATCH and read-only POSTs) — never use it
// for /backend-api/f/conversation, where a retry could duplicate a turn.
func (u *OpenAIBackendAPI) requestRetry(ctx context.Context, method string, path string, payload any, extra map[string]string) (*http.Response, error) {
	return u.requestRetryBudget(ctx, method, path, payload, extra, time.Duration(upstreamRetryBudgetSeconds*float64(time.Second)))
}

// requestRetryBudget retries transient connection failures until the wall clock
// budget runs out. The upstream link drops in bursts that can outlast a fixed
// attempt count, so long running jobs budget by time instead.
func (u *OpenAIBackendAPI) requestRetryBudget(ctx context.Context, method string, path string, payload any, extra map[string]string, budget time.Duration) (*http.Response, error) {
	var response *http.Response
	err := retryTransient(ctx, budget, func() error {
		current, err := u.request(ctx, method, path, payload, extra)
		if err != nil {
			return err
		}
		response = current
		return nil
	})
	if err != nil {
		return nil, err
	}
	return response, nil
}

// conversationMessages 返回会话详情中按时间排序的消息。
// 新会话详情可能只返回 mapping（节点树），messages 为空；优先沿 current_node
// 回溯出当前分支，回溯失败时再退回按 create_time 排序的全量节点。
func conversationMessages(detail map[string]any) []map[string]any {
	items, _ := detail["messages"].([]any)
	result := make([]map[string]any, 0, len(items))
	for _, item := range items {
		if message, ok := item.(map[string]any); ok {
			result = append(result, message)
		}
	}
	if len(result) > 0 {
		return result
	}
	mapping, _ := detail["mapping"].(map[string]any)
	current, _ := detail["current_node"].(string)
	branch := make([]map[string]any, 0, len(mapping))
	seen := map[string]bool{}
	for nodeID := current; nodeID != "" && !seen[nodeID]; {
		seen[nodeID] = true
		node, _ := mapping[nodeID].(map[string]any)
		if node == nil {
			break
		}
		if message, ok := node["message"].(map[string]any); ok {
			branch = append(branch, message)
		}
		nodeID, _ = node["parent"].(string)
	}
	for index, total := 0, len(branch); index < total/2; index++ {
		branch[index], branch[total-1-index] = branch[total-1-index], branch[index]
	}
	if len(branch) > 0 {
		return branch
	}
	for _, raw := range mapping {
		node, _ := raw.(map[string]any)
		if message, ok := node["message"].(map[string]any); ok {
			result = append(result, message)
		}
	}
	sort.SliceStable(result, func(i, j int) bool {
		return messageCreateTime(result[i]) < messageCreateTime(result[j])
	})
	return result
}

func messageCreateTime(message map[string]any) float64 {
	switch value := message["create_time"].(type) {
	case float64:
		return value
	case int64:
		return float64(value)
	case json.Number:
		parsed, _ := value.Float64()
		return parsed
	default:
		return 0
	}
}

func generatedImageIDs(detail map[string]any) []string {
	result := []string{}
	seen := map[string]bool{}
	for _, message := range conversationMessages(detail) {
		author, _ := message["author"].(map[string]any)
		metadata, _ := message["metadata"].(map[string]any)
		name, _ := author["name"].(string)
		if author["role"] != "tool" && metadata["image_gen_async"] != true && !strings.HasPrefix(name, "t2uay3k") && name != "image_gen" {
			continue
		}
		content, _ := message["content"].(map[string]any)
		parts, _ := content["parts"].([]any)
		for _, rawPart := range parts {
			part, _ := rawPart.(map[string]any)
			partMetadata, _ := part["metadata"].(map[string]any)
			if part["content_type"] != "image_asset_pointer" {
				continue
			}
			if partMetadata["generation"] == nil || partMetadata["generation"] == false {
				continue
			}
			pointer, _ := part["asset_pointer"].(string)
			fileID := strings.TrimPrefix(strings.TrimPrefix(pointer, "sediment://"), "file-service://")
			if fileID == "" || seen[fileID] {
				continue
			}
			seen[fileID] = true
			result = append(result, fileID)
		}
	}
	return result
}
