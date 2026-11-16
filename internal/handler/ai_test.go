package handler

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

func TestParseImageRequestJSON(t *testing.T) {
	png := "data:image/png;base64," + base64.StdEncoding.EncodeToString([]byte("png"))
	jpeg := base64.StdEncoding.EncodeToString([]byte("jpeg"))
	body := map[string]any{"prompt": "merge", "images": []any{png, map[string]any{"b64_json": jpeg}, map[string]any{"image_url": map[string]any{"url": png}}}}
	request, err := parseJSONImageRequest(t, "/v1/images/edits", body)
	if err != nil {
		t.Fatal(err)
	}
	if request.Model != "" {
		t.Fatalf("got model %q", request.Model)
	}
	if len(request.Images) != 3 || string(request.Images[0]) != "png" || string(request.Images[1]) != "jpeg" || string(request.Images[2]) != "png" {
		t.Fatalf("got images %#v", request.Images)
	}
}

func TestParseImageRequestKeepsModel(t *testing.T) {
	request, err := parseJSONImageRequest(t, "/v1/images/edits", map[string]any{"model": "gpt-image-2.6", "prompt": "edit", "image": base64.StdEncoding.EncodeToString([]byte("image"))})
	if err != nil {
		t.Fatal(err)
	}
	if request.Model != "gpt-image-2.6" {
		t.Fatalf("got model %q", request.Model)
	}
}

func TestParseImageRequestMultipart(t *testing.T) {
	body := bytes.NewBuffer(nil)
	writer := multipart.NewWriter(body)
	if err := writer.WriteField("prompt", "merge"); err != nil {
		t.Fatal(err)
	}
	for _, file := range []struct{ field, name, data string }{{"image", "one.png", "one"}, {"image", "two.jpg", "two"}, {"image[]", "three.webp", "three"}} {
		part, err := writer.CreateFormFile(file.field, file.name)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := part.Write([]byte(file.data)); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	context := testContext(httptest.NewRequest(http.MethodPost, "/v1/images/edits", body))
	context.Request.Header.Set("Content-Type", writer.FormDataContentType())
	request, err := parseImageRequest(context)
	if err != nil {
		t.Fatal(err)
	}
	if len(request.Images) != 3 || string(request.Images[0]) != "one" || string(request.Images[1]) != "two" || string(request.Images[2]) != "three" {
		t.Fatalf("got images %#v", request.Images)
	}
}

func TestParseImageRequestValidation(t *testing.T) {
	image := base64.StdEncoding.EncodeToString([]byte("image"))
	for _, test := range []struct {
		name, path string
		body       map[string]any
	}{
		{"prompt", "/v1/images/generations", map[string]any{}},
		{"count", "/v1/images/generations", map[string]any{"prompt": "draw", "n": 5}},
		{"edit image", "/v1/images/edits", map[string]any{"prompt": "edit"}},
		{"invalid image", "/v1/images/edits", map[string]any{"prompt": "edit", "image": image + "!"}},
	} {
		t.Run(test.name, func(t *testing.T) {
			if _, err := parseJSONImageRequest(t, test.path, test.body); err == nil {
				t.Fatal("expected error")
			}
		})
	}
}

func parseJSONImageRequest(t *testing.T, path string, body map[string]any) (request service.ImageRequest, err error) {
	t.Helper()
	data, err := json.Marshal(body)
	if err != nil {
		return request, err
	}
	context := testContext(httptest.NewRequest(http.MethodPost, path, bytes.NewReader(data)))
	context.Request.Header.Set("Content-Type", "application/json")
	return parseImageRequest(context)
}

func testContext(request *http.Request) *gin.Context {
	context, _ := gin.CreateTestContext(httptest.NewRecorder())
	context.Request = request
	return context
}
