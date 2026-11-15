package upstream

import (
	"bufio"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"strings"

	http "github.com/bogdanfinn/fhttp"
	"github.com/google/uuid"
)

const CodexBaseURL = "https://chatgpt.com/backend-api/codex/responses"

// Codex CLI 的当前客户端版本，/backend-api/codex/models 用它做能力协商。
const CodexClientVersion = "0.171.0"
const codexUserAgent = "codex_cli_rs/" + CodexClientVersion + " (Windows 11; x86_64)"

type CodexAPI struct {
	token        string
	accountID    string
	baseurl      string
	accountProxy string
	proxy        ClientProvider
}

func NewCodexAPI(token string, baseurl string, accountProxy string, proxy ClientProvider) *CodexAPI {
	if baseurl == "" {
		baseurl = CodexBaseURL
	}
	return &CodexAPI{token: token, baseurl: baseurl, accountProxy: accountProxy, proxy: proxy}
}

// WithAccountID 设置 ChatGPT-Account-ID，Codex 接口在多账号场景下需要它。
func (c *CodexAPI) WithAccountID(accountID string) *CodexAPI {
	c.accountID = accountID
	return c
}

func (c *CodexAPI) Headers() map[string]string {
	headers := map[string]string{"Authorization": "Bearer " + c.token, "Content-Type": "application/json", "OpenAI-Beta": "responses=experimental", "originator": "codex_cli_rs", "session_id": uuid.NewString(), "User-Agent": codexUserAgent, "Accept": "text/event-stream"}
	if c.accountID != "" {
		headers["ChatGPT-Account-ID"] = c.accountID
	}
	return headers
}

func (c *CodexAPI) ImageInput(prompt string, images []string) []map[string]any {
	content := []map[string]any{{"type": "input_text", "text": prompt}}
	for _, image := range images {
		if !strings.HasPrefix(image, "data:image/") {
			image = "data:image/png;base64," + image
		}
		content = append(content, map[string]any{"type": "input_image", "image_url": image})
	}
	return []map[string]any{{"role": "user", "content": content}}
}

func (c *CodexAPI) StartImageGen(ctx context.Context, prompt string, model string, imageModel string, images []string, size string, quality string) ([]byte, error) {
	payload := map[string]any{"model": model, "instructions": "Use the image_generation tool to create exactly one image for the user's request. Return the generated image result.", "store": false, "input": c.ImageInput(prompt, images), "tools": []map[string]any{{"type": "image_generation", "model": imageModel, "action": map[bool]string{true: "edit", false: "generate"}[len(images) > 0], "size": size, "quality": quality, "output_format": "png"}}, "tool_choice": map[string]string{"type": "image_generation"}, "parallel_tool_calls": false, "stream": true}
	data, _ := json.Marshal(payload)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseurl, bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	for key, value := range c.Headers() {
		request.Header.Set(key, value)
	}
	client, err := c.proxy.TLSClient(c.accountProxy, false, 1200)
	if err != nil {
		return nil, err
	}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, responseError("/backend-api/codex/responses", response)
	}
	return c.ReadImage(response.Body)
}

// ReadImage 读取 Codex Responses 流里的图片结果。
// 新版本把结果放在 response.output_item.done 的 image_generation_call 里，
// 也可能在 response.completed 的 output 数组里返回。
func (c *CodexAPI) ReadImage(reader io.Reader) ([]byte, error) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 64*1024), 64*1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		raw := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if raw == "" || raw == "[DONE]" {
			continue
		}
		var event map[string]any
		if json.Unmarshal([]byte(raw), &event) != nil {
			continue
		}
		if message, ok := event["error"].(map[string]any); ok {
			return nil, errors.New("Codex 图片生成失败: " + messageString(message))
		}
		eventType, _ := event["type"].(string)
		if strings.Contains(eventType, "error") {
			return nil, errors.New("Codex 图片生成失败: " + messageString(event))
		}
		switch eventType {
		case "response.output_item.done":
			item, _ := event["item"].(map[string]any)
			if data, ok := decodeCodexImageItem(item); ok {
				return data, nil
			}
		case "response.completed":
			response, _ := event["response"].(map[string]any)
			output, _ := response["output"].([]any)
			for _, raw := range output {
				item, _ := raw.(map[string]any)
				if data, ok := decodeCodexImageItem(item); ok {
					return data, nil
				}
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	return nil, errors.New("No image result found in response")
}

func decodeCodexImageItem(item map[string]any) ([]byte, bool) {
	if item == nil {
		return nil, false
	}
	kind, _ := item["type"].(string)
	if kind != "image_generation_call" && kind != "image_generation" {
		return nil, false
	}
	result, _ := item["result"].(string)
	if result == "" {
		return nil, false
	}
	data, err := base64.StdEncoding.DecodeString(result)
	if err != nil || len(data) == 0 {
		return nil, false
	}
	return data, true
}

func messageString(value map[string]any) string {
	for _, key := range []string{"message", "detail", "code"} {
		if text, ok := value[key].(string); ok && text != "" {
			return text
		}
	}
	data, _ := json.Marshal(value)
	return string(data)
}
