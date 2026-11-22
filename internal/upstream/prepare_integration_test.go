package upstream

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
	"testing"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/google/uuid"
)

// 真实上游联调：需要 TEST_CHATGPT_ACCESS_TOKEN，只上传图片并调用 prepare，
// 不消耗生图额度。上游 prepare 对 3 个及以上 upload ID 会返回 422（#426），
// 修复后该可选字段会被省略，这里保证多图准备仍然成功。
func TestPrepareManyImagesIntegration(t *testing.T) {
	token := os.Getenv("TEST_CHATGPT_ACCESS_TOKEN")
	if token == "" {
		t.Skip("set TEST_CHATGPT_ACCESS_TOKEN to run upstream integration tests")
	}
	cfg := &config.Config{DefaultModel: "auto", Image: config.ImageSettings{PollTimeoutSeconds: 120, PollIntervalSeconds: 5, PollInitialWaitSeconds: 10}}
	client := NewOpenAIBackendAPI(token, "", prepareProvider{}, cfg)
	ctx := context.Background()
	ids := make([]string, 0, 3)
	for index, value := range []color.RGBA{{255, 64, 64, 255}, {64, 255, 64, 255}, {64, 64, 255, 255}} {
		uploaded, err := client.Upload(ctx, encodeTestPNG(t, value), 64, 64, "image/png", fmt.Sprintf("prepare-%d.png", index+1))
		if err != nil {
			t.Fatalf("upload %d: %v", index+1, err)
		}
		id, _ := uploaded["file_id"].(string)
		if id == "" {
			t.Fatalf("upload %d: missing file id", index+1)
		}
		ids = append(ids, id)
	}
	if _, err := client.prepareConversation(ctx, "auto", []string{"picture_v2"}, []string{"image/png"}, ids, uuid.NewString()); err != nil {
		t.Fatalf("prepare with %d images: %v", len(ids), err)
	}
}

func encodeTestPNG(t *testing.T, value color.RGBA) []byte {
	t.Helper()
	img := image.NewRGBA(image.Rect(0, 0, 64, 64))
	for y := 0; y < 64; y++ {
		for x := 0; x < 64; x++ {
			img.Set(x, y, value)
		}
	}
	buffer := bytes.NewBuffer(nil)
	if err := png.Encode(buffer, img); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}
