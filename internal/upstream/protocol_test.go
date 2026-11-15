package upstream

import (
	"context"
	"encoding/json"
	"testing"
)

func TestConvertThinkingEffort(t *testing.T) {
	cases := map[string]string{"auto": "", "default": "", "": "", "standard": "standard", "low": "low", "medium": "medium", "minimal": "minimal", "extended": "extended", "high": "high", "xhigh": "xhigh", "max": "max", "ultra": "ultra", "none": "none", "extra-high": "xhigh", " HIGH ": "high"}
	for input, expected := range cases {
		if actual := ConvertThinkingEffort(input); actual != expected {
			t.Fatalf("ConvertThinkingEffort(%q) = %q, want %q", input, actual, expected)
		}
	}
}

func TestConversationPayloadUsesCurrentFields(t *testing.T) {
	api := &OpenAIBackendAPI{options: OpenAIBackendOptions{DefaultThinkingEffort: "extended"}}
	payload := api.conversationPayload([]map[string]any{{"role": "user", "content": "hi"}}, "auto", "", []string{"picture_v2"}, true)
	for _, stale := range []string{"conversation_mode", "supports_buffering", "force_parallel_switch", "paragen_cot_summary_display_override", "enable_message_followups"} {
		if _, ok := payload[stale]; ok {
			t.Fatalf("payload still contains non-current field %q", stale)
		}
	}
	for _, key := range []string{"turn_attribution", "action", "messages", "model", "parent_message_id", "client_prepare_state", "supported_encodings", "genui_state_snapshots", "client_contextual_info", "timezone", "timezone_offset_min"} {
		if _, ok := payload[key]; !ok {
			t.Fatalf("payload missing field %q", key)
		}
	}
	if payload["thinking_effort"] != "extended" {
		t.Fatalf("thinking_effort = %v", payload["thinking_effort"])
	}
	if payload["force_use_search"] != true {
		t.Fatal("search flag missing")
	}
	hints, _ := payload["system_hints"].([]string)
	if !containsString(hints, "search") || !containsString(hints, "picture_v2") {
		t.Fatalf("unexpected hints: %v", hints)
	}
	contextual, _ := payload["client_contextual_info"].(map[string]any)
	if contextual["app_name"] != "chatgpt.com" || contextual["app_surface"] != "codex_browser" {
		t.Fatalf("unexpected contextual info: %v", contextual)
	}
	turnAttribution, _ := payload["turn_attribution"].(map[string]string)
	if turnAttribution["turn_trigger"] != "composer" {
		t.Fatalf("unexpected turn attribution: %v", turnAttribution)
	}
	if snapshots, ok := payload["genui_state_snapshots"].([]any); !ok || len(snapshots) != 0 {
		t.Fatalf("unexpected genui snapshots: %v", payload["genui_state_snapshots"])
	}
}

func TestConversationPayloadOmitsEmptyHints(t *testing.T) {
	api := &OpenAIBackendAPI{}
	payload := api.conversationPayload([]map[string]any{{"role": "user", "content": "hi"}}, "auto", "", nil, false)
	if _, ok := payload["system_hints"]; ok {
		t.Fatal("system_hints should be omitted for a normal chat")
	}
	if _, ok := payload["thinking_effort"]; ok {
		t.Fatal("thinking_effort should be omitted when auto")
	}
}

func TestConvertMessageCurrentShape(t *testing.T) {
	api := &OpenAIBackendAPI{}
	message, err := api.convertMessage(context.Background(), map[string]any{"role": "user", "content": "hello", "image_generation_settings": map[string]any{"aspect_ratio": "16:9"}})
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"channel", "recipient", "status", "end_turn", "weight"} {
		if _, ok := message[key]; !ok {
			t.Fatalf("message missing field %q", key)
		}
	}
	metadata, _ := message["metadata"].(map[string]any)
	settings, _ := metadata["image_generation_settings"].(map[string]any)
	if settings["aspect_ratio"] != "16:9" {
		t.Fatalf("image settings missing: %v", metadata)
	}
	author, _ := message["author"].(map[string]any)
	if author["role"] != "user" {
		t.Fatalf("author = %v", author)
	}
	if _, ok := author["metadata"]; !ok {
		t.Fatal("author metadata missing")
	}
}

func TestGeneratedImageIDsFromMapping(t *testing.T) {
	detail := map[string]any{"current_node": "node-2", "mapping": map[string]any{
		"node-root": map[string]any{"id": "node-root", "parent": nil, "message": nil},
		"node-1": map[string]any{"id": "node-1", "parent": "node-root", "message": map[string]any{
			"author":      map[string]any{"role": "tool", "name": "t2uay3k.sj1i4kz"},
			"create_time": float64(2),
			"content": map[string]any{"content_type": "multimodal_text", "parts": []any{
				map[string]any{"content_type": "image_asset_pointer", "asset_pointer": "sediment://file_abc", "metadata": map[string]any{"generation": map[string]any{"gen_id": "g1"}}},
			}},
		}},
		"node-2": map[string]any{"id": "node-2", "parent": "node-1", "message": map[string]any{
			"author":      map[string]any{"role": "tool", "name": "image_gen"},
			"create_time": float64(3),
			"content": map[string]any{"content_type": "multimodal_text", "parts": []any{
				map[string]any{"content_type": "image_asset_pointer", "asset_pointer": "file-service://file_def", "metadata": map[string]any{"generation": map[string]any{"gen_id": "g2"}}},
			}},
		}},
	}}
	ids := generatedImageIDs(detail)
	if len(ids) != 2 || ids[0] != "file_abc" || ids[1] != "file_def" {
		t.Fatalf("unexpected ids: %v", ids)
	}
}

func TestConversationRequestShapeMatchesCapture(t *testing.T) {
	api := &OpenAIBackendAPI{}
	message, err := api.convertMessage(context.Background(), map[string]any{"role": "user", "content": "只回复两个字：收到"})
	if err != nil {
		t.Fatal(err)
	}
	payload := api.conversationPayload([]map[string]any{message}, "auto", "", nil, false)
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	var body map[string]any
	if err := json.Unmarshal(data, &body); err != nil {
		t.Fatal(err)
	}
	assertKeys(t, body, "turn_attribution", "action", "messages", "model", "parent_message_id", "timezone", "timezone_offset_min", "is_do_not_remember", "client_contextual_info", "local_function_names", "supported_encodings", "genui_state_snapshots", "client_prepare_state")
	for _, forbidden := range []string{"conversation_mode", "system_hints", "supports_buffering", "force_parallel_switch", "paragen_cot_summary_display_override", "enable_message_followups"} {
		if _, ok := body[forbidden]; ok {
			t.Fatalf("normal text request should not contain %q", forbidden)
		}
	}
	messages, _ := body["messages"].([]any)
	if len(messages) != 1 {
		t.Fatalf("messages = %v", body["messages"])
	}
	item, _ := messages[0].(map[string]any)
	assertKeys(t, item, "author", "channel", "content", "create_time", "end_turn", "id", "metadata", "recipient", "status", "update_time", "weight")
	author, _ := item["author"].(map[string]any)
	assertKeys(t, author, "metadata", "name", "role")
	if author["name"] != nil {
		t.Fatalf("author.name = %v", author["name"])
	}
	metadata, _ := item["metadata"].(map[string]any)
	assertKeys(t, metadata, "automation_creation_attribution")
	attribution, _ := metadata["automation_creation_attribution"].(map[string]any)
	if attribution["origin"] != "conversation" || attribution["flow_id"] != item["id"] {
		t.Fatalf("unexpected attribution: %v", attribution)
	}
}

func TestImageRequestAddsSystemHints(t *testing.T) {
	api := &OpenAIBackendAPI{}
	message, err := api.convertMessage(context.Background(), map[string]any{"role": "user", "content": "画一个红苹果"})
	if err != nil {
		t.Fatal(err)
	}
	hints := []string{"picture_v2"}
	payload := api.conversationPayload([]map[string]any{message}, "auto", "", hints, false)
	applySystemHints([]map[string]any{message}, hints)
	if values, _ := payload["system_hints"].([]string); len(values) != 1 || values[0] != "picture_v2" {
		t.Fatalf("top-level system_hints = %v", payload["system_hints"])
	}
	metadata, _ := message["metadata"].(map[string]any)
	if values, _ := metadata["system_hints"].([]string); len(values) != 1 || values[0] != "picture_v2" {
		t.Fatalf("message system_hints = %v", metadata["system_hints"])
	}
}

func assertKeys(t *testing.T, value map[string]any, keys ...string) {
	t.Helper()
	for _, key := range keys {
		if _, ok := value[key]; !ok {
			t.Fatalf("missing key %q in %v", key, value)
		}
	}
}

func TestPreparePayloadIncludesAttachments(t *testing.T) {
	body := preparePayload("auto", []string{"picture_v2"}, []string{"image/png"}, []string{"file_a", "file_b"})
	assertKeys(t, body, "client_prepare_state", "action", "model", "parent_message_id", "timezone", "timezone_offset_min", "is_do_not_remember", "local_function_names", "client_prepare_dispatch", "client_prepare_source", "system_hints", "attachment_mime_types", "prepare_image_upload_ids")
	if body["client_prepare_state"] != "sent" {
		t.Fatalf("client_prepare_state = %v", body["client_prepare_state"])
	}
	if _, ok := body["messages"]; ok {
		t.Fatal("prepare payload must not contain messages")
	}
	if _, ok := body["partial_query"]; ok {
		t.Fatal("prepare payload must not contain partial_query")
	}
	mimeTypes, _ := body["attachment_mime_types"].([]string)
	if len(mimeTypes) != 1 || mimeTypes[0] != "image/png" {
		t.Fatalf("attachment_mime_types = %v", body["attachment_mime_types"])
	}
	uploadIDs, _ := body["prepare_image_upload_ids"].([]string)
	if len(uploadIDs) != 2 || uploadIDs[0] != "file_a" || uploadIDs[1] != "file_b" {
		t.Fatalf("prepare_image_upload_ids = %v", body["prepare_image_upload_ids"])
	}
}

func TestConversationAttachments(t *testing.T) {
	messages := []map[string]any{{
		"metadata": map[string]any{
			"attachments": []map[string]any{
				{"id": "file_a", "mime_type": "image/png"},
				{"id": "file_b", "mime_type": "image/png"},
				{"id": "file_c", "mime_type": "image/jpeg"},
			},
		},
	}}
	mimeTypes, uploadIDs := conversationAttachments(messages)
	if len(mimeTypes) != 2 || mimeTypes[0] != "image/jpeg" || mimeTypes[1] != "image/png" {
		t.Fatalf("mimeTypes = %v", mimeTypes)
	}
	if len(uploadIDs) != 3 || uploadIDs[0] != "file_a" || uploadIDs[2] != "file_c" {
		t.Fatalf("uploadIDs = %v", uploadIDs)
	}
}
