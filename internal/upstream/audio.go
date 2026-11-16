package upstream

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/textproto"
	"net/url"
	"sort"
	"strings"
	"time"

	http "github.com/bogdanfinn/fhttp"
)

const speechRetryBudgetSeconds = 90.0

// speechVoices 是上游 /backend-api/synthesize 当前接受的音色标识。
// 真实网页端语音列表来自 GET /backend-api/settings/voices，返回
// juniper/maple/cove/breeze/orbit/glimmer/ember/fathom/vale；
// 该接口同时接受 OpenAI 音色名（alloy/ash/...），因此这里原样透传，不再做映射。
var speechVoices = map[string]bool{
	"juniper": true, "maple": true, "cove": true, "breeze": true, "orbit": true,
	"glimmer": true, "ember": true, "fathom": true, "vale": true,
	"alloy": true, "ash": true, "coral": true, "echo": true, "fable": true,
	"onyx": true, "nova": true, "sage": true, "shimmer": true,
}

// ResolveSpeechVoice 接受官网音色名与 OpenAI 音色名，原样返回。
func ResolveSpeechVoice(name string) (string, error) {
	voice := strings.ToLower(strings.TrimSpace(name))
	if voice == "" {
		return "cove", nil
	}
	if speechVoices[voice] {
		return voice, nil
	}
	return "", fmt.Errorf("不支持的音色 %q，可用音色：%s", name, strings.Join(SpeechVoiceNames(), ", "))
}

// SpeechVoiceNames lists the accepted voice names, official names first.
func SpeechVoiceNames() []string {
	names := make([]string, 0, len(speechVoices))
	for name := range speechVoices {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

// Synthesize renders a message that already exists in a conversation to speech.
func (u *OpenAIBackendAPI) Synthesize(ctx context.Context, conversationID string, messageID string, voice string, format string) ([]byte, string, error) {
	if format == "" {
		format = "mp3"
	}
	query := url.Values{"conversation_id": {conversationID}, "message_id": {messageID}, "voice": {voice}, "format": {format}}
	response, err := u.requestRetryBudget(ctx, http.MethodGet, "/backend-api/synthesize?"+query.Encode(), nil, nil, time.Duration(speechRetryBudgetSeconds*float64(time.Second)))
	if err != nil {
		return nil, "", err
	}
	defer response.Body.Close()
	data, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, "", err
	}
	contentType := response.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "audio/mpeg"
	}
	return data, contentType, nil
}

// Speak renders arbitrary text to speech. /backend-api/synthesize can only
// render a message that already exists, so the text is first materialised as an
// assistant turn. An instant model keeps that turn cheap — we only need it to
// echo text we already have.
func (u *OpenAIBackendAPI) Speak(ctx context.Context, text string, voice string, format string) ([]byte, string, error) {
	prompt := "请原样输出下面这段文字，一个字都不要改写、增删或解释，直接输出正文：\n\n" + text
	conversationID, messageID, err := u.echoTurn(ctx, prompt)
	if err != nil {
		return nil, "", err
	}
	if messageID == "" {
		detail, err := u.Conversation(ctx, conversationID)
		if err != nil {
			return nil, "", err
		}
		if messageID = latestAssistantMessageID(detail); messageID == "" {
			return nil, "", fmt.Errorf("上游没有返回可用于合成的消息，conversation_id=%s", conversationID)
		}
	}
	return u.Synthesize(ctx, conversationID, messageID, voice, format)
}

func (u *OpenAIBackendAPI) echoTurn(ctx context.Context, prompt string) (string, string, error) {
	budget := time.Duration(speechRetryBudgetSeconds * float64(time.Second))
	conversationID, messageID := "", ""
	err := retryTransient(ctx, budget, func() error {
		var startErr error
		conversationID, messageID, startErr = u.startConversationWithMessage(ctx, []map[string]any{{"role": "user", "content": prompt}}, u.options.DefaultUpstreamModelName, "", nil, false, false, func(string) error { return nil }, nil)
		return startErr
	})
	return conversationID, messageID, err
}

// Transcribe sends an audio clip to the web speech-to-text endpoint.
func (u *OpenAIBackendAPI) Transcribe(ctx context.Context, data []byte, filename string, contentType string) (string, error) {
	if filename == "" {
		filename = "audio.mp3"
	}
	if contentType == "" {
		contentType = "application/octet-stream"
	}
	var transcript string
	err := retryTransient(ctx, time.Duration(speechRetryBudgetSeconds*float64(time.Second)), func() error {
		body := &bytes.Buffer{}
		writer := multipart.NewWriter(body)
		header := make(textproto.MIMEHeader)
		header.Set("Content-Disposition", fmt.Sprintf(`form-data; name="file"; filename="%s"`, escapeMultipartFilename(filename)))
		header.Set("Content-Type", contentType)
		part, err := writer.CreatePart(header)
		if err != nil {
			return err
		}
		if _, err := part.Write(data); err != nil {
			return err
		}
		if err := writer.Close(); err != nil {
			return err
		}
		response, err := u.requestBody(ctx, http.MethodPost, "/backend-api/transcribe", bytes.NewReader(body.Bytes()), writer.FormDataContentType(), nil)
		if err != nil {
			return err
		}
		defer response.Body.Close()
		var payload struct {
			Text string `json:"text"`
		}
		if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
			return err
		}
		transcript = payload.Text
		return nil
	})
	if err != nil {
		return "", err
	}
	return transcript, nil
}

func latestAssistantMessageID(detail map[string]any) string {
	latest := ""
	for _, message := range conversationMessages(detail) {
		author, _ := message["author"].(map[string]any)
		if author["role"] != "assistant" || message["recipient"] != "all" {
			continue
		}
		content, _ := message["content"].(map[string]any)
		if content["content_type"] != "text" {
			continue
		}
		if id, _ := message["id"].(string); id != "" {
			latest = id
		}
	}
	return latest
}

// escapeMultipartFilename keeps the multipart header well formed for non ASCII
// file names such as Chinese recordings.
func escapeMultipartFilename(name string) string {
	name = strings.ReplaceAll(name, `"`, "")
	name = strings.ReplaceAll(name, "\r", "")
	name = strings.ReplaceAll(name, "\n", "")
	return name
}
