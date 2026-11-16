package handler

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"strings"
	"testing"
)

type integrationAPI struct {
	baseURL string
	auth    string
	client  *http.Client
}

func TestOpenAIHTTPIntegration(t *testing.T) {
	api := newIntegrationAPI(t)
	t.Run("models", func(t *testing.T) {
		payload := decodeResponse(t, api.request(t, http.MethodGet, "/v1/models", nil, nil))
		models, _ := payload["data"].([]any)
		if payload["object"] != "list" || len(models) == 0 {
			t.Fatalf("invalid models: %#v", payload)
		}
		for _, raw := range models {
			item, _ := raw.(map[string]any)
			if item["id"] == "" || item["object"] != "model" || item["root"] != item["id"] || item["permission"] == nil {
				t.Fatalf("invalid model: %#v", item)
			}
		}
	})

	for _, stream := range []bool{false, true} {
		t.Run("chat", func(t *testing.T) {
			response := api.json(t, "/v1/chat/completions", map[string]any{
				"model": "auto", "stream": stream, "stream_options": map[string]any{"include_usage": true},
				"messages": []any{map[string]any{"role": "user", "content": "请简单介绍一下你自己。"}},
			})
			if !stream {
				payload := decodeResponse(t, response)
				if choices, _ := payload["choices"].([]any); len(choices) == 0 {
					t.Fatal("missing choices")
				}
				return
			}
			events := sseEvents(t, response)
			usageEvents := []map[string]any{}
			for _, event := range events {
				choices, ok := event["choices"].([]any)
				if ok && len(choices) == 0 && event["usage"] != nil {
					usageEvents = append(usageEvents, event)
				}
			}
			if len(usageEvents) != 1 {
				t.Fatalf("invalid usage events: %#v", events)
			}
			usage := usageEvents[0]["usage"].(map[string]any)
			if usage["total_tokens"] != usage["prompt_tokens"].(float64)+usage["completion_tokens"].(float64) {
				t.Fatalf("invalid usage: %#v", usage)
			}
		})

		t.Run("messages", func(t *testing.T) {
			response := api.request(t, http.MethodPost, "/v1/messages", jsonBody(t, map[string]any{
				"model": "auto", "stream": stream,
				"messages": []any{map[string]any{"role": "user", "content": "你好，请简单介绍一下你自己。"}},
			}), map[string]string{"Content-Type": "application/json", "x-api-key": api.auth, "anthropic-version": "2023-06-01"})
			if stream {
				events := sseEvents(t, response)
				if !hasEvent(events, "message_start") || !hasEvent(events, "message_delta") {
					t.Fatalf("missing message usage events: %#v", events)
				}
				return
			}
			payload := decodeResponse(t, response)
			if payload["type"] != "message" {
				t.Fatalf("invalid message: %#v", payload)
			}
		})

		t.Run("responses", func(t *testing.T) {
			response := api.json(t, "/v1/responses", map[string]any{
				"model": "auto", "stream": stream,
				"input": []any{map[string]any{"role": "user", "content": []any{map[string]any{"type": "input_text", "text": "你好，请简单介绍一下你自己。"}}}},
			})
			if stream {
				events := sseEvents(t, response)
				if !hasEvent(events, "response.created") || !hasEvent(events, "response.completed") {
					t.Fatalf("missing response events: %#v", events)
				}
				return
			}
			payload := decodeResponse(t, response)
			if payload["status"] != "completed" {
				t.Fatalf("invalid response: %#v", payload)
			}
		})
	}
}

func TestImageHTTPIntegration(t *testing.T) {
	api := newIntegrationAPI(t)
	for _, stream := range []bool{false, true} {
		t.Run("generation", func(t *testing.T) {
			response := api.json(t, "/v1/images/generations", map[string]any{
				"model": "gpt-image-2.6", "prompt": "我想做一张南京城市宣传海报图。", "n": 1,
				"response_format": "b64_json", "stream": stream,
			})
			if stream {
				assertImageEvents(t, sseEvents(t, response))
				return
			}
			assertImages(t, decodeResponse(t, response)["data"])
		})
	}

	t.Run("url", func(t *testing.T) {
		payload := decodeResponse(t, api.json(t, "/v1/images/generations", map[string]any{
			"model": "gpt-image-2.6", "prompt": "一只橘猫坐在窗边，午后阳光，写实摄影", "n": 1, "response_format": "url",
		}))
		data, _ := payload["data"].([]any)
		if len(data) == 0 || data[0].(map[string]any)["url"] == "" {
			t.Fatalf("missing image URL: %#v", payload)
		}
	})

	t.Run("edit", func(t *testing.T) {
		image, err := base64.StdEncoding.DecodeString("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
		if err != nil {
			t.Fatal(err)
		}
		body := bytes.NewBuffer(nil)
		writer := multipart.NewWriter(body)
		writer.WriteField("model", "gpt-image-2.6")
		writer.WriteField("prompt", "把图片改成海报")
		writer.WriteField("response_format", "b64_json")
		part, err := writer.CreateFormFile("image", "image.png")
		if err != nil {
			t.Fatal(err)
		}
		if _, err := part.Write(image); err != nil {
			t.Fatal(err)
		}
		if err := writer.Close(); err != nil {
			t.Fatal(err)
		}
		response := api.request(t, http.MethodPost, "/v1/images/edits", body, map[string]string{"Content-Type": writer.FormDataContentType()})
		assertImages(t, decodeResponse(t, response)["data"])
	})

	for _, model := range []string{"gpt-image-2.6"} {
		for _, stream := range []bool{false, true} {
			t.Run("responses image", func(t *testing.T) {
				response := api.json(t, "/v1/responses", map[string]any{
					"model": model, "stream": stream,
					"input": []any{map[string]any{"role": "user", "content": []any{map[string]any{"type": "input_text", "text": "生成一张南京城市宣传海报图。"}}}},
					"tools": []any{map[string]any{"type": "image_generation"}},
				})
				if stream {
					assertResponseImages(t, sseEvents(t, response))
					return
				}
				assertResponseImages(t, []map[string]any{decodeResponse(t, response)})
			})
		}
	}
}

func TestToolCallHTTPIntegration(t *testing.T) {
	api := newIntegrationAPI(t)
	parameters := map[string]any{"type": "object", "properties": map[string]any{"city": map[string]any{"type": "string"}}, "required": []string{"city"}}
	add := map[string]any{"type": "object", "properties": map[string]any{"left": map[string]any{"type": "number"}, "right": map[string]any{"type": "number"}}, "required": []string{"left", "right"}}
	prompt := "查询上海现在的天气，并计算 1+1。必须分别调用 get_weather 和 add 两个工具，不要直接回答。"

	t.Run("chat completions", func(t *testing.T) {
		payload := decodeResponse(t, api.json(t, "/v1/chat/completions", map[string]any{
			"model": "auto", "messages": []any{map[string]any{"role": "user", "content": prompt}},
			"tools": []any{
				map[string]any{"type": "function", "function": map[string]any{"name": "get_weather", "parameters": parameters}},
				map[string]any{"type": "function", "function": map[string]any{"name": "add", "parameters": add}},
			},
			"tool_choice": "required",
		}))
		choice := payload["choices"].([]any)[0].(map[string]any)
		if choice["finish_reason"] != "tool_calls" {
			t.Fatalf("invalid tool response: %#v", payload)
		}
		assertToolNames(t, choice["message"].(map[string]any)["tool_calls"], "function")
	})

	t.Run("responses", func(t *testing.T) {
		payload := decodeResponse(t, api.json(t, "/v1/responses", map[string]any{
			"model": "auto", "input": prompt,
			"tools": []any{
				map[string]any{"type": "function", "name": "get_weather", "parameters": parameters},
				map[string]any{"type": "function", "name": "add", "parameters": add},
			},
			"tool_choice": "required",
		}))
		assertToolNames(t, payload["output"], "response")
	})

	t.Run("anthropic", func(t *testing.T) {
		response := api.request(t, http.MethodPost, "/v1/messages", jsonBody(t, map[string]any{
			"model": "auto", "max_tokens": 1024,
			"messages": []any{map[string]any{"role": "user", "content": prompt}},
			"tools": []any{
				map[string]any{"name": "get_weather", "input_schema": parameters},
				map[string]any{"name": "add", "input_schema": add},
			},
			"tool_choice": map[string]any{"type": "any"},
		}), map[string]string{"Content-Type": "application/json", "x-api-key": api.auth, "anthropic-version": "2023-06-01"})
		payload := decodeResponse(t, response)
		if payload["stop_reason"] != "tool_use" {
			t.Fatalf("invalid tool response: %#v", payload)
		}
		assertToolNames(t, payload["content"], "anthropic")
	})
}

func newIntegrationAPI(t *testing.T) integrationAPI {
	t.Helper()
	auth := os.Getenv("TEST_API_KEY")
	if auth == "" {
		t.Skip("set TEST_API_KEY to run local HTTP integration tests")
	}
	baseURL := os.Getenv("TEST_BASE_URL")
	if baseURL == "" {
		baseURL = "http://127.0.0.1:3000"
	}
	return integrationAPI{baseURL: strings.TrimSuffix(baseURL, "/"), auth: auth, client: &http.Client{}}
}

func (a integrationAPI) json(t *testing.T, path string, body any) *http.Response {
	return a.request(t, http.MethodPost, path, jsonBody(t, body), map[string]string{"Content-Type": "application/json"})
}

func (a integrationAPI) request(t *testing.T, method string, path string, body io.Reader, headers map[string]string) *http.Response {
	t.Helper()
	request, err := http.NewRequest(method, a.baseURL+path, body)
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Authorization", "Bearer "+a.auth)
	for name, value := range headers {
		request.Header.Set(name, value)
	}
	response, err := a.client.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK {
		data, _ := io.ReadAll(response.Body)
		response.Body.Close()
		t.Fatalf("HTTP %d: %s", response.StatusCode, data)
	}
	return response
}

func jsonBody(t *testing.T, value any) io.Reader {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	return bytes.NewReader(data)
}

func decodeResponse(t *testing.T, response *http.Response) map[string]any {
	t.Helper()
	defer response.Body.Close()
	var payload map[string]any
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		t.Fatal(err)
	}
	return payload
}

func sseEvents(t *testing.T, response *http.Response) []map[string]any {
	t.Helper()
	defer response.Body.Close()
	result := []map[string]any{}
	scanner := bufio.NewScanner(response.Body)
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		value := strings.TrimSpace(strings.TrimPrefix(line, "data:"))
		if value == "[DONE]" {
			break
		}
		var event map[string]any
		if json.Unmarshal([]byte(value), &event) == nil {
			result = append(result, event)
		}
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	return result
}

func hasEvent(events []map[string]any, kind string) bool {
	for _, event := range events {
		if event["type"] == kind {
			return true
		}
	}
	return false
}

func assertImages(t *testing.T, value any) {
	t.Helper()
	items, _ := value.([]any)
	if len(items) == 0 {
		t.Fatal("missing images")
	}
	item, _ := items[0].(map[string]any)
	encoded, _ := item["b64_json"].(string)
	if data, err := base64.StdEncoding.DecodeString(encoded); err != nil || len(data) == 0 {
		t.Fatalf("invalid image: %#v", item)
	}
}

func assertImageEvents(t *testing.T, events []map[string]any) {
	t.Helper()
	for _, event := range events {
		if event["data"] != nil {
			assertImages(t, event["data"])
			return
		}
	}
	t.Fatal("missing image event")
}

func assertResponseImages(t *testing.T, events []map[string]any) {
	t.Helper()
	for _, event := range events {
		if response, ok := event["response"].(map[string]any); ok {
			event = response
		}
		output, _ := event["output"].([]any)
		for _, raw := range output {
			item, _ := raw.(map[string]any)
			result, _ := item["result"].(string)
			if data, err := base64.StdEncoding.DecodeString(result); err == nil && len(data) > 0 {
				return
			}
		}
		if item, ok := event["item"].(map[string]any); ok {
			if result, _ := item["result"].(string); result != "" {
				return
			}
		}
	}
	t.Fatal("missing response image")
}

func assertToolNames(t *testing.T, value any, format string) {
	t.Helper()
	items, _ := value.([]any)
	calls := map[string]map[string]any{}
	for _, raw := range items {
		item, _ := raw.(map[string]any)
		switch format {
		case "function":
			function, _ := item["function"].(map[string]any)
			arguments := map[string]any{}
			json.Unmarshal([]byte(function["arguments"].(string)), &arguments)
			calls[function["name"].(string)] = arguments
		case "response":
			if item["type"] == "function_call" {
				arguments := map[string]any{}
				json.Unmarshal([]byte(item["arguments"].(string)), &arguments)
				calls[item["name"].(string)] = arguments
			}
		case "anthropic":
			if item["type"] == "tool_use" {
				calls[item["name"].(string)], _ = item["input"].(map[string]any)
			}
		}
	}
	if calls["get_weather"]["city"] != "上海" || calls["add"]["left"] != float64(1) || calls["add"]["right"] != float64(1) {
		t.Fatalf("invalid tool calls: %#v", calls)
	}
}
