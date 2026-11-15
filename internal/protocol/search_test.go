package protocol

import "testing"

func TestCleanSearchText(t *testing.T) {
	input := "答案 \ue200url\ue202来源\ue202https://example.com\ue201 。"
	got := CleanSearchText(input)
	if got != "答案 来源 (https://example.com)。" {
		t.Fatalf("clean text = %q", got)
	}
	annotations := SearchAnnotations(got)
	if len(annotations) != 1 || annotations[0]["url"] != "https://example.com" || annotations[0]["start_index"] != 7 {
		t.Fatalf("annotations = %#v", annotations)
	}
}
