package upstream

import (
	"bytes"
	"image"
	"os"
	"path/filepath"
	"testing"
)

// testdata 下是两张 64×48 的 WebP：vp8x_alpha.webp 带 alpha，
// vp8x_no_alpha.webp 无 alpha 但带 XMP（同属 VP8X 容器）。后者在旧版
// x/image 上会报 "webp: non-Alpha VP8X is not implemented"，
// 见 https://github.com/basketikun/chatgpt2api/issues/429。
func TestImageMetadataWebP(t *testing.T) {
	for _, test := range []struct {
		name          string
		width, height int
	}{
		{"vp8x_alpha.webp", 64, 48},
		{"vp8x_no_alpha.webp", 64, 48},
	} {
		t.Run(test.name, func(t *testing.T) {
			data, err := os.ReadFile(filepath.Join("testdata", test.name))
			if err != nil {
				t.Fatal(err)
			}
			width, height, mimeType, err := imageMetadata(data)
			if err != nil {
				t.Fatalf("imageMetadata: %v", err)
			}
			if width != test.width || height != test.height || mimeType != "image/webp" {
				t.Fatalf("imageMetadata = %dx%d %s", width, height, mimeType)
			}
			if _, format, err := image.DecodeConfig(bytes.NewReader(data)); err != nil || format != "webp" {
				t.Fatalf("image.DecodeConfig = %s, %v", format, err)
			}
			if _, _, err := image.Decode(bytes.NewReader(data)); err != nil {
				t.Fatalf("image.Decode: %v", err)
			}
		})
	}
}
