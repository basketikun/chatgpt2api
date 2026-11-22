package service

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/repository"
)

// 没有任何可用账号时应该立即返回额度错误，而不是每秒轮询直到客户端超时。
func TestImageTokenFailsFastWithoutAccounts(t *testing.T) {
	repo, err := repository.Open("sqlite:///" + filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer repo.Close()
	accounts := NewAccountService(repo, NewProxyService(&config.Config{}))
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	started := time.Now()
	if _, err := accounts.ImageToken(ctx, []string{"web"}, nil); err == nil {
		t.Fatal("expected error without accounts")
	}
	if elapsed := time.Since(started); elapsed > time.Second {
		t.Fatalf("ImageToken waited %s without accounts", elapsed)
	}
}
