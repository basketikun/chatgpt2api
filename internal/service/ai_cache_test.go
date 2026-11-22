package service

import "testing"

// /v1/chat/completions 与 /v1/responses 归一化后的 messages 可能完全一致，
// 缓存 key 必须带协议，否则会命中对方格式的缓存（#427）。
func TestProtocolCacheKeySeparatesProtocols(t *testing.T) {
	var ai AIService
	messages := []map[string]any{{"role": "user", "content": "hello"}}
	body := map[string]any{"model": "auto"}
	chat := ai.ProtocolCacheKey("chat.completions", body, messages, false)
	responses := ai.ProtocolCacheKey("responses", body, messages, false)
	if chat == responses {
		t.Fatal("chat.completions and responses share a cache key")
	}
	if chat != ai.ProtocolCacheKey("chat.completions", body, messages, false) {
		t.Fatal("cache key is not stable")
	}
	if chat == ai.ProtocolCacheKey("chat.completions", body, messages, true) {
		t.Fatal("stream and non-stream share a cache key")
	}
	if chat == ai.ProtocolCacheKey("chat.completions", map[string]any{"model": "other"}, messages, false) {
		t.Fatal("different models share a cache key")
	}
}
