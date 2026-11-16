package service

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLocalImagesExcludesThumbnails(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "2026", "08", "10")
	if err := os.MkdirAll(dir, 0755); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"manual.webp", "manual_thumbnail.png", "notes.txt"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte("data"), 0644); err != nil {
			t.Fatal(err)
		}
	}
	service := &ImageService{root: root}
	items, err := service.localImages()
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].rel != "2026/08/10/manual.webp" {
		t.Fatalf("unexpected local images: %#v", items)
	}
}
