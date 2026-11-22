package service

import (
	"net/http"
	"testing"

	chatgpt "github.com/basketikun/chatgpt2api/internal/upstream"
)

func TestNewImageErrorPrepareRejection(t *testing.T) {
	err := &chatgpt.UpstreamHTTPError{Context: "/backend-api/f/conversation/prepare", StatusCode: http.StatusUnprocessableEntity, Body: `{"detail":"Invalid conversation body"}`}
	imageErr := newImageError(err)
	if imageErr.Status != http.StatusUnprocessableEntity || imageErr.Type != "invalid_request_error" || imageErr.Code != "upstream_prepare_rejected" {
		t.Fatalf("status=%d type=%q code=%q", imageErr.Status, imageErr.Type, imageErr.Code)
	}
	if imageRetryable(imageErr) {
		t.Fatal("prepare rejection must not switch accounts")
	}
}

func TestNewImageErrorKeepsOtherUpstreamErrors(t *testing.T) {
	err := &chatgpt.UpstreamHTTPError{Context: "/backend-api/f/conversation", StatusCode: http.StatusUnprocessableEntity, Body: "unexpected"}
	imageErr := newImageError(err)
	if imageErr.Status != http.StatusBadGateway || imageErr.Code != "upstream_error" {
		t.Fatalf("status=%d code=%q", imageErr.Status, imageErr.Code)
	}
	if !imageRetryable(imageErr) {
		t.Fatal("generic upstream failure should stay retryable")
	}
}
