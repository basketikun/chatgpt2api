package protocol

import (
	"reflect"
	"testing"
)

func TestMessagesFromInput(t *testing.T) {
	input := []any{map[string]any{"role": "user", "content": "hello"}, map[string]any{"type": "function_call_output", "call_id": "call_1", "output": "sunny"}}
	want := []map[string]any{{"role": "system", "content": "answer briefly"}, {"role": "user", "content": "hello"}, {"role": "user", "content": "Tool result call_1: sunny"}}
	if got := MessagesFromInput(input, "answer briefly"); !reflect.DeepEqual(got, want) {
		t.Fatalf("got %#v", got)
	}
}

func TestSearchRequested(t *testing.T) {
	if !SearchRequested([]any{map[string]any{"type": "web_search_preview"}}) {
		t.Fatal("search not detected")
	}
}
