package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

func TestWriteImageErrorPrepareRejected(t *testing.T) {
	gin.SetMode(gin.TestMode)
	recorder := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(recorder)
	writeImageError(context, &service.ImageError{
		Err:    errors.New(`/backend-api/f/conversation/prepare failed: HTTP 422: {"detail":"Invalid conversation body"}`),
		Status: http.StatusUnprocessableEntity,
		Type:   "invalid_request_error",
		Code:   "upstream_prepare_rejected",
	})
	if recorder.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d", recorder.Code)
	}
	var body struct {
		Error struct {
			Message string `json:"message"`
			Code    string `json:"code"`
		} `json:"error"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body.Error.Code != "upstream_prepare_rejected" {
		t.Fatalf("code = %q", body.Error.Code)
	}
	if strings.Contains(body.Error.Message, "backend-api") || strings.Contains(body.Error.Message, "Invalid conversation body") {
		t.Fatalf("message leaks upstream detail: %q", body.Error.Message)
	}
	if !strings.Contains(body.Error.Message, "reference images") {
		t.Fatalf("message should explain the reference image limit: %q", body.Error.Message)
	}
}
