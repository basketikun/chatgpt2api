package service

import "testing"

func TestImageTokenCounts(t *testing.T) {
	if got := countImageInputTokens(1024, 1024); got != 1659 {
		t.Fatalf("input tokens = %d", got)
	}
	for quality, expected := range map[string]int{"auto": 1056, "low": 272, "high": 4160} {
		if got := countGeneratedImageTokens(1024, 1024, quality); got != expected {
			t.Fatalf("%s output tokens = %d", quality, got)
		}
	}
}

