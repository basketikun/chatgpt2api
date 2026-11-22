package service

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/draw"
	"image/png"
	"math"
	"net/http"
	"slices"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/protocol"
	chatgpt "github.com/basketikun/chatgpt2api/internal/upstream"
	"github.com/disintegration/imaging"
)

type AIService struct {
	accounts *AccountService
	catalog  *CatalogService
	images   *ImageService
	logs     *LogService
	proxy    *ProxyService
	config   *config.Config
	cacheMu  sync.Mutex
	cache    map[string]cachedProtocol
}
type cachedProtocol struct {
	Value     json.RawMessage
	ExpiresAt time.Time
}

type ImageRequest struct {
	Prompt         string
	Model          string
	Count          int
	Size           string
	Quality        string
	ResponseFormat string
	BaseURL        string
	Stream         bool
	HistoryID      *int64
	TurnID         *int64
	Images         [][]byte
	ImageNames     []string
	ImageMIMEs     []string
	Masks          [][]byte
	MaskNames      []string
	MaskMIMEs      []string
}
type ImageResult struct {
	B64           string
	URL           string
	RevisedPrompt string
}
type ImageError struct {
	Err            error
	Status         int
	Type           string
	Code           string
	Param          any
	ConversationID string
	AccountEmail   string
}

func (e *ImageError) Error() string { return e.Err.Error() }

func NewAIService(accounts *AccountService, catalog *CatalogService, images *ImageService, logs *LogService, proxy *ProxyService, config *config.Config) *AIService {
	return &AIService{accounts: accounts, catalog: catalog, images: images, logs: logs, proxy: proxy, config: config, cache: map[string]cachedProtocol{}}
}

func (s *AIService) Text(ctx context.Context, modelName string, messages []map[string]any, effort string, search bool, delta func(string) error, callLog *CallLog) (string, error) {
	if modelName == "" {
		modelName = s.config.DefaultModel
	}
	callLog.Update(map[string]any{"model": modelName})
	backendModel := modelName
	if search {
		backendModel = s.config.DefaultModel
	}
	output := strings.Builder{}
	var err error
	accountTypes := map[string]bool(nil)
	if backendModel != "auto" {
		accountTypes, err = s.catalog.AccountTypesForModel(ctx, backendModel)
		if err != nil {
			return "", err
		}
	}
	if plans := callLog.identity.Plans; len(plans) > 0 {
		allowed := map[string]bool{}
		for _, plan := range plans {
			allowed[plan] = accountTypes == nil || accountTypes[plan]
		}
		accountTypes = allowed
	}
	attempted, conversationID, email := map[string]bool{}, "", ""
	for {
		token, tokenErr := s.accounts.TextTokenForModel(ctx, attempted, accountTypes, backendModel)
		if tokenErr != nil {
			err = tokenErr
			break
		}
		attempted[token] = true
		account, accountErr := s.accounts.Account(ctx, token)
		if accountErr != nil {
			err = accountErr
			break
		}
		email = ""
		if account.Email != nil {
			email = *account.Email
		}
		callLog.Update(map[string]any{"account_email": email})
		callLog.Add("已选择上游账号", map[string]any{"account_email": email})
		client := chatgpt.NewOpenAIBackendAPI(token, account.Proxy, s.proxy, s.config).WithAccountID(account.AccountID)
		emitted := false
		callLog.Add("开始准备上游请求", map[string]any{"model": backendModel, "thinking_effort": effort, "search": search})
		raw, clean := "", ""
		conversationID, err = client.StartConversation(ctx, messages, backendModel, effort, nil, search, func(value string) error {
			emitted = true
			if search {
				raw += value
				next := protocol.CleanSearchText(raw)
				if !strings.HasPrefix(next, clean) {
					return nil
				}
				value = strings.TrimPrefix(next, clean)
				clean = next
				if value == "" {
					return nil
				}
			}
			output.WriteString(value)
			if delta != nil {
				return delta(value)
			}
			return nil
		})
		if err == nil {
			s.accounts.MarkTextUsed(ctx, token)
			if s.config.Account.RemoveConversation && conversationID != "" {
				client.DeleteConversation(context.Background(), conversationID)
			}
			break
		}
		s.accounts.RecordTextError(ctx, token, err)
		callLog.Add("上游调用失败", map[string]any{"error": err.Error(), "response_started": emitted})
		if emitted || !invalidTokenError(err) {
			break
		}
		refreshed, refreshErr := s.accounts.RefreshToken(ctx, token, true)
		if refreshErr == nil && refreshed != "" && refreshed != token && !attempted[refreshed] {
			continue
		}
		s.accounts.RemoveInvalid(ctx, token)
	}
	if err == nil {
		callLog.Update(map[string]any{"conversation_id": conversationID})
		callLog.Add("上游 SSE 已完成", map[string]any{"conversation_id": conversationID, "output_chars": output.Len()})
	}
	if err != nil {
		callLog.Save("调用失败", "failed", map[string]any{"error": err.Error(), "account_email": email, "conversation_id": conversationID})
	} else {
		callLog.Save("调用完成", "success", map[string]any{"account_email": email, "conversation_id": conversationID})
	}
	return output.String(), err
}

func (s *AIService) PrepareMessages(messages []map[string]any) []map[string]any {
	if s.config.SystemPrompt != "" {
		messages = append([]map[string]any{{"role": "system", "content": s.config.SystemPrompt}}, messages...)
	}
	if !s.config.Cache.NormalizeMessages {
		return messages
	}
	result := make([]map[string]any, 0, len(messages))
	previous := ""
	for _, message := range messages {
		if s.config.Cache.DropAssistantHistory && message["role"] == "assistant" {
			continue
		}
		data, _ := json.Marshal(message)
		signature := string(data)
		if s.config.Cache.DropAdjacentDuplicates && signature == previous {
			continue
		}
		result = append(result, message)
		previous = signature
	}
	return result
}

// ProtocolCacheKey 按接口协议分区缓存：/v1/chat/completions 与 /v1/responses
// 归一化后的 messages 可能完全相同，key 里必须带协议，否则会互相命中对方的响应格式。
func (s *AIService) ProtocolCacheKey(protocol string, body map[string]any, messages []map[string]any, stream bool) string {
	keys := []string{"frequency_penalty", "max_completion_tokens", "max_tokens", "metadata", "model", "presence_penalty", "reasoning_effort", "response_format", "seed", "stop", "stream_options", "temperature", "thinking_effort", "tool_choice", "tools", "top_p", "user", "reasoning"}
	payload := map[string]any{"protocol": protocol, "messages": messages, "stream": stream}
	for _, key := range keys {
		if value, ok := body[key]; ok {
			payload[key] = value
		}
	}
	data, _ := json.Marshal(payload)
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func (s *AIService) CachedProtocol(key string, stream bool, target any) bool {
	if !s.config.Cache.Enabled || s.config.Cache.TTLSeconds <= 0 || stream && !s.config.Cache.StreamCache {
		return false
	}
	s.cacheMu.Lock()
	defer s.cacheMu.Unlock()
	item, ok := s.cache[key]
	if !ok || time.Now().After(item.ExpiresAt) {
		delete(s.cache, key)
		return false
	}
	return json.Unmarshal(item.Value, target) == nil
}

func (s *AIService) StoreProtocol(key string, stream bool, value any) {
	if !s.config.Cache.Enabled || s.config.Cache.TTLSeconds <= 0 || stream && !s.config.Cache.StreamCache {
		return
	}
	data, err := json.Marshal(value)
	if err != nil {
		return
	}
	s.cacheMu.Lock()
	defer s.cacheMu.Unlock()
	now := time.Now()
	for current, item := range s.cache {
		if now.After(item.ExpiresAt) {
			delete(s.cache, current)
		}
	}
	for len(s.cache) >= max(1, s.config.Cache.MaxEntries) {
		oldest := ""
		for current, item := range s.cache {
			if oldest == "" || item.ExpiresAt.Before(s.cache[oldest].ExpiresAt) {
				oldest = current
			}
		}
		delete(s.cache, oldest)
	}
	s.cache[key] = cachedProtocol{Value: data, ExpiresAt: now.Add(time.Duration(s.config.Cache.TTLSeconds) * time.Second)}
}

// generateImage 选一个账号生成一张图；retryable 表示换号重试可能成功（内容违规和没有可用额度不会重试）。
func (s *AIService) generateImage(ctx context.Context, request ImageRequest, callLog *CallLog, index int) (ImageResult, bool, error) {
	token, err := s.accounts.ImageToken(ctx, callLog.identity.Routes, callLog.identity.Plans)
	if err != nil {
		return ImageResult{}, false, newImageError(err)
	}
	success := false
	defer func() { s.accounts.ReleaseImageToken(context.Background(), token, success) }()
	account, _ := s.accounts.Account(ctx, token)
	codex := account.IsCodex && slices.Contains(callLog.identity.Routes, "codex")
	email := ""
	if account.Email != nil {
		email = *account.Email
	}
	callLog.Update(map[string]any{"account_email": email})
	callLog.Add("已选择上游账号", map[string]any{"account_email": email, "position": index})
	var data []byte
	conversationID := ""
	if codex {
		encoded := make([]string, 0, len(request.Images))
		for _, image := range request.Images {
			encoded = append(encoded, base64.StdEncoding.EncodeToString(image))
		}
		callLog.Add("请求 Codex 图片生成", map[string]any{"position": index})
		data, err = chatgpt.NewCodexAPI(token, chatgpt.CodexBaseURL, account.Proxy, s.proxy).WithAccountID(account.AccountID).StartImageGen(ctx, request.Prompt, s.config.Image.CodexModel, s.config.Image.CodexImageModel, encoded, defaultString(request.Size, "2048x2048"), defaultString(request.Quality, "auto"))
		if err == nil {
			callLog.Add("Codex 图片生成完成", map[string]any{"position": index})
		}
	} else {
		client := chatgpt.NewOpenAIBackendAPI(token, account.Proxy, s.proxy, s.config).WithAccountID(account.AccountID)
		callLog.Add("请求上游对话", map[string]any{"position": index, "model": s.config.DefaultModel})
		content := []any{map[string]any{"type": "text", "text": imagePrompt(request.Prompt, request.Size, request.Quality)}}
		for imageIndex, image := range request.Images {
			content = append(content, map[string]any{"type": "image", "data": image, "name": imageValue(request.ImageNames, imageIndex, "image.png"), "mime": imageValue(request.ImageMIMEs, imageIndex, "image/png")})
		}
		message := map[string]any{"role": "user", "content": content}
		if settings := imageGenerationSettings(request.Size); settings != nil {
			message["image_generation_settings"] = settings
		}
		policyText := strings.Builder{}
		conversationID, err = client.StartConversation(ctx, []map[string]any{message}, s.config.DefaultModel, "", []string{"picture_v2"}, false, func(value string) error {
			policyText.WriteString(value)
			return nil
		})
		if err == nil && policyText.Len() > 0 {
			// 生成图片后助手也会附带说明文字，只有会话里没有图片时才视为拒绝
			var ids []string
			if ids, err = client.ImageIDs(ctx, conversationID); err == nil && len(ids) == 0 {
				err = &ImageError{Err: errors.New(policyText.String()), Status: 400, Type: "invalid_request_error", Code: "content_policy_violation"}
			}
		}
		if err == nil {
			callLog.Update(map[string]any{"conversation_id": conversationID})
			callLog.Add("上游对话已结束", map[string]any{"conversation_id": conversationID, "position": index})
			callLog.Add("开始轮询上游图片", map[string]any{"conversation_id": conversationID, "position": index})
			var ids []string
			ids, err = client.PollImages(ctx, conversationID)
			if err == nil {
				callLog.Add("获取到上游图片", map[string]any{"conversation_id": conversationID, "image_ids": ids, "position": index})
				data, err = client.Download(ctx, conversationID, ids[0])
			}
		}
	}
	if err != nil {
		imageErr := newImageError(err)
		imageErr.ConversationID, imageErr.AccountEmail = conversationID, email
		return ImageResult{}, imageRetryable(imageErr), imageErr
	}
	stored, err := s.images.Save(ctx, data, request.BaseURL)
	if err != nil {
		imageErr := newImageError(err)
		imageErr.ConversationID, imageErr.AccountEmail = conversationID, email
		return ImageResult{}, true, imageErr
	}
	result := ImageResult{B64: base64.StdEncoding.EncodeToString(data), URL: stored.URL, RevisedPrompt: request.Prompt}
	callLog.Add("图片已保存", map[string]any{"position": index, "url": stored.URL})
	success = true
	return result, false, nil
}

func (s *AIService) Images(ctx context.Context, request ImageRequest, callLog *CallLog) ([]ImageResult, error) {
	if request.Model == "" || request.Model == "auto" {
		request.Model = s.config.ImageModelName
	}
	if !s.IsImageModel(request.Model) {
		err := newImageError(fmt.Errorf("unsupported image model, supported models: %s", s.config.ImageModelName))
		callLog.Save("调用失败", "failed", map[string]any{"error": err.Error()})
		return nil, err
	}
	if request.Count < 1 || request.Count > 4 {
		err := errors.New("n must be between 1 and 4")
		callLog.Save("调用失败", "failed", map[string]any{"error": err.Error()})
		return nil, err
	}
	if s.config.BaseURL != "" {
		request.BaseURL = s.config.BaseURL
	}
	request.Images = applyMasks(request.Images, request.Masks)
	results := make([]ImageResult, request.Count)
	errs := make(chan error, request.Count)
	var wait sync.WaitGroup
	for index := range request.Count {
		wait.Add(1)
		go func(index int) {
			defer wait.Done()
			for attempt := 0; ; attempt++ {
				result, retryable, err := s.generateImage(ctx, request, callLog, index)
				if err == nil {
					results[index] = result
					return
				}
				if !retryable || attempt >= s.config.Image.AccountRetries || ctx.Err() != nil {
					errs <- err
					return
				}
				callLog.Add("更换账号重试", map[string]any{"position": index, "attempt": attempt + 1, "error": err.Error()})
			}
		}(index)
	}
	wait.Wait()
	close(errs)
	if err := <-errs; err != nil {
		detail := map[string]any{"error": err.Error()}
		var imageErr *ImageError
		if errors.As(err, &imageErr) {
			detail["account_email"], detail["conversation_id"] = imageErr.AccountEmail, imageErr.ConversationID
		}
		callLog.Save("调用失败", "failed", detail)
		return nil, err
	}
	urls := make([]string, 0, len(results))
	for _, result := range results {
		urls = append(urls, result.URL)
	}
	callLog.Save("调用完成", "success", map[string]any{"urls": urls})
	return results, nil
}

func (s *AIService) IsImageModel(model string) bool { return model == s.config.ImageModelName }

func newImageError(err error) *ImageError {
	var imageErr *ImageError
	if errors.As(err, &imageErr) {
		return imageErr
	}
	// 上游 prepare 接口对会话准备参数返回 400/422 时与账号无关，换号重试没有意义。
	var upstreamErr *chatgpt.UpstreamHTTPError
	if errors.As(err, &upstreamErr) && upstreamErr.Context == "/backend-api/f/conversation/prepare" && (upstreamErr.StatusCode == http.StatusBadRequest || upstreamErr.StatusCode == http.StatusUnprocessableEntity) {
		return &ImageError{Err: err, Status: http.StatusUnprocessableEntity, Type: "invalid_request_error", Code: "upstream_prepare_rejected"}
	}
	message := strings.ToLower(err.Error())
	if strings.Contains(message, "图片额度") || strings.Contains(message, "no available") && strings.Contains(message, "image quota") {
		return &ImageError{Err: errors.New("no available image quota"), Status: 429, Type: "insufficient_quota", Code: "insufficient_quota"}
	}
	if strings.Contains(message, "content policy") || strings.Contains(message, "content_policy") || strings.Contains(message, "safety policy") {
		return &ImageError{Err: err, Status: 400, Type: "invalid_request_error", Code: "content_policy_violation"}
	}
	return &ImageError{Err: err, Status: 502, Type: "server_error", Code: "upstream_error"}
}

// imageRetryable 判断换账号重试是否有意义：内容违规和上游准备参数被拒绝都与账号无关。
func imageRetryable(err *ImageError) bool {
	return err.Code != "content_policy_violation" && err.Code != "upstream_prepare_rejected"
}

func imageValue(values []string, index int, fallback string) string {
	if index < len(values) && values[index] != "" {
		return values[index]
	}
	return fallback
}

func applyMasks(images [][]byte, masks [][]byte) [][]byte {
	if len(masks) == 0 {
		return images
	}
	result := make([][]byte, 0, len(images))
	for index, data := range images {
		source, err := imaging.Decode(bytes.NewReader(data))
		if err != nil {
			result = append(result, data)
			continue
		}
		maskData := masks[min(index, len(masks)-1)]
		mask, err := imaging.Decode(bytes.NewReader(maskData))
		if err != nil {
			result = append(result, data)
			continue
		}
		bounds := source.Bounds()
		resized := imaging.Resize(mask, bounds.Dx(), bounds.Dy(), imaging.Lanczos)
		alpha := image.NewAlpha(bounds)
		for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
			for x := bounds.Min.X; x < bounds.Max.X; x++ {
				alpha.SetAlpha(x, y, color.Alpha{A: color.GrayModel.Convert(resized.At(x, y)).(color.Gray).Y})
			}
		}
		output := image.NewNRGBA(bounds)
		draw.DrawMask(output, bounds, source, bounds.Min, alpha, bounds.Min, draw.Src)
		buffer := bytes.NewBuffer(nil)
		if png.Encode(buffer, output) == nil {
			result = append(result, buffer.Bytes())
		} else {
			result = append(result, data)
		}
	}
	return result
}

// imagePrompt 现在只把质量提示写进正文；尺寸改由 message.metadata.image_generation_settings
// 的 aspect_ratio 表达，避免把 "2048x2048" 这类客户端参数直接塞给模型。
func imagePrompt(prompt string, size string, quality string) string {
	hints := []string{}
	if quality != "" && quality != "auto" {
		hints = append(hints, "输出图片质量为 "+quality+"。")
	}
	if len(hints) == 0 {
		return prompt
	}
	return prompt + "\n\n" + strings.Join(hints, "")
}

// imageGenerationSettings 把尺寸换算成网页端支持的宽高比枚举。
func imageGenerationSettings(size string) map[string]any {
	parts := strings.Split(strings.ToLower(strings.TrimSpace(size)), "x")
	if len(parts) != 2 {
		return nil
	}
	width, widthErr := strconv.Atoi(strings.TrimSpace(parts[0]))
	height, heightErr := strconv.Atoi(strings.TrimSpace(parts[1]))
	if widthErr != nil || heightErr != nil || width <= 0 || height <= 0 {
		return nil
	}
	ratio := float64(width) / float64(height)
	options := []struct {
		label string
		value float64
	}{{"1:1", 1}, {"4:3", 4.0 / 3}, {"3:4", 3.0 / 4}, {"16:9", 16.0 / 9}, {"9:16", 9.0 / 16}}
	best, bestDiff := "", math.MaxFloat64
	for _, option := range options {
		diff := math.Abs(math.Log(ratio / option.value))
		if diff < bestDiff {
			best, bestDiff = option.label, diff
		}
	}
	return map[string]any{"aspect_ratio": best, "image_count": 1}
}
func defaultString(value string, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}
func NewID(prefix string) string {
	return prefix + strings.ReplaceAll(fmt.Sprint(time.Now().UnixNano()), "-", "")
}
