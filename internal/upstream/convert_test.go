package upstream

import (
	"strings"
	"testing"
)

func TestReadConversationSSEIgnoresCompletedAssistantHistory(t *testing.T) {
	stream := strings.Join([]string{
		`data: {"v":{"message":{"id":"old","author":{"role":"assistant"},"status":"finished_successfully","end_turn":true,"content":{"parts":["old answer"]}}}}` + "\n\n",
		`data: {"v":{"message":{"id":"new","author":{"role":"assistant"},"status":"in_progress","content":{"parts":[""]}}}}` + "\n\n",
		`data: {"p":"/message/content/parts/0","o":"append","v":"new answer"}` + "\n\n",
		"data: [DONE]\n\n",
	}, "")
	var output strings.Builder
	if _, err := readConversationSSE(strings.NewReader(stream), func(value string) error { output.WriteString(value); return nil }); err != nil {
		t.Fatal(err)
	}
	if output.String() != "new answer" {
		t.Fatalf("got %q", output.String())
	}
}
