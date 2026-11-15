package upstream_test

import (
	"context"
	"encoding/base64"
	"os"
	"strings"
	"testing"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/basketikun/chatgpt2api/internal/upstream"
)

func TestOpenAIBackendAccountIntegration(t *testing.T) {
	client := openAIBackendClient(t)
	email, err := client.Me(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if email == "" {
		t.Fatal("missing email")
	}
	remaining, resetAfter, err := client.QuotaInfo(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if remaining < 0 || resetAfter == "" {
		t.Fatalf("invalid quota: %d %q", remaining, resetAfter)
	}
	models, err := client.ListModels(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(models) == 0 {
		t.Fatal("missing models")
	}
}

func TestOpenAIBackendFilesIntegration(t *testing.T) {
	client := openAIBackendClient(t)
	image, err := base64.StdEncoding.DecodeString("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
	if err != nil {
		t.Fatal(err)
	}
	uploaded, err := client.Upload(context.Background(), image, 1, 1, "image/png")
	if err != nil {
		t.Fatal(err)
	}
	fileID, _ := uploaded["file_id"].(string)
	if fileID == "" {
		t.Fatal("missing file id")
	}
	downloaded, err := client.Download(context.Background(), "", fileID)
	if err != nil {
		t.Fatal(err)
	}
	if string(downloaded) != string(image) {
		t.Fatal("downloaded file mismatch")
	}
}

func TestOpenAIBackendConversationIntegration(t *testing.T) {
	client := openAIBackendClient(t)
	var first strings.Builder
	conversationID, err := client.StartConversation(context.Background(), []map[string]any{{"role": "user", "content": "记住数字 42"}}, "gpt-6-mini", "", nil, false, func(value string) error { first.WriteString(value); return nil })
	if err != nil {
		t.Fatal(err)
	}
	if conversationID == "" || first.Len() == 0 {
		t.Fatal("missing conversation result")
	}
	if _, err := client.Conversation(context.Background(), conversationID); err != nil {
		t.Fatal(err)
	}
}

func TestOpenAIBackendSearchIntegration(t *testing.T) {
	client := openAIBackendClient(t)
	var output strings.Builder
	conversationID, err := client.StartConversation(context.Background(), []map[string]any{{"role": "user", "content": "搜索 chatgpt2api 有关的内容"}}, "gpt-6-mini", "", nil, true, func(value string) error { output.WriteString(value); return nil })
	if err != nil {
		t.Fatal(err)
	}
	if conversationID == "" || output.Len() == 0 {
		t.Fatal("missing search result")
	}
}

func TestOpenAIBackendImageIntegration(t *testing.T) {
	client := openAIBackendClient(t)
	image, _, err := client.GenerateImage(context.Background(), "生成一只鸡", "gpt-image-2.6", nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(image) == 0 {
		t.Fatal("missing image")
	}
}

func TestOpenAIBackendAudioIntegration(t *testing.T) {
	client := openAIBackendClient(t)
	audio, contentType, err := client.Speak(context.Background(), "你好，这是一段语音合成的测试。", "cove", "mp3")
	if err != nil {
		t.Fatal(err)
	}
	if len(audio) == 0 || !strings.HasPrefix(contentType, "audio/") {
		t.Fatalf("invalid speech output: %d bytes, content type %q", len(audio), contentType)
	}
	text, err := client.Transcribe(context.Background(), audio, "speech.mp3", contentType)
	if err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(text) == "" {
		t.Fatal("missing transcript")
	}
}

func openAIBackendClient(t *testing.T) *upstream.OpenAIBackendAPI {
	t.Helper()
	token := os.Getenv("TEST_CHATGPT_ACCESS_TOKEN")
	if token == "" {
		t.Skip("set TEST_CHATGPT_ACCESS_TOKEN to run upstream integration tests")
	}
	cfg := &config.Config{Image: config.ImageSettings{PollTimeoutSeconds: 120, PollIntervalSeconds: 10, PollInitialWaitSeconds: 10}}
	return upstream.NewOpenAIBackendAPI(token, "", service.NewProxyService(cfg), cfg)
}
