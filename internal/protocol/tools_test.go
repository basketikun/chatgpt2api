package protocol

import (
	"reflect"
	"strings"
	"testing"
)

func TestWithToolPromptSupportsOpenAIAndAnthropicTools(t *testing.T) {
	tools := []any{
		map[string]any{"type": "function", "function": map[string]any{"name": "get_weather", "description": "query weather", "parameters": map[string]any{"type": "object"}}},
		map[string]any{"type": "function", "name": "search", "description": "search web", "parameters": map[string]any{"type": "object"}},
		map[string]any{"name": "add", "description": "add numbers", "input_schema": map[string]any{"type": "object"}},
	}
	messages := WithToolPrompt([]map[string]any{{"role": "user", "content": "run tools"}}, tools, map[string]any{"type": "any"})
	prompt, _ := messages[0]["content"].(string)
	for _, value := range []string{"Tool: get_weather", "Description: query weather", "Tool: search", "Description: search web", "Tool: add", "Description: add numbers", "Parameters: {\"type\":\"object\"}", "You must call one or more provided tools."} {
		if !strings.Contains(prompt, value) {
			t.Fatalf("prompt missing %q", value)
		}
	}
}

func TestParseToolCalls(t *testing.T) {
	text := `answer<tool_calls><tool_call><tool_name>get_weather</tool_name><parameters><city>上海</city></parameters></tool_call><tool_call><tool_name>add</tool_name><parameters>{"left":1,"right":1}</parameters></tool_call></tool_calls>`
	calls := ParseToolCalls(text)
	want := []ToolCall{{Name: "get_weather", Arguments: map[string]any{"city": "上海"}}, {Name: "add", Arguments: map[string]any{"left": float64(1), "right": float64(1)}}}
	if !reflect.DeepEqual(calls, want) {
		t.Fatalf("got %#v", calls)
	}
	if VisibleToolText(text) != "answer" {
		t.Fatalf("got %q", VisibleToolText(text))
	}
}
