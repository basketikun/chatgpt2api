package upstream_test

import (
	"context"
	"os"
	"testing"

	"github.com/basketikun/chatgpt2api/internal/upstream"
	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/service"
)

func TestCodexAPIImageIntegration(t *testing.T) {
	token := os.Getenv("TEST_CHATGPT_ACCESS_TOKEN")
	if token == "" {
		t.Skip("set TEST_CHATGPT_ACCESS_TOKEN to run upstream integration tests")
	}
	cfg := &config.Config{}
	client := upstream.NewCodexAPI(token, upstream.CodexBaseURL, "", service.NewProxyService(cfg))
	image, err := client.StartImageGen(context.Background(), "A highly detailed square 2K image of a quiet futuristic library at sunrise", "gpt-6-luna", "gpt-image-2.6", nil, "2048x2048", "auto")
	if err != nil {
		t.Fatal(err)
	}
	if len(image) == 0 {
		t.Fatal("missing image")
	}
}


