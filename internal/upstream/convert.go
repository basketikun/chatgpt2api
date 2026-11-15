package upstream

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	_ "image/gif"
	_ "image/jpeg"
	_ "image/png"
	"io"
	"strings"
	"time"

	"github.com/google/uuid"
	_ "golang.org/x/image/bmp"
	_ "golang.org/x/image/tiff"
	_ "golang.org/x/image/webp"
)

// ConvertThinkingEffort 保留上游支持的完整档位。不同套餐/模型开放的档位不同
// （免费号常见 standard / extended，Pro/Codex 还可能支持 low / medium / high /
// xhigh / max / ultra），这里只把别名归一化，其余非空值原样透传。
func ConvertThinkingEffort(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	switch value {
	case "", "auto", "default":
		return ""
	case "extra-high", "extra_high":
		return "xhigh"
	default:
		return value
	}
}

func (u *OpenAIBackendAPI) convertMessage(ctx context.Context, message map[string]any) (map[string]any, error) {
	role, _ := message["role"].(string)
	if role == "" {
		role = "user"
	}
	parts := []any{}
	attachments := []map[string]any{}
	switch content := message["content"].(type) {
	case string:
		parts = append(parts, content)
	case []any:
		text := strings.Builder{}
		for _, raw := range content {
			item, _ := raw.(map[string]any)
			if item["type"] == "text" || item["type"] == "input_text" {
				text.WriteString(fmt.Sprint(item["text"]))
			}
			if item["type"] == "image" {
				data, ok := item["data"].([]byte)
				if !ok {
					return nil, errors.New("image data must be bytes")
				}
				width, height, mimeType, err := imageMetadata(data)
				if err != nil {
					return nil, err
				}
				name, _ := item["name"].(string)
				if name == "" {
					name = "image.png"
				}
				uploaded, err := u.Upload(ctx, data, width, height, mimeType, name)
				if err != nil {
					return nil, err
				}
				fileID := fmt.Sprint(uploaded["file_id"])
				parts = append(parts, map[string]any{"content_type": "image_asset_pointer", "asset_pointer": "sediment://" + fileID, "width": width, "height": height, "size_bytes": len(data)})
				attachment := map[string]any{"id": fileID, "name": name, "size": len(data), "width": width, "height": height, "mime_type": mimeType, "source": "local"}
				if libraryID, ok := uploaded["library_file_id"].(string); ok && libraryID != "" {
					attachment["library_file_id"] = libraryID
				}
				attachments = append(attachments, attachment)
			}
		}
		if text.Len() > 0 {
			parts = append(parts, text.String())
		}
	default:
		return nil, errors.New("only string or list message content is supported")
	}
	contentType := "text"
	if len(attachments) > 0 {
		contentType = "multimodal_text"
	}
	messageID := uuid.NewString()
	metadata := map[string]any{}
	if role == "user" {
		metadata["automation_creation_attribution"] = map[string]any{"origin": "conversation", "flow_id": messageID}
	}
	if len(attachments) > 0 {
		metadata["attachments"] = attachments
	}
	if settings, ok := message["image_generation_settings"]; ok && settings != nil {
		metadata["image_generation_settings"] = settings
	}
	return map[string]any{"id": messageID, "author": map[string]any{"role": role, "name": nil, "metadata": map[string]any{}}, "create_time": float64(time.Now().UnixNano()) / 1e9, "update_time": nil, "content": map[string]any{"content_type": contentType, "parts": parts}, "metadata": metadata, "channel": nil, "recipient": "all", "status": "finished_successfully", "end_turn": nil, "weight": 1}, nil
}

func readConversationSSE(reader io.Reader, delta func(string) error) (string, error) {
	return readConversationSSEWithTextRequirement(reader, delta, true)
}

func readConversationSSEWithTextRequirement(reader io.Reader, delta func(string) error, requireText bool, createdCallbacks ...func(string) error) (string, error) {
	conversationID, _, err := readConversationSSEWithMessage(reader, delta, requireText, createdCallbacks...)
	return conversationID, err
}

// readConversationSSEWithMessage also returns the assistant message id seen on
// the stream, so callers that need to address that message afterwards (speech
// synthesis) can skip a second round trip to fetch the conversation.
func readConversationSSEWithMessage(reader io.Reader, delta func(string) error, requireText bool, createdCallbacks ...func(string) error) (string, string, error) {
	var created func(string) error
	if len(createdCallbacks) > 0 {
		created = createdCallbacks[0]
	}
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 64*1024), 32*1024*1024)
	conversationID, current, messageID := "", "", ""
	eventCounts := map[string]int{}
	channels := map[string]bool{}
	upstreamError := ""
	started, createdSent := false, false
	for scanner.Scan() {
		line := scanner.Text()
		if !strings.HasPrefix(line, "data:") {
			continue
		}
		value := strings.TrimPrefix(line, "data: ")
		if value == "[DONE]" {
			break
		}
		var event map[string]any
		if json.Unmarshal([]byte(value), &event) != nil {
			eventCounts["invalid_json"]++
			continue
		}
		eventType, _ := event["type"].(string)
		if eventType == "" {
			eventType = "event"
			if event["v"] != nil {
				eventType = "delta"
			}
		}
		eventCounts[eventType]++
		if value := event["error"]; value != nil {
			upstreamError = fmt.Sprint(value)
		} else if value := event["error_code"]; value != nil {
			upstreamError = fmt.Sprint(value)
		}
		if id, ok := event["conversation_id"].(string); ok {
			conversationID = id
		}
		if nested, ok := event["v"].(map[string]any); ok {
			if id, ok := nested["conversation_id"].(string); ok {
				conversationID = id
			}
		}
		if !createdSent && conversationID != "" {
			createdSent = true
			if created != nil {
				if err := created(conversationID); err != nil {
					return conversationID, messageID, err
				}
			}
		}
		text := current
		message := assistantMessage(event)
		if message != nil {
			channels[fmt.Sprint(message["channel"])] = true
			id, _ := message["id"].(string)
			status, _ := message["status"].(string)
			if !started && (message["end_turn"] == true || strings.HasPrefix(status, "finished")) {
				continue
			}
			if messageID != "" && id != "" && id != messageID {
				continue
			}
			started = true
			if messageID == "" {
				messageID = id
			}
			if value := messageText(message); value != "" {
				text = value
			}
		} else if started {
			text = applyConversationTextPatch(event, current)
		} else {
			continue
		}
		if text == current {
			continue
		}
		next := text
		if strings.HasPrefix(text, current) {
			next = strings.TrimPrefix(text, current)
		}
		current = text
		if next != "" && delta != nil {
			if err := delta(next); err != nil {
				return conversationID, messageID, err
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return conversationID, messageID, err
	}
	if current == "" && requireText {
		return conversationID, messageID, fmt.Errorf("ChatGPT SSE completed without assistant text: conversation_id=%s, events=%v, assistant_channels=%v, upstream_error=%s", defaultConversationID(conversationID), eventCounts, channels, defaultUpstreamError(upstreamError))
	}
	return conversationID, messageID, nil
}

func imageMetadata(data []byte) (int, int, string, error) {
	metadata, format, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil {
		return 0, 0, "", err
	}
	if format == "jpg" {
		format = "jpeg"
	}
	return metadata.Width, metadata.Height, "image/" + format, nil
}

func defaultConversationID(value string) string {
	if value == "" {
		return "unknown"
	}
	return value
}

func defaultUpstreamError(value string) string {
	if value == "" {
		return "none"
	}
	return value
}

func assistantMessage(event map[string]any) map[string]any {
	candidates := []map[string]any{event}
	if value, ok := event["v"].(map[string]any); ok {
		candidates = append(candidates, value)
	}
	for _, candidate := range candidates {
		message, _ := candidate["message"].(map[string]any)
		author, _ := message["author"].(map[string]any)
		metadata, _ := message["metadata"].(map[string]any)
		recipient, _ := message["recipient"].(string)
		channel, _ := message["channel"].(string)
		if author["role"] == "assistant" && (metadata["is_visually_hidden_from_conversation"] != true || channel == "final") && (recipient == "" || recipient == "all") && (channel == "" || channel == "final") {
			return message
		}
	}
	return nil
}

func messageText(message map[string]any) string {
	content, _ := message["content"].(map[string]any)
	parts, _ := content["parts"].([]any)
	result := strings.Builder{}
	for _, part := range parts {
		if text, ok := part.(string); ok {
			result.WriteString(text)
		}
	}
	if result.Len() == 0 {
		if text, ok := content["text"].(string); ok {
			result.WriteString(text)
		}
	}
	return result.String()
}

func applyConversationTextPatch(event map[string]any, current string) string {
	if event["p"] == "/message/content/parts/0" {
		value, _ := event["v"].(string)
		if event["o"] == "replace" {
			return value
		}
		return current + value
	}
	if value, ok := event["v"].(string); ok && event["p"] == nil && event["o"] == nil {
		return current + value
	}
	if values, ok := event["v"].([]any); ok {
		for _, raw := range values {
			if operation, ok := raw.(map[string]any); ok {
				current = applyConversationTextPatch(operation, current)
			}
		}
	}
	return current
}
