package service

import (
	"encoding/base64"
	"encoding/json"
	"testing"

	"github.com/basketikun/chatgpt2api/internal/repository"
)

func TestImportedAccountKeepsExistingFields(t *testing.T) {
	payload, _ := json.Marshal(map[string]any{"https://api.openai.com/auth": map[string]any{"chatgpt_plan_type": "PLUS"}, "https://api.openai.com/profile": map[string]any{"email": "a@example.com"}})
	token := "header." + base64.RawURLEncoding.EncodeToString(payload) + ".signature"
	current := repository.Account{AccessToken: token, RefreshToken: "refresh", Proxy: "http://proxy", Quota: 12, Success: 3, Type: "free"}
	merged := mergeImportedAccount(current, repository.Account{AccessToken: token})
	if err := applyTokenClaims(&merged); err != nil {
		t.Fatal(err)
	}
	if merged.RefreshToken != "refresh" || merged.Proxy != "http://proxy" || merged.Quota != 12 || merged.Success != 3 || merged.Type != "plus" {
		t.Fatalf("unexpected merged account: %#v", merged)
	}
}
