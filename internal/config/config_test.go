package config

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateBind(t *testing.T) {
	for _, value := range []string{"127.0.0.1", "0.0.0.0", "::1", "::", "fe80::1%eth0", "localhost"} {
		if err := validateBind(value); err != nil {
			t.Errorf("validateBind(%q) = %v", value, err)
		}
	}
	for _, value := range []string{"127.0.0.1:8080", "localhost:3000", "[::1]", "1.2.3.4/24", "127.0.0.1 192.168.1.1"} {
		if err := validateBind(value); err == nil {
			t.Errorf("validateBind(%q) = nil, want error", value)
		}
	}
}

func TestLoadBind(t *testing.T) {
	t.Setenv("CHATGPT2API_AUTH_KEY", "test-key")
	t.Setenv("PORT", "3999")
	path := filepath.Join(t.TempDir(), "config.yaml")

	t.Setenv("BIND_ADDR", " 127.0.0.1 ")
	cfg, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if cfg.Bind != "127.0.0.1" || cfg.Port != "3999" {
		t.Fatalf("Bind = %q, Port = %q", cfg.Bind, cfg.Port)
	}

	t.Setenv("BIND_ADDR", "127.0.0.1:8080")
	if _, err := Load(path); err == nil || !strings.Contains(err.Error(), "PORT") {
		t.Fatalf("Load error = %v, want hint about PORT", err)
	}
}
