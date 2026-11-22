package upstream

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"slices"
	"testing"

	tls_client "github.com/bogdanfinn/tls-client"
	"github.com/bogdanfinn/tls-client/profiles"

	"github.com/basketikun/chatgpt2api/internal/config"
)

// prepareProvider 复用真实 TLS 客户端，但不走代理，便于把请求打到本地 httptest。
type prepareProvider struct{}

func (prepareProvider) TLSClient(string, bool, ...int) (tls_client.HttpClient, error) {
	return tls_client.NewHttpClient(tls_client.NewNoopLogger(), tls_client.WithTimeoutSeconds(300), tls_client.WithClientProfile(profiles.Chrome_146), tls_client.WithRandomTLSExtensionOrder())
}

func (prepareProvider) UpstreamClearance(context.Context, string) (string, map[string]string) {
	return "", nil
}

// 上游 prepare 接口最多接受 2 个 upload ID，3 个及以上会返回 422
// Invalid conversation body（#426）；正式会话消息仍然携带全部附件。
func TestPreparePayloadUploadIDs(t *testing.T) {
	ids := []string{"file_1", "file_2", "file_3", "file_4"}
	for _, test := range []struct {
		count int
		want  []string
	}{
		{0, nil},
		{1, []string{"file_1"}},
		{2, []string{"file_1", "file_2"}},
		{3, nil},
		{4, nil},
	} {
		body := preparePayload("gpt-5-6", []string{"picture_v2"}, []string{"image/png"}, ids[:test.count])
		value, ok := body["prepare_image_upload_ids"]
		if test.want == nil {
			if ok {
				t.Errorf("count=%d: prepare_image_upload_ids = %v, want omitted", test.count, value)
			}
		} else {
			got, _ := value.([]string)
			if !ok || !slices.Equal(got, test.want) {
				t.Errorf("count=%d: prepare_image_upload_ids = %v, want %v", test.count, value, test.want)
			}
		}
		if _, ok := body["attachment_mime_types"]; !ok {
			t.Errorf("count=%d: attachment_mime_types missing", test.count)
		}
	}
}

func TestPrepareConversationOmitsUploadIDsForLargeBatches(t *testing.T) {
	var bodies []map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		body := map[string]any{}
		_ = json.NewDecoder(request.Body).Decode(&body)
		bodies = append(bodies, body)
		ids, _ := body["prepare_image_upload_ids"].([]any)
		if len(ids) > 2 {
			writer.WriteHeader(http.StatusUnprocessableEntity)
			_, _ = writer.Write([]byte(`{"detail":"Invalid conversation body"}`))
			return
		}
		_, _ = writer.Write([]byte(`{"conduit_token":"conduit"}`))
	}))
	defer server.Close()

	client := NewOpenAIBackendAPI("token", "", prepareProvider{}, &config.Config{})
	client.baseURL = server.URL
	conduit, err := client.prepareConversation(context.Background(), "gpt-5-6", []string{"picture_v2"}, []string{"image/png"}, []string{"file_1", "file_2", "file_3"}, "trace")
	if err != nil {
		t.Fatalf("prepareConversation: %v", err)
	}
	if conduit != "conduit" {
		t.Fatalf("conduit = %q", conduit)
	}
	if len(bodies) != 1 {
		t.Fatalf("requests = %d", len(bodies))
	}
	if value, ok := bodies[0]["prepare_image_upload_ids"]; ok {
		t.Fatalf("prepare_image_upload_ids = %v, want omitted", value)
	}
}
