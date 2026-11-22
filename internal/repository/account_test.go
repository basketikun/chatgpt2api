package repository

import (
	"context"
	"path/filepath"
	"testing"
)

func TestImageAccountAvailable(t *testing.T) {
	repo, err := Open("sqlite:///" + filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer repo.Close()
	ctx := context.Background()
	email := "a@example.com"
	account := Account{AccessToken: "token", Email: &email, AccountID: "acc", Type: "free", Status: "正常", Quota: 5, CreatedAt: "2026-11-22T00:00:00Z"}
	if _, _, err := repo.SaveAccounts(ctx, []Account{account}); err != nil {
		t.Fatal(err)
	}

	for _, test := range []struct {
		name      string
		routes    []string
		plans     []string
		attempted map[string]bool
		want      bool
	}{
		{"available", []string{"web"}, nil, nil, true},
		{"attempted", []string{"web"}, nil, map[string]bool{email: true}, false},
		{"codex route needs codex account", []string{"codex"}, nil, nil, false},
		{"plan mismatch", []string{"web"}, []string{"plus"}, nil, false},
	} {
		available, err := repo.ImageAccountAvailable(ctx, test.routes, test.plans, test.attempted)
		if err != nil {
			t.Fatalf("%s: %v", test.name, err)
		}
		if available != test.want {
			t.Errorf("%s: available = %v, want %v", test.name, available, test.want)
		}
	}

	if _, err := repo.UpdateAccount(ctx, email, map[string]any{"quota": 0}); err != nil {
		t.Fatal(err)
	}
	if available, err := repo.ImageAccountAvailable(ctx, []string{"web"}, nil, nil); err != nil || available {
		t.Fatalf("quota exhausted: available = %v, err = %v", available, err)
	}
}
