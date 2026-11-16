package protocol

import (
	"encoding/json"
	"fmt"
	"strings"
)

func MessagesFromInput(input any, instructions any) []map[string]any {
	var result []map[string]any
	if text := contentText(instructions); text != "" {
		result = append(result, map[string]any{"role": "system", "content": text})
	}
	switch value := input.(type) {
	case string:
		result = append(result, map[string]any{"role": "user", "content": value})
	case []any:
		if responseParts(value) {
			return append(result, map[string]any{"role": "user", "content": value})
		}
		for _, raw := range value {
			item, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			if item["type"] == "function_call_output" {
				result = append(result, map[string]any{"role": "user", "content": "Tool result " + fmt.Sprint(item["call_id"]) + ": " + fmt.Sprint(item["output"])})
				continue
			}
			role, _ := item["role"].(string)
			if role == "" {
				role = "user"
			}
			content := item["content"]
			if content == nil {
				content = []any{item}
			}
			result = append(result, map[string]any{"role": role, "content": content})
		}
	case map[string]any:
		role, _ := value["role"].(string)
		if role == "" {
			role = "user"
		}
		content := value["content"]
		if content == nil {
			content = []any{value}
		}
		result = append(result, map[string]any{"role": role, "content": content})
	}
	return result
}

func SearchRequested(tools any) bool {
	items, _ := tools.([]any)
	for _, raw := range items {
		item, _ := raw.(map[string]any)
		kind, _ := item["type"].(string)
		if strings.Contains(kind, "web_search") {
			return true
		}
	}
	return false
}

func WebSearchRequested(body map[string]any) bool {
	if ResponseSearchRequested(body) {
		return true
	}
	if _, ok := body["web_search_options"].(map[string]any); ok {
		return true
	}
	model, _ := body["model"].(string)
	for _, prefix := range []string{"gpt-4o-search-preview", "gpt-4o-mini-search-preview", "gpt-5-search-api"} {
		if model == prefix || strings.HasPrefix(model, prefix+"-") {
			return true
		}
	}
	return false
}

func ResponseSearchRequested(body map[string]any) bool {
	return SearchRequested(body["tools"]) || SearchRequested([]any{body["tool_choice"]})
}

func HasUnsupportedTools(tools any, allowed map[string]bool) bool {
	items, _ := tools.([]any)
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if ok && !allowed[fmt.Sprint(item["type"])] {
			return true
		}
	}
	return false
}

func SearchQuery(messages []map[string]any) string {
	for index := len(messages) - 1; index >= 0; index-- {
		if messages[index]["role"] == "user" {
			return contentText(messages[index]["content"])
		}
	}
	return ""
}

func AnthropicMessages(messages any, system any) []map[string]any {
	result := MessagesFromInput(messages, system)
	for _, message := range result {
		parts, ok := message["content"].([]any)
		if !ok {
			continue
		}
		converted := make([]any, 0, len(parts))
		for _, raw := range parts {
			block, ok := raw.(map[string]any)
			if !ok {
				converted = append(converted, raw)
				continue
			}
			switch block["type"] {
			case "tool_use":
				input, _ := json.Marshal(block["input"])
				converted = append(converted, map[string]any{"type": "text", "text": "<tool_calls><tool_call><tool_name>" + fmt.Sprint(block["name"]) + "</tool_name><parameters>" + string(input) + "</parameters></tool_call></tool_calls>"})
			case "tool_result":
				converted = append(converted, map[string]any{"type": "text", "text": "Tool result " + fmt.Sprint(block["tool_use_id"]) + ": " + fmt.Sprint(block["content"])})
			default:
				converted = append(converted, block)
			}
		}
		message["content"] = converted
	}
	return result
}
func responseParts(items []any) bool {
	if len(items) == 0 {
		return false
	}
	for _, raw := range items {
		item, ok := raw.(map[string]any)
		if !ok {
			return false
		}
		kind, _ := item["type"].(string)
		if kind != "input_text" && kind != "input_image" && kind != "image_url" && kind != "image" {
			return false
		}
	}
	return true
}
func contentText(value any) string {
	switch item := value.(type) {
	case string:
		return item
	case []any:
		result := strings.Builder{}
		for _, raw := range item {
			if part, ok := raw.(map[string]any); ok {
				if text, ok := part["text"].(string); ok {
					result.WriteString(text)
				}
			}
		}
		return result.String()
	}
	return ""
}
